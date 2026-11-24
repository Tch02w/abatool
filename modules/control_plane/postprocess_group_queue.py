"""Durable FIFO of comparison groups. Abaqus work stays in the postprocess manager."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from modules.postprocessor.cache import abaqus_cache_version, quick_odb_fingerprint
from modules.postprocessor.paths import APP_NAME
from modules.postprocessor.postprocess_core import count_render_pngs
from modules.postprocessor.postprocess_execution import safe_folder_name
from modules.postprocessor.result_assets import (
    GROUP_MEMBER_MANIFEST_NAME,
    INCOMPLETE_OUTPUT_MARKER,
    RESULT_LAYOUT_VERSION,
    numeric_asset_dir,
    numeric_asset_is_valid,
    resolve_group_member_asset,
)

from .contracts import ApiProblem, utc_now_text
from .operation_journal import OperationJournal
from .postprocessing import _client_request_id, _validate_fields

KIND = "odb.postprocess.group-queue"
ACTIVE = {"queued", "running", "cancelling"}
CHILD_TERMINAL = {"succeeded", "failed", "cancelled"}
TERMINAL = CHILD_TERMINAL | {"partial"}
GROUP_STATES = ACTIVE | CHILD_TERMINAL | {"skipped", "interrupted"}
ACTIONS = {"append", "update-pending", "skip-pending", "cancel-current", "clear-pending", "stop",
           "resume", "acknowledge-interrupted"}


def _conflict(message):
    return ApiProblem(409, "POSTPROCESS_QUEUE_CONFLICT", message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _key(path):
    return os.path.normcase(str(path))


def _results(outputs=(), roots=()):
    files = list({_key(p): p for p in outputs}.values())
    return {"outputs": files, "resultRoots": list({_key(p): p for p in roots}.values()), "outputCount": len(files)}


def _snapshot(record):
    item = copy.deepcopy(record["snapshot"])
    for group in item["groups"]:
        if group["status"] in ACTIVE | {"interrupted"}:
            group["run"] = copy.deepcopy(record["drafts"][group["groupId"]])
    return item


def _finish(item):
    states = {group["status"] for group in item["groups"]}
    if states == {"succeeded"}:
        status, phase = "succeeded", "全部分组已完成"
    elif any(group["result"]["outputs"] for group in item["groups"]):
        status, phase = "partial", "部分结果已发布，请查看各组状态"
    elif "failed" in states or "interrupted" in states:
        status, phase = "failed", "队列结束，没有可确认的结果"
    else:
        status, phase = "cancelled", "队列已取消或跳过"
    item.update(status=status, phase=phase, currentGroupId="")


def _validate_record(record):
    item = record["snapshot"]
    if (item["kind"] != KIND or item["status"] not in ACTIVE | TERMINAL | {"suspended"}
            or not re.fullmatch("[0-9a-f]{32}", item["operationId"]) or not Path(item["root"]).is_absolute()
            or item["schemaVersion"] != 1 or type(item["version"]) is not int or item["version"] < 1
            or not item["groups"] or not isinstance(record["commands"], dict)
            or not re.fullmatch("[0-9a-f]{64}", record["signature"])):
        raise ValueError("分组队列记录无效")
    ids = set()
    running = []
    for group in item["groups"]:
        gid = group["groupId"]
        if (gid in ids or not re.fullmatch("[0-9a-f]{32}", gid) or group["status"] not in GROUP_STATES
                or not group["members"] or not all(Path(p).is_relative_to(item["root"]) and ".." not in Path(p).parts
                                                  for p in group["members"])):
            raise ValueError("分组条目无效")
        draft = record["drafts"][gid]
        if (draft["root"] != item["root"] or draft["clientRequestId"] != "pgq:" + gid
                or len(draft["groups"]) != 1 or draft["groups"][0]["members"] != group["members"]
                or draft["groups"][0]["name"] != group["name"] or draft["groups"][0]["standalone"] != group["standalone"]
                or [job["path"] for job in draft["jobs"]] != group["members"]
                or set(record["sources"][gid]) != set(group["members"])):
            raise ValueError("分组快照与条目不一致")
        if not re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9]{6}_[0-9a-f]{8}", group["batchId"]):
            raise ValueError("分组发布时间标识无效")
        expected = dict(_output_paths(group, Path(member)) for member in group["members"])
        outputs = list(map(Path, group["result"]["outputs"]))
        if (any(p not in expected for p in outputs)
                or _results(map(str, outputs), (str(expected[p]) for p in outputs)) != group["result"]):
            raise ValueError("分组发布路径与批次或来源不一致")
        if group["status"] in {"running", "cancelling"} or (
                group["status"] == "interrupted" and not group.get("acknowledged", False)):
            running.append(gid)
        ids.add(gid)
    if running != ([item["currentGroupId"]] if item["currentGroupId"] else []):
        raise ValueError("分组队列活动条目不一致")
    if item["result"] != _results((p for g in item["groups"] for p in g["result"]["outputs"]),
                                   (p for g in item["groups"] for p in g["result"]["resultRoots"])):
        raise ValueError("队列与各组发布回执不一致")


def _pin(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, quick_odb_fingerprint(path)]


def _group_inputs(manager, payload):
    request = manager.parse_run_request(payload)
    plan = request.plan
    try:
        pins = {str(path): _pin(path) for path in plan.jobs}
    except (OSError, RuntimeError) as error:
        raise _conflict("无法读取所选 ODB") from error
    jobs = {_key(path): dict(raw, path=str(path)) for path, raw in zip(plan.jobs, payload["jobs"], strict=True)}
    inputs = {}
    for group, raw in zip(plan.groups, payload["groups"], strict=True):
        key = "odb:" + _key(group.members[0]) if group.standalone else "group:" + group.name.casefold()
        if key in inputs:
            raise ApiProblem(400, "DUPLICATE_POSTPROCESS_GROUP", "同一份请求中出现重复组")
        members = list(map(str, group.members))
        draft = dict(payload, root=str(plan.options.root), groups=[dict(raw, name=group.name, members=members)],
                     jobs=[jobs[_key(p)] for p in group.members])
        inputs[key] = (draft, {p: pins[p] for p in members})
    return str(plan.options.root), inputs


def _output_paths(group, source):
    # result_root_for_odb also creates the directory. Recovery is read-only.
    root = source.parent / f"{APP_NAME}_Results"
    folder = "未分组" if group["standalone"] else safe_folder_name(group["name"])
    output = root / folder / (group["batchId"] + "_01") / safe_folder_name(source.stem)
    return output, root


def _member_output(record, group, source):
    output, root = _output_paths(group, source)
    if output.resolve() != output or (output / INCOMPLETE_OUTPUT_MARKER).exists():
        return None
    manifest = output / GROUP_MEMBER_MANIFEST_NAME
    if not manifest.is_file():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    source_identity = record["sources"][group["groupId"]][str(source)]
    if _pin(source) != source_identity:
        raise ValueError("原 ODB 内容或修改时间已变化")
    fingerprint = source_identity[2]
    if (Path(data["odb_path"]) != source or data["kind"] != "comparison_group_member"
            or data["layout_version"] != RESULT_LAYOUT_VERSION or data["comparison_group"] != group["name"]
            or data["content_fingerprint"] != fingerprint):
        raise ValueError("已发布结果与原组或源 ODB 不一致")
    config_hash = data["numeric_config_hash"]
    expected = numeric_asset_dir(root, source, fingerprint, config_hash)
    asset = resolve_group_member_asset(output)
    if (not re.fullmatch("[0-9a-f]{64}", config_hash) or asset != expected or expected.resolve() != expected
            or not numeric_asset_is_valid(expected, content_fingerprint=fingerprint,
                                          numeric_config_hash=config_hash, abaqus_version=group["abaqusVersion"])):
        raise ValueError("原组引用的共享数值结果缺失或无效")
    allowed = {"frames", "frames_transparent", "animations", "contours", "contours_transparent"}
    for name in data["group_dependent_contents"]:
        child = output / name
        if name not in allowed or not child.is_dir() or child.resolve() != child:
            raise ValueError("原组声明的图像或动画目录无效")
    render = json.loads((output / "render_postprocess_manifest.json").read_text(encoding="utf-8"))
    for field, folders in (("white_png_count", ("frames", "contours")),
                           ("transparent_png_count", ("frames_transparent", "contours_transparent"))):
        if render[field] != count_render_pngs(output, folders):
            raise ValueError("原组发布的 PNG 文件数量与渲染回执不一致")
    for field in render["animations"]:
        gif = output / "animations" / (field + ".gif")
        if Path(field).name != field or not gif.is_file() or gif.resolve() != gif or not gif.stat().st_size:
            raise ValueError("原组发布的 GIF 不完整")
    return str(output), str(root)


def _outputs_on_disk(record, group):
    """Use the exact frozen attempt's directories; never adopt a different batch's artifacts."""
    paths, roots, errors = [], [], []
    for member in group["members"]:
        try:
            verified = _member_output(record, group, Path(member))
            if verified:
                paths.append(verified[0])
                roots.append(verified[1])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            errors.append(f"{Path(member).name}：{error}")
    return _results(paths, roots), errors


class PostprocessGroupQueueManager:
    def __init__(self, postprocess_manager, journal_path):
        self._children = postprocess_manager
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="postprocess-group-queue")
        self._records = {}
        self._futures = {}
        self._journal = None
        self._storage_error = ""
        self._closed = False
        self._reserved = False
        try:
            self._journal = OperationJournal(journal_path, table="postprocess_group_queues", validator=_validate_record)
            for record in self._journal.load():
                item = record["snapshot"]
                self._records[item["operationId"]] = record
                if item["status"] in ACTIVE:
                    for group in item["groups"]:
                        if group["status"] in {"running", "cancelling"}:
                            group["interruptedFrom"] = group["status"]
                            group["status"] = "interrupted"
                            group["message"] = "后台已重启，须核对原组输出"
                    item.update(status="suspended", phase="后台已重启，等待核对并继续")
                    self._save(record)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
            self._storage_error = str(error)

    def _available(self):
        if self._storage_error:
            raise ApiProblem(503, "POSTPROCESS_QUEUE_HISTORY_UNAVAILABLE", "队列记录不可用：" + self._storage_error)

    def _admit(self):
        self._available()
        if self._closed or self._reserved:
            raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭")

    def _save(self, record):
        item = record["snapshot"]
        item["version"] += 1
        item["updatedAt"] = utc_now_text()
        item["result"] = _results((p for g in item["groups"] for p in g["result"]["outputs"]),
                                  (p for g in item["groups"] for p in g["result"]["resultRoots"]))
        try:
            self._journal.save(record)
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
            self._storage_error = str(error)
            self._available()
        self._records[item["operationId"]] = record

    def _record(self, oid):
        self._available()
        if oid not in self._records:
            raise ApiProblem(404, "POSTPROCESS_QUEUE_NOT_FOUND", "找不到指定分组队列")
        return self._records[oid]

    def get(self, operation_id):
        with self._condition:
            return _snapshot(self._record(operation_id))

    def get_if_changed(self, operation_id, after_version):
        with self._condition:
            record = self._record(operation_id)
            if after_version == record["snapshot"]["version"]:
                return None
            return _snapshot(record)

    def list_snapshots(self, *, active_only=False):
        with self._condition:
            self._available()
            return [_snapshot(r) for r in reversed(list(self._records.values()))
                    if not active_only or r["snapshot"]["status"] in ACTIVE]

    def _existing(self, rid, signature):
        self._admit()
        for record in self._records.values():
            if record["snapshot"]["clientRequestId"] == rid:
                if record["signature"] != signature:
                    raise _conflict("请求编号已用于其他队列")
                return _snapshot(record)
        return None

    def create(self, payload):
        rid, signature = _client_request_id(payload), _digest(payload)
        with self._condition:
            existing = self._existing(rid, signature)
            if existing:
                return existing
        root, inputs = _group_inputs(self._children, payload)
        with self._condition:
            existing = self._existing(rid, signature)
            if existing:
                return existing
            if any(r["snapshot"]["status"] not in TERMINAL and _key(r["snapshot"]["root"]) == _key(root)
                   for r in self._records.values()):
                raise _conflict("此工作区已有执行中或待核对的队列，请在原队列追加")
            oid = uuid4().hex
            item = {
                "schemaVersion": 1, "operationId": oid, "kind": KIND, "clientRequestId": rid,
                "root": root, "status": "queued", "version": 0, "phase": "已入队",
                "currentGroupId": "", "groups": [], "result": _results(), "createdAt": utc_now_text(),
            }
            record = {"snapshot": item, "signature": signature, "commands": {}, "drafts": {}, "sources": {}}
            self._edit_groups(record, inputs, update=False)
            self._save(record)
            self._start(oid)
            return _snapshot(record)

    def _start(self, oid):
        future = self._executor.submit(self._run, oid)
        self._futures[oid] = future
        future.add_done_callback(lambda done: self._worker_done(oid, done))

    def _worker_done(self, oid, future):
        with self._condition:
            if self._futures.get(oid) is future:
                self._futures.pop(oid)
            if not future.cancelled() and future.exception() and not self._storage_error:
                record = copy.deepcopy(self._record(oid))
                item = record["snapshot"]
                for group in item["groups"]:
                    if group["groupId"] == item["currentGroupId"]:
                        group.update(interruptedFrom=group["status"], status="interrupted", message="调度异常，等待核对")
                item.update(status="suspended", phase=f"调度异常，等待核对：{future.exception()}")
                self._save(record)
            self._condition.notify_all()

    @staticmethod
    def _edit_groups(record, inputs, *, update):
        groups = record["snapshot"]["groups"]
        live = {g["groupKey"]: g for g in groups if g["status"] in ACTIVE}
        for key, (draft, pins) in inputs.items():
            raw = draft["groups"][0]
            if update:
                row = live.get(key)
                if row is None or row["status"] != "queued":
                    raise _conflict("只能更新仍在排队的对比组，请刷新")
                gid = row["groupId"]
                draft["forceRescan"] = record["drafts"][gid]["forceRescan"]
                row.update(name=raw["name"], members=raw["members"])
            elif key in live:
                continue
            else:
                gid = uuid4().hex
                row = {
                    "groupId": gid, "groupKey": key, "name": raw["name"], "members": raw["members"],
                    "standalone": raw["standalone"], "status": "queued", "childOperationId": "", "message": "等待执行",
                    "batchId": datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f_") + gid[:8], "result": _results(),
                }
                groups.append(row)
            record["drafts"][gid] = dict(draft, clientRequestId="pgq:" + gid)
            record["sources"][gid] = pins

    def command(self, operation_id, action, payload):
        if action not in ACTIONS:
            raise ApiProblem(400, "INVALID_POSTPROCESS_QUEUE_ACTION", "未知的队列操作")
        fields = {"schemaVersion", "clientRequestId", "expectedVersion"}
        if action in {"append", "update-pending"}:
            fields.add("run")
        if action in {"skip-pending", "cancel-current", "acknowledge-interrupted"}:
            fields.add("expectedGroupId")
        _validate_fields(payload, fields)
        rid, digest = _client_request_id(payload), _digest([action, payload])
        with self._condition:
            record, replay = self._command_record(operation_id, rid, digest, payload["expectedVersion"])
            if replay:
                return _snapshot(record)
            record = copy.deepcopy(record)
        self._apply_command(record, action, payload)
        with self._condition:
            latest, replay = self._command_record(operation_id, rid, digest, payload["expectedVersion"])
            if replay:
                return _snapshot(latest)
            record["commands"][rid] = digest
            self._save(record)
            if action == "resume":
                self._start(operation_id)
            self._condition.notify_all()
            return _snapshot(record)

    def _command_record(self, oid, rid, digest, version):
        self._admit()
        record = self._record(oid)
        if rid in record["commands"]:
            if record["commands"][rid] != digest:
                raise _conflict("命令编号已用于不同操作")
            return record, True
        if type(version) is not int or version != record["snapshot"]["version"]:
            raise _conflict("队列已变化，请刷新后重试")
        return record, False

    def _apply_command(self, record, action, payload):
        item = record["snapshot"]
        state = item["status"]
        if state in TERMINAL or (state == "cancelling" and action != "stop"):
            raise _conflict("此队列已结束或正在停止")
        if ((state == "suspended" and action not in {"stop", "resume", "acknowledge-interrupted"})
                or (action in {"resume", "acknowledge-interrupted"} and state != "suspended")):
            raise _conflict("挂起队列需要先核对并继续")
        if action in {"append", "update-pending"}:
            if not isinstance(payload["run"], dict):
                raise ApiProblem(400, "INVALID_POSTPROCESS_GROUP", "缺少有效的运行计划")
            root, inputs = _group_inputs(self._children, payload["run"])
            if _key(root) != _key(item["root"]):
                raise _conflict("不能向同一队列添加其他工程目录")
            self._edit_groups(record, inputs, update=action == "update-pending")
        elif action in {"cancel-current", "skip-pending"}:
            target = next((g for g in item["groups"] if g["groupId"] == payload["expectedGroupId"]), None)
            if target is None or target["status"] != ("running" if action == "cancel-current" else "queued"):
                raise _conflict("目标组的状态已改变，请刷新")
            if action == "cancel-current":
                target.update(status="cancelling", message="等待当前组安全结束")
            else:
                target.update(status="skipped", message="已跳过待运行组")
        elif action in {"clear-pending", "stop"}:
            self._clear(record, stop=action == "stop")
        elif action == "acknowledge-interrupted":
            gid = payload["expectedGroupId"]
            if not gid or gid != item["currentGroupId"]:
                raise _conflict("待核对的中断组已变化")
            group = next(g for g in item["groups"] if g["groupId"] == gid)
            result, errors = _outputs_on_disk(record, group)
            if not errors and result["outputCount"] == len(group["members"]):
                state = "cancelled" if group.get("interruptedFrom") == "cancelling" else "succeeded"
                group.update(status=state, result=result, message="已人工确认原进程结束并核对全部成员产物")
            else:
                group.update(acknowledged=True, result=result, message="已人工确认原进程结束，保留中断记录"
                             + ("；" + "；".join(errors) if errors else ""))
            item.update(currentGroupId="", phase="已确认原进程结束，可继续待办或结束队列")
        else:
            self._resume(record)

    @staticmethod
    def _clear(record, *, stop):
        item = record["snapshot"]
        for group in item["groups"]:
            if group["status"] == "queued":
                group.update(status="cancelled", message="已从待办队列清除")
            elif stop and group["status"] == "running":
                group.update(status="cancelling", message="等待当前组安全结束")
        if stop:
            if item["status"] == "suspended" and item["currentGroupId"]:
                raise _conflict("后台重启前已有组开始执行，请先核实该组的实际状态")
            item.update(status="cancelling", phase="已请求停止整批")
        if not item["currentGroupId"] and not any(g["status"] == "queued" for g in item["groups"]):
            _finish(item)

    def cancel(self, operation_id):
        with self._condition:
            record = copy.deepcopy(self._record(operation_id))
            if record["snapshot"]["status"] in ACTIVE:
                self._clear(record, stop=True)
                self._save(record)
                self._condition.notify_all()
            return _snapshot(record)

    def _resume(self, record):
        item = record["snapshot"]
        for group in item["groups"]:
            if group["status"] == "queued":
                # Recheck each input at dispatch so one invalid ODB does not block other groups.
                continue
            outputs, errors = _outputs_on_disk(record, group)
            if group["status"] in {"interrupted", "succeeded"} and not group.get("acknowledged"):
                if outputs["outputCount"] != len(group["members"]):
                    errors.append("未能确认全部成员已发布")
                if errors and group["status"] == "interrupted":
                    raise _conflict(f"未能恢复 {group['name']}：{'；'.join(errors)}。不会再提交原组")
                if errors:
                    group.update(status="failed", message="；".join(errors))
                elif group.get("interruptedFrom") == "cancelling":
                    group.update(status="cancelled", message="已核对取消前发布的全部成员")
                else:
                    group.update(status="succeeded", message="已核对原批次发布的全部成员")
            group["result"] = outputs
        item.update(status="queued", currentGroupId="", phase="已核对，等待继续")

    @staticmethod
    def _verify_sources(record, group):
        if any(_pin(Path(p)) != record["sources"][group["groupId"]][p] for p in group["members"]):
            raise ValueError("原 ODB 内容或修改时间已变化")

    def _run(self, oid):
        while True:
            with self._condition:
                record = copy.deepcopy(self._record(oid))
                item = record["snapshot"]
                if item["status"] in TERMINAL | {"suspended"}:
                    return
                group = next((g for g in item["groups"] if g["status"] == "queued"), None)
                if group is None:
                    _finish(item)
                    self._save(record)
                    return
                gid = group["groupId"]
                draft, sources = record["drafts"][gid], record["sources"][gid]
            try:
                self._verify_sources(record, group)
                parsed = self._children.parse_run_request(draft)
                problem = ""
            except (ApiProblem, OSError, ValueError, RuntimeError) as error:
                problem = f"启动前校验未通过：{error}"
            with self._condition:
                record = copy.deepcopy(self._record(oid))
                item = record["snapshot"]
                group = next(g for g in item["groups"] if g["groupId"] == gid)
                if group["status"] != "queued" or draft != record["drafts"][gid] or sources != record["sources"][gid]:
                    continue
                if problem:
                    group.update(status="failed", message=problem)
                    self._save(record)
                    continue
                # Commit intent before crossing into the child manager. Recovery never
                # creates a fresh child for an intent recorded as running.
                item.update(status="running", phase="正在处理 " + group["name"], currentGroupId=gid)
                group.update(status="running", abaqusVersion=abaqus_cache_version(dict(parsed.plan.options.settings)),
                             message="已冻结当前参数")
                self._save(record)
                try:
                    request = replace(parsed, plan=replace(parsed.plan, batch_id=group["batchId"]))
                    child = self._children.create_run(request)
                except ApiProblem as error:
                    record = copy.deepcopy(record)
                    item = record["snapshot"]
                    next(g for g in item["groups"] if g["groupId"] == gid).update(status="failed", message=str(error))
                    item["currentGroupId"] = ""
                    self._save(record)
                    continue
                except (OSError, RuntimeError, ValueError) as error:
                    record = copy.deepcopy(record)
                    item = record["snapshot"]
                    group = next(g for g in item["groups"] if g["groupId"] == gid)
                    group.update(status="interrupted", interruptedFrom="running", message=f"子任务提交结果未确认：{error}")
                    item.update(status="suspended", phase="请核对子任务是否已执行")
                    self._save(record)
                    return
                child_id = child["operationId"]
                record = copy.deepcopy(record)
                next(g for g in record["snapshot"]["groups"] if g["groupId"] == gid)["childOperationId"] = child_id
                self._save(record)
            self._wait_for_child(oid, gid, child_id)

    def _wait_for_child(self, oid, gid, child_id):
        cancel_sent = False
        while True:
            with self._condition:
                record = self._record(oid)
                group = next(g for g in record["snapshot"]["groups"] if g["groupId"] == gid)
                cancel = group["status"] == "cancelling" and not cancel_sent
            try:
                child = self._children.cancel(child_id) if cancel else self._children.get(child_id)
            except (ApiProblem, OSError, RuntimeError) as error:
                with self._condition:
                    record = copy.deepcopy(self._record(oid))
                    item = record["snapshot"]
                    group = next(g for g in item["groups"] if g["groupId"] == gid)
                    group.update(interruptedFrom=group["status"], status="interrupted",
                                 message=f"未能核实原子任务状态：{error}")
                    item.update(status="suspended", phase="等待核实原子任务")
                    self._save(record)
                return
            cancel_sent |= cancel
            if child["status"] not in CHILD_TERMINAL:
                with self._condition:
                    self._condition.wait(timeout=.2)
                continue
            result = child.get("result") or {}
            state = child["status"]
            message = (child.get("error") or {}).get("message") or child["progress"]["phase"]
            published, errors = _outputs_on_disk(record, group)
            if errors:
                state, message = "failed", "；".join(errors)
            elif state == "succeeded" and (published["outputCount"] != len(group["members"])
                    or set(published["outputs"]) != set(result.get("outputs", []))):
                state, message = "failed", "子任务回执与已发布的实际成员目录不一致"
            with self._condition:
                record = copy.deepcopy(self._record(oid))
                group = next(g for g in record["snapshot"]["groups"] if g["groupId"] == gid)
                group.update(status=state, message=message, result=published)
                record["snapshot"]["currentGroupId"] = ""
                self._save(record)
                return

    def prepare_shutdown(self, *, reserve=True):
        with self._condition:
            if self._storage_error:
                return {"schemaVersion": 1, "safeToStop": False, "operations": [
                    {"kind": KIND, "operationId": "history", "status": "unavailable", "phase": "无法核实队列历史"}
                ]}
            active = self.list_snapshots(active_only=True)
            safe = not active and all(f.done() for f in self._futures.values())
            if safe and reserve:
                self._reserved = True
            return {"schemaVersion": 1, "safeToStop": safe, "operations": active}

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            if not self._storage_error:
                for r in self.list_snapshots(active_only=True):
                    self.cancel(r["operationId"])
            self._condition.notify_all()
        self._executor.shutdown(wait=True)
        if self._journal is not None:
            self._journal.close()
