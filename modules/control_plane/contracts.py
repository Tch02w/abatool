"""Versioned JSON contracts shared by the local HTTP API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1
API_VERSION = "v1"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
MAX_COMPATIBILITY_PATHS = 256
MAX_CLIENT_REQUEST_ID_LENGTH = 128


def utc_now_text() -> str:
    """Return an RFC 3339 UTC timestamp with millisecond precision."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Serialize an API payload as compact UTF-8 while preserving user text."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class ApiProblem(Exception):
    """An expected request or service error suitable for an API response."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)
        self.retryable = bool(retryable)
        self.details = dict(details or {})

    def as_payload(self, trace_id: str) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "traceId": trace_id,
                "details": self.details,
            },
        }


@dataclass(frozen=True)
class OdbDiscoveryRequest:
    root: str
    recursive: bool = True
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> OdbDiscoveryRequest:
        allowed_fields = {"schemaVersion", "root", "recursive"}
        unknown_fields = sorted(set(payload) - allowed_fields)
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "请求包含 v1 协议不支持的字段",
                details={"fields": unknown_fields},
            )

        schema_version = payload.get("schemaVersion")
        if schema_version != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持该请求结构版本",
                details={
                    "received": schema_version,
                    "supported": [SCHEMA_VERSION],
                },
            )

        root = payload.get("root")
        if not isinstance(root, str) or not root.strip():
            raise ApiProblem(
                400,
                "INVALID_ROOT",
                "root 必须是非空路径字符串",
            )

        recursive = payload.get("recursive", True)
        if not isinstance(recursive, bool):
            raise ApiProblem(
                400,
                "INVALID_RECURSIVE",
                "recursive 必须是布尔值",
            )

        return cls(
            root=root.strip(),
            recursive=recursive,
            schema_version=SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class OdbCompatibilityCheckRequest:
    client_request_id: str
    root: str
    paths: tuple[str, ...]
    force_rescan: bool
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> OdbCompatibilityCheckRequest:
        allowed_fields = {
            "schemaVersion",
            "clientRequestId",
            "root",
            "paths",
            "forceRescan",
        }
        unknown_fields = sorted(set(payload) - allowed_fields)
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "请求包含 v1 协议不支持的字段",
                details={"fields": unknown_fields},
            )

        missing_fields = sorted(allowed_fields - set(payload))
        if missing_fields:
            raise ApiProblem(
                400,
                "MISSING_FIELDS",
                "兼容性检查请求缺少必填字段",
                details={"fields": missing_fields},
            )

        schema_version = payload.get("schemaVersion")
        if schema_version != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持该请求结构版本",
                details={
                    "received": schema_version,
                    "supported": [SCHEMA_VERSION],
                },
            )

        client_request_id = payload.get("clientRequestId")
        if not isinstance(client_request_id, str) or not client_request_id.strip():
            raise ApiProblem(
                400,
                "INVALID_CLIENT_REQUEST_ID",
                "clientRequestId 必须是非空字符串",
            )
        client_request_id = client_request_id.strip()
        if (
            len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH
            or any(ord(character) < 32 for character in client_request_id)
        ):
            raise ApiProblem(
                400,
                "INVALID_CLIENT_REQUEST_ID",
                "clientRequestId 长度或字符不符合 v1 约束",
                details={"maximumLength": MAX_CLIENT_REQUEST_ID_LENGTH},
            )

        root = payload.get("root")
        if not isinstance(root, str) or not root.strip():
            raise ApiProblem(
                400,
                "INVALID_ROOT",
                "root 必须是非空路径字符串",
            )

        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list):
            raise ApiProblem(
                400,
                "INVALID_PATHS",
                "paths 必须是路径字符串数组",
            )
        if not raw_paths:
            raise ApiProblem(
                400,
                "EMPTY_PATHS",
                "至少需要选择一个 ODB 文件",
            )
        if len(raw_paths) > MAX_COMPATIBILITY_PATHS:
            raise ApiProblem(
                400,
                "TOO_MANY_PATHS",
                "单次兼容性检查的 ODB 数量超过限制",
                details={"maximum": MAX_COMPATIBILITY_PATHS},
            )
        paths: list[str] = []
        for index, value in enumerate(raw_paths):
            if not isinstance(value, str) or not value.strip():
                raise ApiProblem(
                    400,
                    "INVALID_PATH",
                    "paths 中的每一项都必须是非空路径字符串",
                    details={"index": index},
                )
            paths.append(value.strip())

        force_rescan = payload.get("forceRescan")
        if not isinstance(force_rescan, bool):
            raise ApiProblem(
                400,
                "INVALID_FORCE_RESCAN",
                "forceRescan 必须是布尔值",
            )

        return cls(
            client_request_id=client_request_id,
            root=root.strip(),
            paths=tuple(paths),
            force_rescan=force_rescan,
            schema_version=SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class OdbFileDto:
    path: str
    relative_path: str
    name: str
    size_bytes: int
    modified_at: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relativePath": self.relative_path,
            "name": self.name,
            "sizeBytes": self.size_bytes,
            "modifiedAt": self.modified_at,
        }


@dataclass(frozen=True)
class OdbDiscoveryResponse:
    discovery_id: str
    root: str
    recursive: bool
    odbs: tuple[OdbFileDto, ...]
    warnings: tuple[str, ...] = ()
    event_cursor: int = 0

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "discoveryId": self.discovery_id,
            "root": self.root,
            "recursive": self.recursive,
            "odbs": [item.as_payload() for item in self.odbs],
            "count": len(self.odbs),
            "warnings": list(self.warnings),
            "eventCursor": self.event_cursor,
        }


@dataclass(frozen=True)
class EventDto:
    sequence: int
    event_id: str
    occurred_at: str
    aggregate_type: str
    aggregate_id: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    attempt_id: str = ""
    version: int = 1

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "sequence": self.sequence,
            "eventId": self.event_id,
            "occurredAt": self.occurred_at,
            "aggregateType": self.aggregate_type,
            "aggregateId": self.aggregate_id,
            "attemptId": self.attempt_id,
            "version": self.version,
            "kind": self.kind,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class ControlPlaneDescriptor:
    instance_id: str
    pid: int
    host: str
    port: int
    base_url: str
    token: str
    started_at: str
    launch_token: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "apiVersion": API_VERSION,
            "instanceId": self.instance_id,
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "baseUrl": self.base_url,
            "token": self.token,
            "startedAt": self.started_at,
            "launchToken": self.launch_token,
        }


def new_trace_id() -> str:
    return uuid4().hex


__all__ = [
    "API_VERSION",
    "JSON_CONTENT_TYPE",
    "MAX_CLIENT_REQUEST_ID_LENGTH",
    "MAX_COMPATIBILITY_PATHS",
    "SCHEMA_VERSION",
    "ApiProblem",
    "ControlPlaneDescriptor",
    "EventDto",
    "OdbCompatibilityCheckRequest",
    "OdbDiscoveryRequest",
    "OdbDiscoveryResponse",
    "OdbFileDto",
    "json_bytes",
    "new_trace_id",
    "utc_now_text",
]
