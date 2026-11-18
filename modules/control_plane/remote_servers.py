"""Qt-free server profile persistence and verified SSH session commands."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from modules.submitter.app_paths import APP_DATA_DIR
from modules.submitter.queue_store import atomic_write_json
from modules.submitter.remote_connection import (
    HostKeyConfirmationRequired,
    RemoteConnectionError,
    RemoteConnectionManager,
    ServerConnectionRequest,
    ServerCredentials,
    normalize_fingerprint,
)
from modules.submitter.remote_models import ServerProfileDraft

from .contracts import SCHEMA_VERSION, ApiProblem
from .events import EventStore
from .remote_job_journal import server_identity

SERVER_PROFILES_PATH = APP_DATA_DIR / "server_profiles.json"
AUTHENTICATION_MODES = frozenset({"用户名/密码", "SSH Agent", "SSH 私钥"})


class RemoteManager(Protocol):
    @property
    def connected_profile(self) -> ServerProfileDraft | None: ...

    def connect(self, request: ServerConnectionRequest) -> dict[str, Any]: ...

    def refresh(self) -> dict[str, Any]: ...

    def disconnect(self) -> str: ...

    def list_directory(self, remote_path: str = "") -> dict[str, Any]: ...

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        *,
        overwrite: bool = False,
        progress: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]: ...

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
        progress: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]: ...

    def execute_powershell(self, script: str, *, timeout: float = 30) -> str: ...

    def validate_remote_path(self, remote_path: str) -> str: ...


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApiProblem(400, "INVALID_REMOTE_FIELD", f"{name} 必须是对象")
    return value


def _text(
    payload: Mapping[str, Any],
    name: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str):
        raise ApiProblem(
            400,
            "INVALID_REMOTE_FIELD",
            f"{name} 必须是字符串",
            details={"field": name},
        )
    cleaned = value.strip()
    if required and not cleaned:
        raise ApiProblem(
            400,
            "MISSING_REMOTE_FIELD",
            f"{name} 不能为空",
            details={"field": name},
        )
    return cleaned


def _profile_from_payload(payload: object) -> ServerProfileDraft:
    value = _require_mapping(payload, "profile")
    allowed_fields = {
        "profileName",
        "host",
        "username",
        "authentication",
        "hostFingerprint",
        "abaqusCommand",
        "computeRoot",
        "allowedRoots",
        "port",
        "privateKeyPath",
    }
    unknown = sorted(set(value) - allowed_fields)
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "服务器配置包含未知字段",
            details={"fields": unknown},
        )
    port = value.get("port", 22)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ApiProblem(
            400,
            "INVALID_REMOTE_PORT",
            "服务器端口必须在 1–65535 之间",
        )
    authentication = _text(
        value,
        "authentication",
        default="用户名/密码",
    )
    if authentication not in AUTHENTICATION_MODES:
        raise ApiProblem(
            400,
            "INVALID_AUTHENTICATION_MODE",
            "不支持的服务器认证方式",
        )
    roots = value.get("allowedRoots", [])
    if not isinstance(roots, list) or any(not isinstance(root, str) for root in roots):
        raise ApiProblem(
            400,
            "INVALID_REMOTE_FIELD",
            "allowedRoots 必须是字符串数组",
        )
    allowed_roots = tuple(dict.fromkeys(root.strip() for root in roots if root.strip()))
    return ServerProfileDraft(
        profile_name=_text(value, "profileName", required=True),
        host=_text(value, "host", required=True),
        username=_text(value, "username", required=True),
        authentication=authentication,
        host_fingerprint=normalize_fingerprint(_text(value, "hostFingerprint")),
        abaqus_command=_text(value, "abaqusCommand", default="abaqus.bat")
        or "abaqus.bat",
        compute_root=_text(value, "computeRoot"),
        allowed_roots=allowed_roots,
        port=port,
        private_key_path=_text(value, "privateKeyPath"),
    )


def _profile_payload(profile: ServerProfileDraft) -> dict[str, Any]:
    return {
        "profileName": profile.profile_name,
        "host": profile.host,
        "username": profile.username,
        "authentication": profile.authentication,
        "hostFingerprint": profile.host_fingerprint,
        "abaqusCommand": profile.abaqus_command,
        "computeRoot": profile.compute_root,
        "allowedRoots": list(profile.allowed_roots),
        "port": profile.port,
        "privateKeyPath": profile.private_key_path,
    }


class RemoteServerService:
    """Own persisted non-secret profiles and one live verified SSH session."""

    def __init__(
        self,
        event_store: EventStore,
        profiles_path: str | Path | None = None,
        manager: RemoteManager | None = None,
    ) -> None:
        self._event_store = event_store
        self._profiles_path = Path(profiles_path or SERVER_PROFILES_PATH)
        self._manager = manager or RemoteConnectionManager()
        self._lock = threading.RLock()
        self._profiles, self._load_error = self._load_profiles()
        self._connection_status = "disconnected"
        self._connected_profile_name = ""
        self._pending_fingerprint = ""
        self._resource: dict[str, Any] | None = None
        self._last_error = ""

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        schema_version = payload.get("schemaVersion")
        if schema_version != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持的服务器命令架构版本",
            )
        action = _text(payload, "action", required=True)
        allowed = {
            "schemaVersion",
            "action",
            "profile",
            "profileName",
            "credentials",
            "confirmFingerprint",
            "saveProfile",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "服务器命令包含未知字段",
                details={"fields": unknown},
            )
        with self._lock:
            if action == "saveProfile":
                self._save_profile(_profile_from_payload(payload.get("profile")))
            elif action == "deleteProfile":
                self._delete_profile(_text(payload, "profileName", required=True))
            elif action == "connect":
                self._connect(payload)
            elif action == "refresh":
                self._refresh()
            elif action == "disconnect":
                self._disconnect()
            else:
                raise ApiProblem(
                    400,
                    "UNSUPPORTED_REMOTE_ACTION",
                    f"不支持的服务器操作：{action}",
                )
            return self._snapshot_locked()

    def browse(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持的远端目录请求架构版本",
            )
        unknown = sorted(set(payload) - {"schemaVersion", "path"})
        if unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "远端目录请求包含未知字段",
                details={"fields": unknown},
            )
        with self._lock:
            try:
                result = self._manager.list_directory(_text(payload, "path"))
            except RemoteConnectionError as exc:
                raise ApiProblem(502, "REMOTE_BROWSE_FAILED", str(exc)) from exc
        return {"schemaVersion": SCHEMA_VERSION, **result}

    def transfer_file(
        self,
        *,
        direction: str,
        source: str,
        destination: str,
        overwrite: bool,
        progress: Callable[[int, int], None],
        cancel_requested: Callable[[], bool],
        expected_profile: dict | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._verify_profile_locked(expected_profile)
            if direction == "upload":
                return self._manager.upload_file(
                    source,
                    destination,
                    overwrite=overwrite,
                    progress=progress,
                    cancel_requested=cancel_requested,
                )
            if direction == "download":
                return self._manager.download_file(
                    source,
                    destination,
                    overwrite=overwrite,
                    progress=progress,
                    cancel_requested=cancel_requested,
                )
        raise ApiProblem(400, "INVALID_TRANSFER_DIRECTION", "文件传输方向无效")

    def connected_profile(self, expected_profile: dict | None = None) -> ServerProfileDraft:
        with self._lock:
            if self._connection_status != "connected":
                raise RemoteConnectionError("连接不可用，请在计算资源中重新连接原服务器。")
            self._verify_profile_locked(expected_profile)
            profile = self._manager.connected_profile
            if profile is None:
                raise RemoteConnectionError("尚未连接服务器。")
            return profile

    def execute_powershell(self, script: str, *, timeout: float = 30, expected_profile: dict | None = None) -> str:
        with self._lock:
            self._verify_profile_locked(expected_profile)
            try:
                return self._manager.execute_powershell(script, timeout=timeout)
            except RemoteConnectionError as exc:
                self._connection_status = "error"
                self._resource = None
                self._last_error = str(exc)
                raise

    def validate_remote_path(self, remote_path: str, expected_profile: dict | None = None) -> str:
        with self._lock:
            self._verify_profile_locked(expected_profile)
            return self._manager.validate_remote_path(remote_path)

    def _verify_profile_locked(self, expected):
        if expected is not None and (self._connection_status != "connected" or self._manager.connected_profile is None
                or server_identity(self._manager.connected_profile) != expected):
            raise RemoteConnectionError("请重新连接本任务原服务器、指纹及计算目录；未向其他服务器发送命令。")

    def requested_identity(self, payload):
        with self._lock:
            profile = (_profile_from_payload(payload["profile"]) if payload.get("profile") is not None
                       else self._profiles.get(_text(payload, "profileName", required=True)))
            if profile is None:
                raise ApiProblem(404, "REMOTE_PROFILE_NOT_FOUND", "服务器配置不存在")
            identity = server_identity(profile)
            confirmed = normalize_fingerprint(_text(payload, "confirmFingerprint"))
            if confirmed:
                identity["fingerprint"] = confirmed
            return identity

    def close(self) -> None:
        with self._lock:
            try:
                self._manager.disconnect()
            finally:
                self._connection_status = "disconnected"
                self._connected_profile_name = ""
                self._resource = None

    def _connect(self, payload: Mapping[str, Any]) -> None:
        profile_payload = payload.get("profile")
        if profile_payload is None:
            profile_name = _text(payload, "profileName", required=True)
            profile = self._profiles.get(profile_name)
            if profile is None:
                raise ApiProblem(404, "REMOTE_PROFILE_NOT_FOUND", "服务器配置不存在")
        else:
            profile = _profile_from_payload(profile_payload)

        credentials_payload = _require_mapping(payload.get("credentials", {}), "credentials")
        credential_unknown = sorted(
            set(credentials_payload) - {"password", "privateKeyPassphrase"}
        )
        if credential_unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "认证信息包含未知字段",
                details={"fields": credential_unknown},
            )
        credentials = ServerCredentials(
            password=_text(credentials_payload, "password"),
            private_key_passphrase=_text(
                credentials_payload,
                "privateKeyPassphrase",
            ),
        )
        save_profile = payload.get("saveProfile", True)
        if not isinstance(save_profile, bool):
            raise ApiProblem(400, "INVALID_REMOTE_FIELD", "saveProfile 必须是布尔值")
        if save_profile and self._load_error:
            raise ApiProblem(
                409,
                "REMOTE_PROFILES_CORRUPT",
                "服务器配置文件损坏，已拒绝覆盖原文件",
                details={"message": self._load_error},
            )
        confirmed = normalize_fingerprint(_text(payload, "confirmFingerprint"))
        if confirmed:
            profile = ServerProfileDraft(
                **{
                    **profile.__dict__,
                    "host_fingerprint": confirmed,
                }
            )
        if self._connection_status == "connected":
            self._manager.disconnect()
        self._connection_status = "connecting"
        self._connected_profile_name = ""
        self._pending_fingerprint = ""
        self._last_error = ""
        try:
            resource = self._manager.connect(
                ServerConnectionRequest(profile=profile, credentials=credentials)
            )
        except HostKeyConfirmationRequired as exc:
            self._connection_status = "confirmationRequired"
            self._pending_fingerprint = exc.fingerprint
            self._resource = None
            return
        except RemoteConnectionError as exc:
            self._connection_status = "error"
            self._last_error = str(exc)
            self._resource = None
            raise ApiProblem(502, "REMOTE_CONNECTION_FAILED", str(exc)) from exc

        verified_profile = ServerProfileDraft(
            **{
                **profile.__dict__,
                "host_fingerprint": str(resource.get("host_fingerprint") or confirmed),
            }
        )
        if save_profile:
            self._save_profile(verified_profile)
        self._connection_status = "connected"
        self._connected_profile_name = verified_profile.profile_name
        self._pending_fingerprint = ""
        self._resource = resource
        self._event_store.append(
            aggregate_type="remoteServer",
            aggregate_id=verified_profile.profile_name,
            kind="remote.server.connected",
            version=1,
            payload={"host": verified_profile.host},
        )

    def _refresh(self) -> None:
        try:
            self._resource = self._manager.refresh()
        except RemoteConnectionError as exc:
            self._connection_status = "error"
            self._last_error = str(exc)
            raise ApiProblem(502, "REMOTE_REFRESH_FAILED", str(exc)) from exc
        self._connection_status = "connected"
        self._last_error = ""

    def _disconnect(self) -> None:
        profile_name = self._manager.disconnect()
        self._connection_status = "disconnected"
        self._connected_profile_name = ""
        self._pending_fingerprint = ""
        self._resource = None
        self._last_error = ""
        if profile_name:
            self._event_store.append(
                aggregate_type="remoteServer",
                aggregate_id=profile_name,
                kind="remote.server.disconnected",
                version=1,
                payload={},
            )

    def _save_profile(self, profile: ServerProfileDraft) -> None:
        if self._load_error:
            raise ApiProblem(
                409,
                "REMOTE_PROFILES_CORRUPT",
                "服务器配置文件损坏，已拒绝覆盖原文件",
                details={"message": self._load_error},
            )
        self._profiles[profile.profile_name] = profile
        self._persist_profiles()

    def _delete_profile(self, profile_name: str) -> None:
        if self._load_error:
            raise ApiProblem(
                409,
                "REMOTE_PROFILES_CORRUPT",
                "服务器配置文件损坏，已拒绝覆盖原文件",
                details={"message": self._load_error},
            )
        if profile_name == self._connected_profile_name:
            raise ApiProblem(409, "REMOTE_PROFILE_CONNECTED", "请先断开该服务器")
        if self._profiles.pop(profile_name, None) is None:
            raise ApiProblem(404, "REMOTE_PROFILE_NOT_FOUND", "服务器配置不存在")
        self._persist_profiles()

    def _load_profiles(self) -> tuple[dict[str, ServerProfileDraft], str]:
        try:
            payload = json.loads(self._profiles_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, ""
        except (OSError, json.JSONDecodeError) as exc:
            return {}, str(exc)
        if not isinstance(payload, dict) or not isinstance(payload.get("profiles", []), list):
            return {}, "服务器配置文件格式无效"
        profiles: dict[str, ServerProfileDraft] = {}
        try:
            for item in payload.get("profiles", []):
                profile = _profile_from_payload(item)
                profiles[profile.profile_name] = profile
        except ApiProblem as exc:
            return {}, exc.message
        return profiles, ""

    def _persist_profiles(self) -> None:
        atomic_write_json(
            self._profiles_path,
            {"profiles": [_profile_payload(profile) for profile in self._profiles.values()]},
        )

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "profiles": [
                _profile_payload(profile)
                for profile in sorted(
                    self._profiles.values(),
                    key=lambda item: item.profile_name.casefold(),
                )
            ],
            "profilesError": self._load_error,
            "connection": {
                "status": self._connection_status,
                "profileName": self._connected_profile_name,
                "pendingFingerprint": self._pending_fingerprint,
                "lastError": self._last_error,
                "resource": self._resource,
            },
            "eventCursor": self._event_store.cursor,
        }


__all__ = ["SERVER_PROFILES_PATH", "RemoteManager", "RemoteServerService"]
