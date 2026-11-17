"""Standard-library loopback HTTP server for the WinUI control plane."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .compatibility import (
    CANCELLING,
    QUEUED,
    RUNNING,
    STARTING,
    AbaqusCompatibilitySettings,
    CompatibilityOperationManager,
    CompatibilityRunner,
)
from .contracts import (
    API_VERSION,
    JSON_CONTENT_TYPE,
    SCHEMA_VERSION,
    ApiProblem,
    ControlPlaneDescriptor,
    OdbCompatibilityCheckRequest,
    OdbDiscoveryRequest,
    OdbDiscoveryResponse,
    json_bytes,
    new_trace_id,
    utc_now_text,
)
from .descriptor import remove_descriptor_if_owned, write_descriptor_atomic
from .discovery import discover_odb_files
from .events import EventStore
from .job_drafts import preview_local_job_draft
from .job_queue_commands import JobQueueService
from .local_queue_runtime import LocalJobRunner, LocalQueueRuntimeManager
from .odb_merge_drafts import preview_odb_merge_draft
from .odb_merge_operations import (
    OdbMergeOperationManager,
    OdbMergeOperationRequest,
    OdbMergeRunner,
)
from .odb_result_graphs import OdbResultGraphService
from .odb_upgrade_drafts import preview_odb_upgrade
from .odb_upgrade_operations import OdbUpgradeOperationManager
from .postprocessing import (
    PostprocessOperationManager,
    PostprocessRunRunner,
    PostprocessScanRequest,
    PostprocessScanRunner,
)
from .remote_jobs import RemoteJobOperationManager, RemoteJobRequest, preview_remote_job
from .remote_servers import RemoteManager, RemoteServerService
from .remote_transfers import RemoteTransferOperationManager, RemoteTransferRequest
from .resources import capture_local_resource
from .restart_chains import read_restart_chains
from .restart_result_plans import build_restart_result_plan
from .result_indexing import (
    ResultIndexBuilder,
    ResultIndexBuildRequest,
    ResultIndexOperationManager,
)
from .results import discover_result_scopes, list_result_records, preview_result

LOGGER = logging.getLogger(__name__)
LOOPBACK_HOST = "127.0.0.1"
MAX_REQUEST_BODY_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ControlPlaneContext:
    token: str
    instance_id: str
    started_at: str
    event_store: EventStore
    operation_manager: CompatibilityOperationManager
    result_index_manager: ResultIndexOperationManager
    odb_merge_manager: OdbMergeOperationManager
    odb_upgrade_manager: OdbUpgradeOperationManager
    postprocess_manager: PostprocessOperationManager
    job_queue_service: JobQueueService
    local_queue_runtime: LocalQueueRuntimeManager
    remote_server_service: RemoteServerService
    remote_transfer_manager: RemoteTransferOperationManager
    remote_job_manager: RemoteJobOperationManager
    odb_result_graph_service: OdbResultGraphService


class ControlPlaneHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        context: ControlPlaneContext,
    ) -> None:
        self.context = context
        super().__init__(server_address, ControlPlaneRequestHandler)


class ControlPlaneRequestHandler(BaseHTTPRequestHandler):
    """Serve the small version-one API without importing GUI frameworks."""

    protocol_version = "HTTP/1.1"
    server_version = "AbaqusToolsControlPlane/1"
    sys_version = ""

    @property
    def control_server(self) -> ControlPlaneHttpServer:
        return cast(ControlPlaneHttpServer, self.server)

    @property
    def context(self) -> ControlPlaneContext:
        return self.control_server.context

    def do_GET(self) -> None:
        trace_id = new_trace_id()
        try:
            self._require_authorization()
            target = urlsplit(self.path)
            if target.path == "/healthz":
                self._handle_health(trace_id)
                return
            if target.path == "/api/v1/events":
                self._handle_event_replay(target.query, trace_id)
                return
            if target.path == "/api/v1/operations":
                self._handle_list_operations(target.query, trace_id)
                return
            if target.path == "/api/v1/result-index-builds":
                self._handle_list_result_index_builds(target.query, trace_id)
                return
            if target.path == "/api/v1/odb-merge-operations":
                self._handle_list_odb_merge_operations(target.query, trace_id)
                return
            if target.path == "/api/v1/odb-postprocess-operations":
                self._handle_list_postprocess_operations(target.query, trace_id)
                return
            if target.path == "/api/v1/odb-upgrade-operations":
                active_only = self._parse_active_only(target.query, "ODB 升级任务")
                self._send_json(HTTPStatus.OK, {
                    "schemaVersion": SCHEMA_VERSION,
                    "operations": self.context.odb_upgrade_manager.list_snapshots(active_only=active_only),
                }, trace_id)
                return
            upgrade_id = self._upgrade_id_from_path(target.path)
            if upgrade_id is not None and not target.query:
                self._send_json(HTTPStatus.OK, self.context.odb_upgrade_manager.get(upgrade_id), trace_id)
                return
            if target.path == "/api/v1/local-resources":
                query = parse_qs(target.query)
                if set(query) - {"abaqusCommand"} or len(query.get("abaqusCommand", [])) > 1:
                    raise ApiProblem(400, "INVALID_QUERY", "无效的本机资源查询")
                command = query.get("abaqusCommand", [""])[0]
                self._send_json(HTTPStatus.OK, capture_local_resource(command), trace_id)
                return
            if target.path == "/api/v1/job-queues" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.job_queue_service.snapshot(),
                    trace_id,
                )
                return
            if target.path == "/api/v1/local-queue-runtime" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.local_queue_runtime.snapshot(),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-servers" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self._remote_servers_snapshot(),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-transfers":
                active_only = self._parse_active_only(target.query, "远端文件传输列表")
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "operations": self.context.remote_transfer_manager.list_snapshots(
                            active_only=active_only
                        ),
                        "eventCursor": self.context.event_store.cursor,
                    },
                    trace_id,
                )
                return
            transfer_id = self._remote_transfer_id_from_get_path(target.path)
            if transfer_id is not None and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.remote_transfer_manager.get(transfer_id),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-jobs":
                active_only = self._parse_active_only(target.query, "远端作业列表")
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "operations": self.context.remote_job_manager.list_snapshots(
                            active_only=active_only
                        ),
                        "eventCursor": self.context.event_store.cursor,
                    },
                    trace_id,
                )
                return
            remote_job_id = self._remote_job_id_from_get_path(target.path)
            if remote_job_id is not None and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.remote_job_manager.get(remote_job_id),
                    trace_id,
                )
                return
            if target.path == "/api/v1/restart-chains" and not target.query:
                self._send_json(HTTPStatus.OK, read_restart_chains(), trace_id)
                return
            if target.path == "/api/v1/odb-result-graph" and not target.query:
                self._send_json(HTTPStatus.OK, self.context.odb_result_graph_service.snapshot(), trace_id)
                return
            result_index_id = self._result_index_id_from_get_path(target.path)
            if result_index_id is not None and not target.query:
                self._handle_get_result_index_build(result_index_id, trace_id)
                return
            odb_merge_id = self._odb_merge_id_from_get_path(target.path)
            if odb_merge_id is not None and not target.query:
                self._handle_get_odb_merge_operation(odb_merge_id, trace_id)
                return
            postprocess_id = self._postprocess_id_from_get_path(target.path)
            if postprocess_id is not None and not target.query:
                self._handle_get_postprocess_operation(postprocess_id, trace_id)
                return
            operation_id = self._operation_id_from_get_path(target.path)
            if operation_id is not None and not target.query:
                self._handle_get_operation(operation_id, trace_id)
                return
            raise ApiProblem(404, "ENDPOINT_NOT_FOUND", "API 端点不存在")
        except ApiProblem as problem:
            self._send_problem(problem, trace_id)
        except BrokenPipeError, ConnectionResetError:
            return
        except Exception:
            LOGGER.exception("Unhandled GET request failure; trace_id=%s", trace_id)
            self._send_problem(
                ApiProblem(500, "INTERNAL_ERROR", "控制面发生未处理错误"),
                trace_id,
            )

    def do_POST(self) -> None:
        trace_id = new_trace_id()
        try:
            self._require_authorization()
            target = urlsplit(self.path)
            if target.path == "/api/v1/odb-discoveries" and not target.query:
                self._handle_odb_discovery(trace_id)
                return
            if target.path == "/api/v1/result-scopes" and not target.query:
                self._handle_result_scopes(trace_id)
                return
            if target.path == "/api/v1/result-records" and not target.query:
                self._handle_result_records(trace_id)
                return
            if target.path == "/api/v1/result-previews" and not target.query:
                self._handle_result_preview(trace_id)
                return
            if target.path == "/api/v1/local-job-draft-previews" and not target.query:
                self._handle_local_job_draft_preview(trace_id)
                return
            if target.path == "/api/v1/job-queue-commands" and not target.query:
                self._handle_job_queue_command(trace_id)
                return
            if target.path == "/api/v1/local-queue-controls" and not target.query:
                self._handle_local_queue_control(trace_id)
                return
            if target.path == "/api/v1/remote-server-commands" and not target.query:
                self._handle_remote_server_command(trace_id)
                return
            if target.path == "/api/v1/remote-file-listings" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.remote_server_service.browse(self._read_json_object()),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-job-previews" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    preview_remote_job(
                        self._read_json_object(),
                        self.context.remote_server_service,
                    ),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-transfers" and not target.query:
                request = RemoteTransferRequest.from_payload(self._read_json_object())
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.remote_transfer_manager.create(request),
                    trace_id,
                )
                return
            if target.path == "/api/v1/remote-jobs" and not target.query:
                request = RemoteJobRequest.from_payload(self._read_json_object())
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.remote_job_manager.create(request),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-merge-draft-previews" and not target.query:
                self._handle_odb_merge_draft_preview(trace_id)
                return
            if target.path == "/api/v1/odb-upgrade-previews" and not target.query:
                self._send_json(HTTPStatus.OK, preview_odb_upgrade(self._read_json_object()), trace_id)
                return
            if target.path == "/api/v1/odb-upgrade-operations" and not target.query:
                self._send_json(HTTPStatus.ACCEPTED,
                    self.context.odb_upgrade_manager.create(self._read_json_object()), trace_id)
                return
            if target.path == "/api/v1/odb-upgrade-shutdown-check" and not target.query:
                self._send_json(HTTPStatus.OK, self.context.odb_upgrade_manager.prepare_shutdown(), trace_id)
                return
            upgrade_id = self._upgrade_id_from_path(target.path, cancel=True)
            if upgrade_id is not None and not target.query:
                self._send_json(HTTPStatus.ACCEPTED, self.context.odb_upgrade_manager.cancel(upgrade_id), trace_id)
                return
            if target.path == "/api/v1/restart-result-plans" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    build_restart_result_plan(self._read_json_object()),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-result-graph-commands" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.odb_result_graph_service.command(self._read_json_object()),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-result-graph-plans" and not target.query:
                self._send_json(
                    HTTPStatus.OK,
                    self.context.odb_result_graph_service.plans(self._read_json_object()),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-merge-operations" and not target.query:
                self._handle_create_odb_merge_operation(trace_id)
                return
            if target.path == "/api/v1/odb-postprocess-scans" and not target.query:
                request = PostprocessScanRequest.from_payload(self._read_json_object())
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.postprocess_manager.create_scan(request),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-region-extractions" and not target.query:
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.postprocess_manager.create_region(self._read_json_object()),
                    trace_id,
                )
                return
            if target.path == "/api/v1/odb-postprocess-operations" and not target.query:
                request = self.context.postprocess_manager.parse_run_request(
                    self._read_json_object()
                )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.postprocess_manager.create_run(request),
                    trace_id,
                )
                return
            if target.path == "/api/v1/result-index-builds" and not target.query:
                self._handle_create_result_index_build(trace_id)
                return
            if target.path == "/api/v1/odb-compatibility-checks" and not target.query:
                self._handle_create_compatibility_check(trace_id)
                return
            operation_id = self._operation_id_from_cancel_path(target.path)
            if operation_id is not None and not target.query:
                self._handle_cancel_operation(operation_id, trace_id)
                return
            result_index_id = self._result_index_id_from_cancel_path(target.path)
            if result_index_id is not None and not target.query:
                self._handle_cancel_result_index_build(result_index_id, trace_id)
                return
            odb_merge_id = self._odb_merge_id_from_cancel_path(target.path)
            if odb_merge_id is not None and not target.query:
                self._handle_cancel_odb_merge_operation(odb_merge_id, trace_id)
                return
            postprocess_id = self._postprocess_id_from_cancel_path(target.path)
            if postprocess_id is not None and not target.query:
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.postprocess_manager.cancel(postprocess_id),
                    trace_id,
                )
                return
            transfer_id = self._remote_transfer_id_from_cancel_path(target.path)
            if transfer_id is not None and not target.query:
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.remote_transfer_manager.cancel(transfer_id),
                    trace_id,
                )
                return
            remote_job_id = self._remote_job_id_from_control_path(target.path)
            if remote_job_id is not None and not target.query:
                control_payload = self._read_json_object()
                if set(control_payload) != {"schemaVersion", "action"}:
                    raise ApiProblem(
                        400,
                        "INVALID_REMOTE_JOB_CONTROL",
                        "远端作业控制请求字段无效",
                    )
                if control_payload.get("schemaVersion") != SCHEMA_VERSION:
                    raise ApiProblem(
                        400,
                        "UNSUPPORTED_SCHEMA_VERSION",
                        "不支持该请求结构版本",
                    )
                action = control_payload.get("action")
                if not isinstance(action, str):
                    raise ApiProblem(
                        400,
                        "INVALID_REMOTE_JOB_CONTROL",
                        "action 必须是字符串",
                    )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    self.context.remote_job_manager.control(remote_job_id, action),
                    trace_id,
                )
                return
            raise ApiProblem(404, "ENDPOINT_NOT_FOUND", "API 端点不存在")
        except ApiProblem as problem:
            self._send_problem(problem, trace_id)
        except BrokenPipeError, ConnectionResetError:
            return
        except Exception:
            LOGGER.exception("Unhandled POST request failure; trace_id=%s", trace_id)
            self._send_problem(
                ApiProblem(500, "INTERNAL_ERROR", "控制面发生未处理错误"),
                trace_id,
            )

    def do_OPTIONS(self) -> None:
        trace_id = new_trace_id()
        try:
            self._require_authorization()
            self._send_problem(
                ApiProblem(405, "METHOD_NOT_ALLOWED", "不支持该 HTTP 方法"),
                trace_id,
                extra_headers={"Allow": "GET, POST"},
            )
        except ApiProblem as problem:
            self._send_problem(problem, trace_id)

    @staticmethod
    def _upgrade_id_from_path(path: str, *, cancel: bool = False) -> str | None:
        prefix = "/api/v1/odb-upgrade-operations/"
        if not path.startswith(prefix):
            return None
        tail = path[len(prefix):]
        if cancel:
            if not tail.endswith("/cancel"):
                return None
            tail = tail[:-len("/cancel")]
        return tail if tail and "/" not in tail else None

    def _require_authorization(self) -> None:
        value = self.headers.get("Authorization", "")
        scheme, separator, supplied_token = value.partition(" ")
        authorized = (
            bool(separator)
            and scheme.casefold() == "bearer"
            and bool(supplied_token)
            and supplied_token.isascii()
            and hmac.compare_digest(supplied_token, self.context.token)
        )
        if not authorized:
            raise ApiProblem(
                401,
                "UNAUTHORIZED",
                "缺少或无效的控制面访问令牌",
            )

    def _handle_health(self, trace_id: str) -> None:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "apiVersion": API_VERSION,
            "status": "ok",
            "capabilities": ["jobQueue.scanExternalJobs", "odb.resultGraph", "odb.upgrade.safe-v1", "odb.upgrade.history-v1"],
            "instanceId": self.context.instance_id,
            "pid": os.getpid(),
            "startedAt": self.context.started_at,
            "eventCursor": self.context.event_store.cursor,
        }
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_odb_discovery(self, trace_id: str) -> None:
        request_payload = self._read_json_object()
        request = OdbDiscoveryRequest.from_payload(request_payload)
        discovery_id = uuid4().hex
        self.context.event_store.append(
            aggregate_type="odbDiscovery",
            aggregate_id=discovery_id,
            kind="odb.discovery.started",
            version=1,
            payload={
                "root": request.root,
                "recursive": request.recursive,
            },
        )

        try:
            root, odbs, warnings = discover_odb_files(request)
        except ApiProblem as problem:
            self.context.event_store.append(
                aggregate_type="odbDiscovery",
                aggregate_id=discovery_id,
                kind="odb.discovery.failed",
                version=2,
                payload={
                    "code": problem.code,
                    "message": problem.message,
                },
            )
            raise

        completed = self.context.event_store.append(
            aggregate_type="odbDiscovery",
            aggregate_id=discovery_id,
            kind="odb.discovery.completed",
            version=2,
            payload={
                "root": str(root),
                "recursive": request.recursive,
                "count": len(odbs),
                "warningCount": len(warnings),
            },
        )
        response = OdbDiscoveryResponse(
            discovery_id=discovery_id,
            root=str(root),
            recursive=request.recursive,
            odbs=odbs,
            warnings=warnings,
            event_cursor=completed.sequence,
        )
        self._send_json(HTTPStatus.OK, response.as_payload(), trace_id)

    def _handle_result_scopes(self, trace_id: str) -> None:
        payload = discover_result_scopes(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_result_records(self, trace_id: str) -> None:
        payload = list_result_records(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_result_preview(self, trace_id: str) -> None:
        payload = preview_result(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_local_job_draft_preview(self, trace_id: str) -> None:
        payload = preview_local_job_draft(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_job_queue_command(self, trace_id: str) -> None:
        payload = self.context.job_queue_service.execute(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_local_queue_control(self, trace_id: str) -> None:
        payload = self.context.local_queue_runtime.control(self._read_json_object())
        self._send_json(HTTPStatus.ACCEPTED, payload, trace_id)

    def _handle_remote_server_command(self, trace_id: str) -> None:
        request_payload = self._read_json_object()
        if request_payload.get("action") in {"connect", "disconnect"}:
            active_jobs = self.context.remote_job_manager.list_snapshots(
                active_only=True
            )
            active_transfers = self.context.remote_transfer_manager.list_snapshots(
                active_only=True
            )
            if active_jobs or active_transfers:
                raise ApiProblem(
                    409,
                    "REMOTE_SESSION_BUSY",
                    "远端作业或文件传输仍在进行，不能切换或断开服务器",
                    details={
                        "activeJobs": len(active_jobs),
                        "activeTransfers": len(active_transfers),
                    },
                )
        self.context.remote_server_service.execute(request_payload)
        self._send_json(HTTPStatus.OK, self._remote_servers_snapshot(), trace_id)

    def _remote_servers_snapshot(self) -> dict[str, Any]:
        snapshot = self.context.remote_server_service.snapshot()
        connection = snapshot.get("connection")
        if not isinstance(connection, dict):
            return snapshot
        resource = connection.get("resource")
        if not isinstance(resource, dict):
            return snapshot
        jobs = self.context.remote_job_manager.list_snapshots()
        active = [
            job
            for job in jobs
            if job.get("status") in {QUEUED, STARTING, RUNNING, CANCELLING}
        ]
        resource["running_jobs"] = sum(
            job.get("status") in {STARTING, RUNNING, CANCELLING} for job in active
        )
        resource["waiting_jobs"] = sum(job.get("status") == QUEUED for job in active)
        resource["active_jobs"] = [
            str(job.get("request", {}).get("jobName") or "")
            for job in active
            if job.get("request", {}).get("jobName")
        ]
        return snapshot

    def _handle_odb_merge_draft_preview(self, trace_id: str) -> None:
        payload = preview_odb_merge_draft(self._read_json_object())
        self._send_json(HTTPStatus.OK, payload, trace_id)

    def _handle_create_odb_merge_operation(self, trace_id: str) -> None:
        request = OdbMergeOperationRequest.from_payload(self._read_json_object())
        snapshot = self.context.odb_merge_manager.create(request)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    def _handle_get_odb_merge_operation(
        self,
        operation_id: str,
        trace_id: str,
    ) -> None:
        snapshot = self.context.odb_merge_manager.get(operation_id)
        self._send_json(HTTPStatus.OK, snapshot, trace_id)

    def _handle_cancel_odb_merge_operation(
        self,
        operation_id: str,
        trace_id: str,
    ) -> None:
        snapshot = self.context.odb_merge_manager.cancel(operation_id)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    def _handle_list_odb_merge_operations(
        self,
        raw_query: str,
        trace_id: str,
    ) -> None:
        active_only = self._parse_active_only(raw_query, "ODB 合并操作列表")
        self._send_json(
            HTTPStatus.OK,
            {
                "schemaVersion": SCHEMA_VERSION,
                "operations": self.context.odb_merge_manager.list_snapshots(
                    active_only=active_only
                ),
                "eventCursor": self.context.event_store.cursor,
            },
            trace_id,
        )

    def _handle_get_postprocess_operation(
        self,
        operation_id: str,
        trace_id: str,
    ) -> None:
        self._send_json(
            HTTPStatus.OK,
            self.context.postprocess_manager.get(operation_id),
            trace_id,
        )

    def _handle_list_postprocess_operations(
        self,
        raw_query: str,
        trace_id: str,
    ) -> None:
        active_only = self._parse_active_only(raw_query, "ODB 后处理操作列表")
        self._send_json(
            HTTPStatus.OK,
            {
                "schemaVersion": SCHEMA_VERSION,
                "operations": self.context.postprocess_manager.list_snapshots(
                    active_only=active_only
                ),
                "eventCursor": self.context.event_store.cursor,
            },
            trace_id,
        )

    def _handle_create_result_index_build(self, trace_id: str) -> None:
        request = ResultIndexBuildRequest.from_payload(self._read_json_object())
        snapshot = self.context.result_index_manager.create(request)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    def _handle_get_result_index_build(
        self,
        operation_id: str,
        trace_id: str,
    ) -> None:
        snapshot = self.context.result_index_manager.get(operation_id)
        self._send_json(HTTPStatus.OK, snapshot, trace_id)

    def _handle_cancel_result_index_build(
        self,
        operation_id: str,
        trace_id: str,
    ) -> None:
        snapshot = self.context.result_index_manager.cancel(operation_id)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    def _handle_list_result_index_builds(self, raw_query: str, trace_id: str) -> None:
        active_only = self._parse_active_only(raw_query, "结果索引操作列表")
        self._send_json(
            HTTPStatus.OK,
            {
                "schemaVersion": SCHEMA_VERSION,
                "operations": self.context.result_index_manager.list_snapshots(
                    active_only=active_only
                ),
                "eventCursor": self.context.event_store.cursor,
            },
            trace_id,
        )

    def _handle_create_compatibility_check(self, trace_id: str) -> None:
        request_payload = self._read_json_object()
        request = OdbCompatibilityCheckRequest.from_payload(request_payload)
        snapshot = self.context.operation_manager.create(request)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    def _handle_get_operation(self, operation_id: str, trace_id: str) -> None:
        snapshot = self.context.operation_manager.get(operation_id)
        self._send_json(HTTPStatus.OK, snapshot, trace_id)

    def _handle_list_operations(self, raw_query: str, trace_id: str) -> None:
        active_only = self._parse_active_only(raw_query, "操作列表")
        operations = self.context.operation_manager.list_snapshots(
            active_only=active_only
        )
        self._send_json(
            HTTPStatus.OK,
            {
                "schemaVersion": SCHEMA_VERSION,
                "operations": operations,
                "eventCursor": self.context.event_store.cursor,
            },
            trace_id,
        )

    @staticmethod
    def _parse_active_only(raw_query: str, label: str) -> bool:
        query = parse_qs(raw_query, keep_blank_values=True)
        unknown_fields = sorted(set(query) - {"activeOnly"})
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_QUERY_FIELDS",
                f"{label}包含未知查询参数",
                details={"fields": unknown_fields},
            )
        values = query.get("activeOnly", ["false"])
        if len(values) != 1 or values[0] not in {"true", "false"}:
            raise ApiProblem(
                400,
                "INVALID_ACTIVE_ONLY",
                "activeOnly 必须是 true 或 false",
            )
        return values[0] == "true"

    def _handle_cancel_operation(self, operation_id: str, trace_id: str) -> None:
        snapshot = self.context.operation_manager.cancel(operation_id)
        self._send_json(HTTPStatus.ACCEPTED, snapshot, trace_id)

    @staticmethod
    def _operation_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/operations/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _operation_id_from_cancel_path(path: str) -> str | None:
        prefix = "/api/v1/operations/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _result_index_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/result-index-builds/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _result_index_id_from_cancel_path(path: str) -> str | None:
        prefix = "/api/v1/result-index-builds/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _odb_merge_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/odb-merge-operations/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _odb_merge_id_from_cancel_path(path: str) -> str | None:
        prefix = "/api/v1/odb-merge-operations/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _postprocess_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/odb-postprocess-operations/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _postprocess_id_from_cancel_path(path: str) -> str | None:
        prefix = "/api/v1/odb-postprocess-operations/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _remote_transfer_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/remote-transfers/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _remote_transfer_id_from_cancel_path(path: str) -> str | None:
        prefix = "/api/v1/remote-transfers/"
        suffix = "/cancel"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _remote_job_id_from_get_path(path: str) -> str | None:
        prefix = "/api/v1/remote-jobs/"
        if not path.startswith(prefix):
            return None
        operation_id = path[len(prefix) :]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    @staticmethod
    def _remote_job_id_from_control_path(path: str) -> str | None:
        prefix = "/api/v1/remote-jobs/"
        suffix = "/control"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        operation_id = path[len(prefix) : -len(suffix)]
        if not operation_id or "/" in operation_id:
            return None
        return operation_id

    def _handle_event_replay(self, raw_query: str, trace_id: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=True)
        unknown_fields = sorted(set(query) - {"after"})
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_QUERY_FIELDS",
                "事件查询包含不支持的字段",
                details={"fields": unknown_fields},
            )
        after_values = query.get("after")
        if after_values is None:
            header_cursor = self.headers.get("Last-Event-ID", "").strip()
            after_text = header_cursor or "0"
        elif len(after_values) == 1:
            after_text = after_values[0]
        else:
            raise ApiProblem(400, "INVALID_EVENT_CURSOR", "after 只能出现一次")
        try:
            after = int(after_text)
        except (TypeError, ValueError) as exc:
            raise ApiProblem(
                400,
                "INVALID_EVENT_CURSOR",
                "after 必须是非负整数",
            ) from exc
        if after < 0:
            raise ApiProblem(400, "INVALID_EVENT_CURSOR", "after 必须是非负整数")

        events, cursor = self.context.event_store.replay(after_sequence=after)
        chunks = ["retry: 1000\n\n"]
        for event in events:
            event_json = json.dumps(
                event.as_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            chunks.append(
                f"id: {event.sequence}\nevent: {event.kind}\ndata: {event_json}\n\n"
            )
        chunks.append(f": replay-complete cursor={cursor}\n\n")
        body = "".join(chunks).encode("utf-8")
        self._send_bytes(
            HTTPStatus.OK,
            body,
            "text/event-stream; charset=utf-8",
            trace_id,
            extra_headers={
                "Cache-Control": "no-cache, no-store",
                "X-Event-Cursor": str(cursor),
            },
        )

    def _read_json_object(self) -> dict[str, Any]:
        length_text = self.headers.get("Content-Length")
        if length_text is None:
            raise ApiProblem(
                411, "CONTENT_LENGTH_REQUIRED", "请求必须提供 Content-Length"
            )
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ApiProblem(
                400, "INVALID_CONTENT_LENGTH", "Content-Length 无效"
            ) from exc
        if length < 0:
            raise ApiProblem(400, "INVALID_CONTENT_LENGTH", "Content-Length 无效")
        if length > MAX_REQUEST_BODY_BYTES:
            raise ApiProblem(413, "REQUEST_TOO_LARGE", "请求正文超过大小限制")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ApiProblem(400, "INCOMPLETE_REQUEST_BODY", "请求正文不完整")
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiProblem(
                400, "INVALID_JSON", "请求正文不是有效的 UTF-8 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ApiProblem(400, "INVALID_JSON_OBJECT", "请求正文必须是 JSON 对象")
        return payload

    def _send_json(
        self,
        status: int | HTTPStatus,
        payload: dict[str, Any],
        trace_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._send_bytes(
            status,
            json_bytes(payload),
            JSON_CONTENT_TYPE,
            trace_id,
            extra_headers=extra_headers,
        )

    def _send_problem(
        self,
        problem: ApiProblem,
        trace_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = dict(extra_headers or {})
        if problem.status == HTTPStatus.UNAUTHORIZED:
            headers["WWW-Authenticate"] = "Bearer"
        self._send_json(
            problem.status,
            problem.as_payload(trace_id),
            trace_id,
            extra_headers=headers,
        )

    def _send_bytes(
        self,
        status: int | HTTPStatus,
        body: bytes,
        content_type: str,
        trace_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Trace-Id", trace_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info(
            "%s - %s",
            self.client_address[0],
            format_string % args,
        )


class ControlPlaneRuntime:
    """Own one loopback server and its atomically published descriptor."""

    def __init__(
        self,
        *,
        descriptor_path: str | Path,
        port: int = 0,
        token: str | None = None,
        launch_token: str = "",
        event_store: EventStore | None = None,
        compatibility_runner: CompatibilityRunner | None = None,
        compatibility_settings_provider: (
            Callable[[], AbaqusCompatibilitySettings] | None
        ) = None,
        result_index_builder: ResultIndexBuilder | None = None,
        odb_merge_runner: OdbMergeRunner | None = None,
        odb_upgrade_runner=None,
        odb_merge_command_provider: Callable[[], str] | None = None,
        postprocess_scan_runner: PostprocessScanRunner | None = None,
        postprocess_run_runner: PostprocessRunRunner | None = None,
        postprocess_settings_provider: (
            Callable[[], tuple[str, str, dict[str, Any]]] | None
        ) = None,
        joblist_path: str | Path | None = None,
        local_job_runner: LocalJobRunner | None = None,
        external_job_scanner=None,
        external_monitor_interval: float = 5.0,
        server_profiles_path: str | Path | None = None,
        odb_result_graph_path: str | Path | None = None,
        remote_manager: RemoteManager | None = None,
    ) -> None:
        if not 0 <= int(port) <= 65535:
            raise ValueError("port must be between 0 and 65535")
        supplied_token = token if token is not None else secrets.token_urlsafe(32)
        if not supplied_token:
            raise ValueError("token must not be empty")

        self.descriptor_path = Path(descriptor_path).expanduser().resolve()
        self.instance_id = uuid4().hex
        self.started_at = utc_now_text()
        self.token = supplied_token
        self.launch_token = str(launch_token).strip()
        self._close_lock = threading.Lock()
        self._closed = False
        operation_kwargs: dict[str, Any] = {}
        if compatibility_runner is not None:
            operation_kwargs["runner"] = compatibility_runner
        if compatibility_settings_provider is not None:
            operation_kwargs["settings_provider"] = compatibility_settings_provider
        event_history = event_store or EventStore()
        operation_manager = CompatibilityOperationManager(
            event_history,
            **operation_kwargs,
        )
        result_index_manager = ResultIndexOperationManager(
            event_history,
            **(
                {"builder": result_index_builder}
                if result_index_builder is not None
                else {}
            ),
        )
        odb_merge_kwargs: dict[str, Any] = {}
        if odb_merge_runner is not None:
            odb_merge_kwargs["runner"] = odb_merge_runner
        if odb_merge_command_provider is not None:
            odb_merge_kwargs["command_provider"] = odb_merge_command_provider
        odb_merge_manager = OdbMergeOperationManager(
            event_history,
            **odb_merge_kwargs,
        )
        odb_upgrade_manager = OdbUpgradeOperationManager(
            journal_path=self.descriptor_path.with_name('odb-upgrade-history.json'),
            event_store=event_history,
            **({"runner": odb_upgrade_runner} if odb_upgrade_runner is not None else {}),
        )
        postprocess_kwargs: dict[str, Any] = {}
        if postprocess_scan_runner is not None:
            postprocess_kwargs["scan_runner"] = postprocess_scan_runner
        if postprocess_run_runner is not None:
            postprocess_kwargs["run_runner"] = postprocess_run_runner
        if postprocess_settings_provider is not None:
            postprocess_kwargs["settings_provider"] = postprocess_settings_provider
        postprocess_manager = PostprocessOperationManager(
            event_history,
            **postprocess_kwargs,
        )
        job_queue_kwargs: dict[str, Any] = {
            "external_monitor_interval": external_monitor_interval,
        }
        if external_job_scanner is not None:
            job_queue_kwargs["external_job_scanner"] = external_job_scanner
        job_queue_service = JobQueueService(joblist_path, **job_queue_kwargs)
        local_queue_runtime = LocalQueueRuntimeManager(
            job_queue_service,
            event_history,
            **({"runner": local_job_runner} if local_job_runner is not None else {}),
        )
        remote_server_service = RemoteServerService(
            event_history,
            profiles_path=server_profiles_path,
            manager=remote_manager,
        )
        remote_transfer_manager = RemoteTransferOperationManager(
            event_history,
            remote_server_service,
        )
        remote_job_manager = RemoteJobOperationManager(
            event_history,
            remote_server_service,
        )
        context = ControlPlaneContext(
            token=self.token,
            instance_id=self.instance_id,
            started_at=self.started_at,
            event_store=event_history,
            operation_manager=operation_manager,
            result_index_manager=result_index_manager,
            odb_merge_manager=odb_merge_manager,
            odb_upgrade_manager=odb_upgrade_manager,
            postprocess_manager=postprocess_manager,
            job_queue_service=job_queue_service,
            local_queue_runtime=local_queue_runtime,
            remote_server_service=remote_server_service,
            remote_transfer_manager=remote_transfer_manager,
            remote_job_manager=remote_job_manager,
            odb_result_graph_service=OdbResultGraphService(odb_result_graph_path),
        )
        try:
            self.httpd = ControlPlaneHttpServer((LOOPBACK_HOST, int(port)), context)
        except BaseException:
            remote_job_manager.close()
            remote_transfer_manager.close()
            remote_server_service.close()
            local_queue_runtime.close()
            job_queue_service.close()
            postprocess_manager.close()
            operation_manager.close()
            result_index_manager.close()
            odb_merge_manager.close()
            odb_upgrade_manager.close()
            raise
        actual_host, actual_port = self.httpd.server_address[:2]
        self.host = str(actual_host)
        self.port = int(actual_port)
        self.base_url = f"http://{self.host}:{self.port}"
        descriptor = ControlPlaneDescriptor(
            instance_id=self.instance_id,
            pid=os.getpid(),
            host=self.host,
            port=self.port,
            base_url=self.base_url,
            token=self.token,
            started_at=self.started_at,
            launch_token=self.launch_token,
        )
        try:
            write_descriptor_atomic(self.descriptor_path, descriptor)
        except BaseException:
            self.httpd.server_close()
            remote_job_manager.close()
            remote_transfer_manager.close()
            remote_server_service.close()
            local_queue_runtime.close()
            job_queue_service.close()
            postprocess_manager.close()
            operation_manager.close()
            result_index_manager.close()
            odb_merge_manager.close()
            odb_upgrade_manager.close()
            raise

    @property
    def event_store(self) -> EventStore:
        return self.httpd.context.event_store

    @property
    def operation_manager(self) -> CompatibilityOperationManager:
        return self.httpd.context.operation_manager

    @property
    def result_index_manager(self) -> ResultIndexOperationManager:
        return self.httpd.context.result_index_manager

    @property
    def odb_merge_manager(self) -> OdbMergeOperationManager:
        return self.httpd.context.odb_merge_manager

    @property
    def odb_upgrade_manager(self) -> OdbUpgradeOperationManager:
        return self.httpd.context.odb_upgrade_manager

    @property
    def job_queue_service(self) -> JobQueueService:
        return self.httpd.context.job_queue_service

    @property
    def postprocess_manager(self) -> PostprocessOperationManager:
        return self.httpd.context.postprocess_manager

    @property
    def local_queue_runtime(self) -> LocalQueueRuntimeManager:
        return self.httpd.context.local_queue_runtime

    @property
    def remote_server_service(self) -> RemoteServerService:
        return self.httpd.context.remote_server_service

    @property
    def remote_transfer_manager(self) -> RemoteTransferOperationManager:
        return self.httpd.context.remote_transfer_manager

    @property
    def remote_job_manager(self) -> RemoteJobOperationManager:
        return self.httpd.context.remote_job_manager

    def serve_forever(self) -> None:
        try:
            self.httpd.serve_forever(poll_interval=0.2)
        finally:
            self.close()

    def shutdown(self) -> None:
        self.httpd.shutdown()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self.httpd.server_close()
            self.remote_job_manager.close()
            self.remote_transfer_manager.close()
            self.remote_server_service.close()
            self.local_queue_runtime.close()
            self.job_queue_service.close()
            self.postprocess_manager.close()
            self.operation_manager.close()
            self.result_index_manager.close()
            self.odb_merge_manager.close()
            self.odb_upgrade_manager.close()
            remove_descriptor_if_owned(self.descriptor_path, self.instance_id)


__all__ = [
    "LOOPBACK_HOST",
    "MAX_REQUEST_BODY_BYTES",
    "ControlPlaneContext",
    "ControlPlaneHttpServer",
    "ControlPlaneRequestHandler",
    "ControlPlaneRuntime",
]
