"""Durable result materialization, with one idempotent merge per unique stage."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from .contracts import MAX_CLIENT_REQUEST_ID_LENGTH, ApiProblem, utc_now_text
from .odb_merge_operations import OdbMergeOperationRequest
from .operation_journal import OperationJournal
from .restart_result_plans import build_restart_result_plan

ACTIVE = {"queued", "running", "cancelling"}
TERMINAL = {"succeeded", "failed", "cancelled"}
OPTIONS = {"includeHistory", "compressResult", "copyOriginal"}


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def _stat(path):
    value = Path(path).stat()
    if not Path(path).is_file() or value.st_size == 0:
        raise ValueError(f"文件为空或不是普通文件：{path}")
    return [
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    ]


def _source_identity(path):
    # Bounded reads keep admission responsive for multi-GB sources. Unlike full
    # result SHA256 below, this is a sampled identity and is documented as such.
    before = _stat(path)
    digest = hashlib.sha256()
    size = before[2]
    with Path(path).open("rb") as stream:
        for offset in sorted({0, max(0, size // 2 - 32768), max(0, size - 65536)}):
            stream.seek(offset)
            digest.update(offset.to_bytes(8, "little"))
            digest.update(stream.read(65536))
    if _stat(path) != before:
        raise ValueError(f"读取期间源文件发生变化：{path}")
    return {"stat": before, "sampleSha256": digest.hexdigest()}


def _identity(path, stopped):
    before = _stat(path)
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            if stopped.is_set():
                raise InterruptedError("已停止结果校验")
            digest.update(block)
    if _stat(path) != before:
        raise ValueError(f"校验期间文件发生变化：{path}")
    return {"stat": before, "sha256": digest.hexdigest()}


def _stages(plans):
    """Compile each ancestry separately. Sharing never adds a sibling to a chain."""
    stages, targets, shared = [], [], {}
    for plan in plans:
        if not plan.get("valid") or not plan.get("steps"):
            raise ValueError("完整结果计划不可执行")
        parent = None
        previous = None
        for step in plan["steps"]:
            paths = [step[name] for name in ("originalOdb", "restartOdb", "outputOdb")]
            if any(
                not Path(path).is_absolute() or Path(path).suffix.lower() != ".odb"
                for path in paths
            ):
                raise ValueError("计划必须使用绝对 ODB 路径")
            if previous is not None and _key(paths[0]) != _key(previous):
                raise ValueError("计划中的祖先顺序不连续")
            signature = (parent, *map(_key, paths))
            if signature not in shared:
                shared[signature] = len(stages)
                stages.append(
                    {
                        "index": len(stages),
                        "parent": parent,
                        "originalOdb": paths[0],
                        "restartOdb": paths[1],
                        "outputOdb": paths[2],
                        "jobName": step["jobName"],
                        "childOperationId": None,
                        "submitted": False,
                        "message": "",
                        "result": None,
                        "identity": {},
                    }
                )
            parent = shared[signature]
            previous = paths[2]
        targets.append({"targetJobName": plan["targetJobName"], "stageIndex": parent})
    if not stages:
        raise ValueError("没有可执行的合并阶段")
    sources = {_key(s["restartOdb"]) for s in stages}
    sources.update(_key(s["originalOdb"]) for s in stages if s["parent"] is None)
    outputs = [_key(s["outputOdb"]) for s in stages]
    if len(outputs) != len(set(outputs)) or sources.intersection(outputs):
        raise ValueError("计划输出与源文件或其他阶段冲突")
    return stages, targets, sources


def _validate_request(request):
    if not isinstance(request, dict) or set(request) != {
        "schemaVersion",
        "clientRequestId",
        "source",
        "options",
    }:
        raise ValueError("批量请求字段无效")
    client = request["clientRequestId"]
    if (
        type(request["schemaVersion"]) is not int
        or request["schemaVersion"] != 1
        or not isinstance(client, str)
        or not client.strip()
        or len(client) > MAX_CLIENT_REQUEST_ID_LENGTH
        or any(ord(c) < 32 for c in client)
    ):
        raise ValueError("批量请求版本或标识无效")
    options = request["options"]
    if (
        not isinstance(options, dict)
        or set(options) != OPTIONS
        or any(type(v) is not bool for v in options.values())
    ):
        raise ValueError("批量合并选项无效")
    source = request["source"]
    if not isinstance(source, dict):
        raise TypeError("请选择结果图或重启动计划")
    if source.get("kind") == "graph":
        if (
            set(source) != {"kind", "revision", "targetNodeIds"}
            or type(source["revision"]) is not int
            or source["revision"] < 0
            or not isinstance(source["targetNodeIds"], list)
            or not source["targetNodeIds"]
            or any(not isinstance(s, str) or not s for s in source["targetNodeIds"])
        ):
            raise ValueError("结果图目标或修订号无效")
    elif source.get("kind") == "restart":
        if set(source) != {"kind", "expectedPlan"} or not isinstance(
            source["expectedPlan"], dict
        ):
            raise ValueError("重启动计划无效")
    else:
        raise ValueError("不支持该结果计划来源")


def validate_record(record):
    if (
        not isinstance(record, dict)
        or set(record) != {"schemaVersion", "request", "sources", "snapshot"}
        or record["schemaVersion"] != 1
    ):
        raise ValueError("批量任务记录结构无效")
    _validate_request(record["request"])
    item = record["snapshot"]
    if set(item) != {
        "schemaVersion",
        "kind",
        "operationId",
        "clientRequestId",
        "createdAt",
        "updatedAt",
        "version",
        "status",
        "phase",
        "error",
        "plans",
        "stages",
        "targets",
        "options",
    }:
        raise ValueError("批量任务快照结构无效")
    if (
        item["schemaVersion"] != 1
        or item["kind"] != "odb.result_batch"
        or item["status"] not in ACTIVE | TERMINAL | {"suspended"}
        or item["clientRequestId"] != record["request"]["clientRequestId"]
        or item["options"] != record["request"]["options"]
        or type(item["version"]) is not int
        or item["version"] < 1
        or any(
            not isinstance(item[k], str) or not item[k]
            for k in ("operationId", "createdAt", "updatedAt", "phase")
        )
    ):
        raise ValueError("批量任务身份或状态无效")
    if item["error"] is not None and (
        not isinstance(item["error"], dict)
        or set(item["error"]) != {"code", "message"}
        or any(not isinstance(v, str) for v in item["error"].values())
    ):
        raise ValueError("批量任务错误记录无效")
    stages, targets, sources = _stages(item["plans"])
    if (
        targets != item["targets"]
        or len(stages) != len(item["stages"])
        or set(record["sources"]) != sources
    ):
        raise ValueError("批量计划与进度不一致")
    if any(
        not isinstance(s, dict)
        or set(s) != {"stat", "sampleSha256"}
        or not isinstance(s["stat"], list)
        or len(s["stat"]) != 5
        or any(type(n) is not int for n in s["stat"])
        or not isinstance(s["sampleSha256"], str)
        or len(s["sampleSha256"]) != 64
        for s in record["sources"].values()
    ):
        raise ValueError("批量源文件身份无效")
    for template, stage in zip(stages, item["stages"], strict=True):
        if set(template) != set(stage) or any(
            template[k] != stage[k]
            for k in template
            if k
            not in {"childOperationId", "submitted", "message", "result", "identity"}
        ):
            raise ValueError("批量阶段被修改")
        if not isinstance(stage["message"], str):
            raise TypeError("批量阶段提示无效")
        if type(stage["submitted"]) is not bool or (
            stage["childOperationId"] is not None
            and (
                not isinstance(stage["childOperationId"], str)
                or not stage["childOperationId"]
                or not stage["submitted"]
            )
        ):
            raise ValueError("批量阶段提交记录无效")
        result = stage["result"]
        if result is None:
            if stage["identity"]:
                raise ValueError("未完成阶段包含结果身份")
        else:
            if (
                not isinstance(result, dict)
                or not result.get("outputOdb")
                or not result.get("validationReport")
                or not stage["childOperationId"]
                or (
                    stage["parent"] is not None
                    and item["stages"][stage["parent"]]["result"] is None
                )
            ):
                raise ValueError("批量阶段结果不完整")
            expected = {result["outputOdb"], result["validationReport"]}
            if set(stage["identity"]) != expected or any(
                not Path(p).is_absolute() or _key(p) in sources for p in expected
            ):
                raise ValueError("批量结果身份缺失或与源冲突")
            for identity in stage["identity"].values():
                if (
                    set(identity) != {"stat", "sha256"}
                    or len(identity["stat"]) != 5
                    or len(identity["sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in identity["sha256"])
                ):
                    raise ValueError("批量结果摘要无效")
    if item["status"] == "succeeded" and (
        item["error"] is not None or any(s["result"] is None for s in item["stages"])
    ):
        raise ValueError("批量成功状态缺少已验证结果")


class OdbResultBatchManager:
    def __init__(self, merge_manager, graph_service, journal_path, *, joblist_path=None):
        self._merge = merge_manager
        self._graph = graph_service
        self._joblist_path = joblist_path
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="odb-result-batch"
        )
        self._records, self._stops = {}, {}
        self._closed = self._disposed = False
        self._journal = None
        self._storage_error = None
        try:
            self._journal = OperationJournal(
                journal_path, table="batch_operations", validator=validate_record
            )
            records = self._journal.load()
            if len({r["request"]["clientRequestId"] for r in records}) != len(records):
                raise ValueError("批量记录包含重复请求")
            for record in records:
                item = record["snapshot"]
                self._records[item["operationId"]] = record
                self._stops[item["operationId"]] = threading.Event()
                if item["status"] in ACTIVE:
                    item["status"] = "suspended"
                    item["phase"] = (
                        "后台已重启；可检查已完成结果并继续，状态不明的阶段不会重跑"
                    )
                    self._save(record)
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
            self._storage_error = str(error)

    def _require_storage(self):
        if self._storage_error:
            raise ApiProblem(
                503,
                "ODB_BATCH_HISTORY_UNAVAILABLE",
                "批量记录无法读取或保存，已禁止新步骤；请保留后台和记录并检查磁盘。",
            )

    def _save(self, record):
        self._require_storage()
        item = record["snapshot"]
        item["version"] += 1
        item["updatedAt"] = utc_now_text()
        try:
            self._journal.save(record)
        except (OSError, ValueError, TypeError, sqlite3.Error) as error:
            self._storage_error = str(error)
            for stopped in self._stops.values():
                stopped.set()
            self._require_storage()

    def create(self, payload):
        try:
            _validate_request(payload)
        except (ValueError, TypeError, KeyError) as error:
            raise ApiProblem(400, "INVALID_ODB_BATCH_REQUEST", str(error)) from error
        with self._lock:
            self._require_storage()
            if self._closed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在关闭")
            for record in self._records.values():
                if record["request"]["clientRequestId"] == payload["clientRequestId"]:
                    if record["request"] != payload:
                        raise ApiProblem(
                            409, "IDEMPOTENCY_CONFLICT", "该请求标识已用于另一批量任务"
                        )
                    return self._snapshot(record)
            source = payload["source"]
            if source["kind"] == "graph":
                batch = self._graph.plans(
                    {"schemaVersion": 1, "targetNodeIds": source["targetNodeIds"]}
                )
                if batch["graphRevision"] != source["revision"]:
                    raise ApiProblem(
                        409,
                        "RESULT_GRAPH_REVISION_CONFLICT",
                        "结果图已变化，请重新生成计划",
                    )
                plans = batch["plans"]
                if not batch["valid"]:
                    raise ApiProblem(
                        400, "INVALID_ODB_BATCH_PLAN", "；".join(batch["issues"])
                    )
            else:
                expected = source["expectedPlan"]
                try:
                    plan = build_restart_result_plan(
                        {
                            "schemaVersion": 1,
                            "itemId": expected["targetItemId"],
                            "outputDirectory": str(
                                Path(expected["finalOutputOdb"]).parent
                            ),
                        },
                        joblist_path=self._joblist_path,
                    )
                except (KeyError, TypeError) as error:
                    raise ApiProblem(
                        400, "INVALID_ODB_BATCH_PLAN", "重启动计划不完整"
                    ) from error
                if plan != expected:
                    raise ApiProblem(
                        409, "RESTART_PLAN_CHANGED", "重启动计划已变化，请重新生成计划"
                    )
                plans = [plan]
            try:
                stages, targets, sources = _stages(plans)
                identities = {path: _source_identity(path) for path in sources}
            except (OSError, ValueError) as error:
                raise ApiProblem(400, "INVALID_ODB_BATCH_PLAN", str(error)) from error
            operation_id = uuid4().hex
            item = {
                "schemaVersion": 1,
                "kind": "odb.result_batch",
                "operationId": operation_id,
                "clientRequestId": payload["clientRequestId"],
                "createdAt": utc_now_text(),
                "updatedAt": utc_now_text(),
                "version": 1,
                "status": "queued",
                "phase": "等待批量执行",
                "error": None,
                "plans": plans,
                "stages": stages,
                "targets": targets,
                "options": deepcopy(payload["options"]),
            }
            record = {
                "schemaVersion": 1,
                "request": deepcopy(payload),
                "sources": identities,
                "snapshot": item,
            }
            self._save(
                record
            )  # No child can start before the complete immutable plan is durable.
            self._records[operation_id] = record
            self._stops[operation_id] = threading.Event()
            self._submit(record)
            return self._snapshot(record)

    def _submit(self, record):
        try:
            self._executor.submit(self._run, record)
        except RuntimeError:
            item = record["snapshot"]
            item.update(status="suspended", phase="调度器未启动；可稍后继续")
            self._save(record)

    def _record(self, operation_id):
        self._require_storage()
        if operation_id not in self._records:
            raise ApiProblem(404, "ODB_BATCH_NOT_FOUND", "找不到批量任务")
        return self._records[operation_id]

    def get(self, operation_id):
        with self._lock:
            return self._snapshot(self._record(operation_id))

    def list_snapshots(self, *, active_only=False):
        with self._lock:
            self._require_storage()
            return [
                self._snapshot(r)
                for r in reversed(list(self._records.values()))
                if not active_only or r["snapshot"]["status"] in ACTIVE
            ]

    def resume(self, operation_id):
        with self._lock:
            record = self._record(operation_id)
            item = record["snapshot"]
            if self._closed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在关闭")
            if item["status"] in ACTIVE:  # Idempotent repeated resume.
                return self._snapshot(record)
            if item["status"] != "suspended":
                raise ApiProblem(
                    409, "ODB_BATCH_NOT_RESUMABLE", "只有后台重启后暂停的任务可以继续"
                )
            item.update(status="queued", phase="正在检查来源和已完成结果", error=None)
            self._stops[operation_id].clear()
            self._save(record)
            self._submit(record)
            return self._snapshot(record)

    def cancel(self, operation_id):
        with self._lock:
            record = self._record(operation_id)
            item = record["snapshot"]
            if item["status"] not in TERMINAL:
                self._stops[operation_id].set()
                item.update(
                    status="cancelled"
                    if item["status"] == "suspended"
                    else "cancelling",
                    phase="已请求停止；保留已发布结果",
                )
                self._save(record)
            return self._snapshot(record)

    def _run(self, record):
        item = record["snapshot"]
        stopped = self._stops[item["operationId"]]
        child = None
        try:
            with self._lock:
                if stopped.is_set():
                    raise InterruptedError("批量任务已停止")
                item.update(status="running", phase="检查来源和已完成结果")
                self._save(record)
            self._check_sources(record)
            for stage in item["stages"]:
                if stopped.is_set():
                    raise InterruptedError("批量任务已停止")
                if stage["result"] is not None:
                    for path, expected in stage["identity"].items():
                        if _identity(path, stopped) != expected:
                            raise ValueError(
                                f"已完成结果发生变化，不能继续复用：{path}"
                            )
                    continue
                self._check_sources(record)
                parent = (
                    item["stages"][stage["parent"]]
                    if stage["parent"] is not None
                    else None
                )
                if parent is not None:
                    for path, expected in parent["identity"].items():
                        if _stat(path) != expected["stat"]:
                            raise ValueError(f"前置结果发生变化：{path}")
                request = OdbMergeOperationRequest.from_payload(
                    {
                        "schemaVersion": 1,
                        "clientRequestId": f"batch:{item['operationId']}:{stage['index']}",
                        "originalOdb": parent["result"]["outputOdb"]
                        if parent
                        else stage["originalOdb"],
                        "restartOdb": stage["restartOdb"],
                        "outputOdb": stage["outputOdb"],
                        **item["options"],
                        "conflictPolicy": "auto_number",
                    }
                )
                with self._lock:
                    if stopped.is_set():
                        raise InterruptedError("批量任务已停止")
                    # Checkpoint the intent before create. The same child ID is reused even
                    # if a crash happens before childOperationId can be recorded here.
                    item["phase"] = (
                        f"合并阶段 {stage['index'] + 1}/{len(item['stages'])} · {stage['jobName']}"
                    )
                    if stage["submitted"]:
                        child = self._merge.find_request(
                            request.client_request_id, signature=request.signature
                        )
                        if child is None or (
                            stage["childOperationId"] is not None
                            and stage["childOperationId"] != child["operationId"]
                        ):
                            raise ValueError(
                                "已提交阶段的合并记录缺失，执行情况不明；请核对，不会自动重跑。"
                            )
                    else:
                        stage["submitted"] = True
                        self._save(record)
                        child = self._merge.create(request)
                    stage["childOperationId"] = child["operationId"]
                    self._save(record)
                while child["status"] in ACTIVE | {"starting"}:
                    if stopped.wait(0.2):
                        self._merge.cancel(child["operationId"])
                        # Wait for actual cleanup before declaring the batch stopped.
                        threading.Event().wait(0.1)
                    child = self._merge.get(child["operationId"])
                if child.get("persistenceWarning"):
                    raise ValueError(child["persistenceWarning"])
                if child["status"] != "succeeded":
                    if child["status"] == "cancelled":
                        raise InterruptedError("当前合并阶段已取消，后续阶段未启动")
                    raise ValueError(
                        (child.get("error") or {}).get(
                            "message", "合并阶段未成功；后续阶段未启动"
                        )
                    )
                result = child["result"]
                if not result.get("validationReport"):
                    raise ValueError("当前阶段没有内容校验报告，不能作为完整结果复用")
                # A published result remains published even if Stop arrives during hashing.
                # The child ID is durable; a recovery can check it without replaying it.
                identities = {
                    p: _identity(p, stopped)
                    for p in (result["outputOdb"], result["validationReport"])
                }
                with self._lock:
                    stage.update(
                        result=deepcopy(result),
                        identity=identities,
                        message=child["progress"]["phase"],
                    )
                    self._save(record)
            with self._lock:
                if stopped.is_set():
                    raise InterruptedError("批量任务已停止，已完成结果保留")
                item.update(status="succeeded", phase="全部完整结果已生成并校验")
                self._save(record)
        except Exception as error:  # noqa: BLE001 - worker failures must produce a durable terminal state.
            if child and child["status"] in ACTIVE | {"starting"}:
                self._merge.cancel(child["operationId"])
            with self._lock:
                item.update(
                    status="cancelled"
                    if isinstance(error, InterruptedError)
                    else "failed",
                    phase=str(error),
                    error={
                        "code": "ODB_BATCH_CANCELLED"
                        if isinstance(error, InterruptedError)
                        else "ODB_BATCH_FAILED",
                        "message": str(error),
                    },
                )
                if not self._storage_error:
                    self._save(record)

    @staticmethod
    def _check_sources(record):
        for path, expected in record["sources"].items():
            if _source_identity(path) != expected:
                raise ValueError(f"源文件发生变化，已停止后续合并：{path}")

    def _snapshot(self, record):
        item = deepcopy(record["snapshot"])
        item["totalSteps"] = len(item["stages"])
        item["completedSteps"] = sum(s["result"] is not None for s in item["stages"])
        item["results"] = [
            {
                "targetJobName": target["targetJobName"],
                "outputOdb": item["stages"][target["stageIndex"]]["result"][
                    "outputOdb"
                ],
            }
            for target in item["targets"]
            if item["stages"][target["stageIndex"]]["result"] is not None
        ]
        item["warnings"] = list(
            dict.fromkeys(
                s["message"]
                for s in item["stages"]
                if s["result"] is not None and "无结果帧" in s["message"]
            )
        )
        item["currentOperation"] = None
        for stage in reversed(item["stages"]):
            if stage["childOperationId"]:
                item["currentOperation"] = self._merge.find_request(
                    f"batch:{item['operationId']}:{stage['index']}"
                )
                break
        return item

    def prepare_shutdown(self, *, reserve=True):
        with self._lock:
            active = self.list_snapshots(active_only=True)
            safe = not active and not self._storage_error
            if safe and reserve:
                self._closed = True
            return {"schemaVersion": 1, "safeToStop": safe, "operations": active}

    def close(self):
        with self._lock:
            if self._disposed:
                return
            self._disposed = self._closed = True
            for stopped in self._stops.values():
                stopped.set()
        self._executor.shutdown(wait=True)
        if self._journal is not None:
            self._journal.close()
