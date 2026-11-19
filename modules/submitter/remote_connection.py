"""Qt-free Windows SSH connection adapter.

``RemoteConnectionService`` remains available through a lazy compatibility
export so the legacy PySide6 frontend keeps its existing import path without
making the native control plane import Qt.
"""

from __future__ import annotations

import base64
import gzip
import json
import ntpath
import os
import re
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4
from xml.etree import ElementTree

import paramiko

from .remote_models import ServerProfileDraft

if TYPE_CHECKING:
    from .remote_connection_qt import RemoteConnectionService


class RemoteConnectionError(RuntimeError):
    """A user-facing remote connection failure."""


class HostKeyConfirmationRequired(RemoteConnectionError):
    """Raised when a host key has not been trusted by the user yet."""

    def __init__(self, fingerprint: str) -> None:
        super().__init__(f"需要确认服务器主机指纹：{fingerprint}")
        self.fingerprint = fingerprint


class RemoteTransferCancelled(RemoteConnectionError):
    """Raised by a cooperative SFTP progress callback."""


@dataclass(frozen=True)
class ServerCredentials:
    """Ephemeral authentication material; never serialize this object."""

    password: str = ""
    private_key_passphrase: str = ""


@dataclass(frozen=True)
class ServerConnectionRequest:
    """One connection attempt, including ephemeral credentials."""

    profile: ServerProfileDraft
    credentials: ServerCredentials = ServerCredentials()

    def with_fingerprint(self, fingerprint: str) -> ServerConnectionRequest:
        return replace(
            self,
            profile=replace(self.profile, host_fingerprint=fingerprint),
        )


_CLIXML_CODEPOINT_PATTERN = re.compile(r"_x([0-9A-Fa-f]{4})_")


def _decode_clixml_codepoints(value: str) -> str:
    return _CLIXML_CODEPOINT_PATTERN.sub(
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def clean_remote_error_output(output: str) -> str:
    """Convert PowerShell CLIXML stderr into readable plain text."""
    normalized = str(output or "").strip()
    if not normalized:
        return ""
    if not normalized.startswith("#< CLIXML"):
        return _decode_clixml_codepoints(normalized)

    xml_text = normalized.partition("\n")[2].strip()
    messages: list[str] = []
    try:
        root = ElementTree.fromstring(xml_text)
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "S":
                continue
            if element.attrib.get("S") != "Error" or not element.text:
                continue
            messages.append(_decode_clixml_codepoints(element.text).strip())
    except ElementTree.ParseError:
        messages.append(_decode_clixml_codepoints(xml_text))

    readable_lines: list[str] = []
    for message in messages:
        for line in message.replace("\r\n", "\n").replace("\r", "\n").splitlines():
            stripped = line.strip()
            if stripped and (not readable_lines or stripped != readable_lines[-1]):
                readable_lines.append(stripped)
    return "\n".join(readable_lines) or "PowerShell 返回了无法解析的错误。"


def decode_remote_stream(payload: bytes) -> str:
    """Decode Windows SSH output without assuming the server code page."""
    if not payload:
        return ""
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        return payload.decode("utf-16")
    if len(payload) >= 4 and payload[1::2].count(0) >= len(payload) // 4:
        try:
            return payload.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def normalize_fingerprint(value: str) -> str:
    """Normalize OpenSSH SHA256 fingerprints for exact comparison."""
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("sha256:"):
        return f"SHA256:{normalized.split(':', 1)[1].rstrip('=')}"
    return normalized


def key_fingerprint(key: paramiko.PKey) -> str:
    """Return the modern OpenSSH-compatible SHA256 fingerprint."""
    fingerprint = getattr(key, "fingerprint", "")
    if fingerprint:
        return normalize_fingerprint(str(fingerprint))
    import hashlib

    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii")
    return f"SHA256:{digest.rstrip('=')}"


class _PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected_fingerprint: str) -> None:
        self.expected_fingerprint = normalize_fingerprint(expected_fingerprint)

    def missing_host_key(self, client, hostname: str, key: paramiko.PKey) -> None:
        del client, hostname
        actual = key_fingerprint(key)
        if not self.expected_fingerprint:
            raise HostKeyConfirmationRequired(actual)
        if actual != self.expected_fingerprint:
            raise RemoteConnectionError(
                "服务器主机指纹已变化，已拒绝连接。"
                f"\n已保存：{self.expected_fingerprint}"
                f"\n本次获取：{actual}"
            )


def _remote_replace_file_script(source: str, destination: str) -> str:
    """Windows fallback for servers without the POSIX rename extension."""
    paths = base64.b64encode(json.dumps({"source": source, "destination": destination},
                                       ensure_ascii=False).encode("utf-8")).decode("ascii")
    return rf"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$paths = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{paths}')) | ConvertFrom-Json
$sourcePath = [IO.Path]::GetFullPath($paths.source)
$destinationPath = [IO.Path]::GetFullPath($paths.destination)
if (-not [string]::Equals([IO.Path]::GetDirectoryName($sourcePath), [IO.Path]::GetDirectoryName($destinationPath), [StringComparison]::OrdinalIgnoreCase)) {{
    throw 'The upload temporary file must be in the destination directory.'
}}
if ([IO.File]::Exists($destinationPath)) {{
    [IO.File]::Replace($sourcePath, $destinationPath, [NullString]::Value)
}} else {{
    [IO.File]::Move($sourcePath, $destinationPath)
}}
""".strip()


def _powershell_resource_script(profile: ServerProfileDraft) -> str:
    config = {
        "compute_root": profile.compute_root,
        "allowed_roots": list(profile.allowed_roots),
        "abaqus_command": profile.abaqus_command or "abaqus.bat",
    }
    config_json = json.dumps(config, ensure_ascii=False).encode("utf-8")
    config_base64 = base64.b64encode(config_json).decode("ascii")
    script = rf"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$configJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{config_base64}'))
$config = $configJson | ConvertFrom-Json
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace AbaqusSubmitter
{{
    public static class NativeResourceMetrics
    {{
        [StructLayout(LayoutKind.Sequential)]
        public struct FileTime
        {{
            public uint Low;
            public uint High;
        }}

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
        public class MemoryStatusEx
        {{
            public uint Length = (uint)Marshal.SizeOf(typeof(MemoryStatusEx));
            public uint MemoryLoad;
            public ulong TotalPhysical;
            public ulong AvailablePhysical;
            public ulong TotalPageFile;
            public ulong AvailablePageFile;
            public ulong TotalVirtual;
            public ulong AvailableVirtual;
            public ulong AvailableExtendedVirtual;
        }}

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetSystemTimes(
            out FileTime idle,
            out FileTime kernel,
            out FileTime user
        );

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint GetActiveProcessorCount(ushort groupNumber);

        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GlobalMemoryStatusEx(
            [In, Out] MemoryStatusEx status
        );

        public static ulong ToUInt64(FileTime value)
        {{
            return ((ulong)value.High << 32) | value.Low;
        }}

        public static int LogicalProcessorCount()
        {{
            return (int)GetActiveProcessorCount(ushort.MaxValue);
        }}
    }}
}}
"@

function Read-CpuTimes {{
    $idle = New-Object 'AbaqusSubmitter.NativeResourceMetrics+FileTime'
    $kernel = New-Object 'AbaqusSubmitter.NativeResourceMetrics+FileTime'
    $user = New-Object 'AbaqusSubmitter.NativeResourceMetrics+FileTime'
    if (-not [AbaqusSubmitter.NativeResourceMetrics]::GetSystemTimes(
        [ref]$idle,
        [ref]$kernel,
        [ref]$user
    )) {{
        throw "GetSystemTimes failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }}
    return @(
        [AbaqusSubmitter.NativeResourceMetrics]::ToUInt64($idle),
        [AbaqusSubmitter.NativeResourceMetrics]::ToUInt64($kernel),
        [AbaqusSubmitter.NativeResourceMetrics]::ToUInt64($user)
    )
}}

$cpuBefore = @(Read-CpuTimes)
Start-Sleep -Milliseconds 250
$cpuAfter = @(Read-CpuTimes)
$idleDelta = [double]($cpuAfter[0] - $cpuBefore[0])
$systemDelta = [double](
    ($cpuAfter[1] - $cpuBefore[1]) + ($cpuAfter[2] - $cpuBefore[2])
)
$cpuLoad = if ($systemDelta -gt 0) {{
    [Math]::Max(
        0,
        [Math]::Min(100, 100 * ($systemDelta - $idleDelta) / $systemDelta)
    )
}} else {{
    0
}}
$cpuTotal = [AbaqusSubmitter.NativeResourceMetrics]::LogicalProcessorCount()
$cpuUsed = [int][Math]::Round($cpuTotal * $cpuLoad / 100)

$memory = New-Object 'AbaqusSubmitter.NativeResourceMetrics+MemoryStatusEx'
if (-not [AbaqusSubmitter.NativeResourceMetrics]::GlobalMemoryStatusEx($memory)) {{
    throw "GlobalMemoryStatusEx failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}}
$memoryTotal = [Math]::Round([double]$memory.TotalPhysical / 1GB, 2)
$memoryFree = [Math]::Round([double]$memory.AvailablePhysical / 1GB, 2)
$validRoots = @()
foreach ($root in @($config.allowed_roots)) {{
    if ($root -and (Test-Path -LiteralPath $root -PathType Container)) {{
        $validRoots += [string](Resolve-Path -LiteralPath $root).Path
    }}
}}
$computeRoot = [string]$config.compute_root
$computeRootExists = $false
if ($computeRoot) {{
    $computeRootExists = Test-Path -LiteralPath $computeRoot -PathType Container
    if ($computeRootExists) {{
        $computeRoot = [string](Resolve-Path -LiteralPath $computeRoot).Path
    }}
}}
$abaqusAvailable = [bool](Get-Command -Name ([string]$config.abaqus_command) -ErrorAction SilentlyContinue)
[ordered]@{{
    computer_name = [string]$env:COMPUTERNAME
    cpu_used = $cpuUsed
    cpu_total = $cpuTotal
    cpu_percent = [Math]::Round($cpuLoad, 1)
    memory_used_gb = [Math]::Round($memoryTotal - $memoryFree, 2)
    memory_total_gb = $memoryTotal
    compute_root = $computeRoot
    compute_root_exists = $computeRootExists
    allowed_roots = $validRoots
    abaqus_command_available = $abaqusAvailable
}} | ConvertTo-Json -Compress
"""
    return script


def _powershell_encoded_command(profile: ServerProfileDraft) -> str:
    return _powershell_encoded_script(_powershell_resource_script(profile))


def _powershell_encoded_script(script: str) -> str:
    """Encode a trusted application-owned script below cmd.exe length limits."""
    compressed = gzip.compress(script.encode("utf-8"), mtime=0)
    payload = base64.b64encode(compressed).decode("ascii")
    launcher = (
        f"$bytes=[Convert]::FromBase64String('{payload}');"
        "$memoryStream=[IO.MemoryStream]::new($bytes);"
        "$gzipStream=[IO.Compression.GzipStream]::new("
        "$memoryStream,[IO.Compression.CompressionMode]::Decompress);"
        "$reader=[IO.StreamReader]::new($gzipStream,[Text.Encoding]::UTF8);"
        "& ([ScriptBlock]::Create($reader.ReadToEnd()))"
    )
    encoded = base64.b64encode(launcher.encode("utf-16-le")).decode("ascii")
    return (
        "powershell.exe -NoLogo -NoProfile -NonInteractive "
        f"-ExecutionPolicy Bypass -OutputFormat Text -EncodedCommand {encoded}"
    )


def parse_resource_snapshot(
    output: str,
    *,
    profile: ServerProfileDraft,
    fingerprint: str,
) -> dict[str, Any]:
    """Validate the PowerShell JSON and map it to the existing UI contract."""
    try:
        payload = json.loads(output.strip())
    except (TypeError, json.JSONDecodeError) as exc:
        raise RemoteConnectionError("服务器资源信息不是有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise RemoteConnectionError("服务器资源信息格式无效。")
    return {
        "profile_name": profile.profile_name or profile.host,
        "host": profile.host,
        "connected": True,
        "computer_name": str(payload.get("computer_name") or ""),
        "cpu_used": int(payload.get("cpu_used") or 0),
        "cpu_total": int(payload.get("cpu_total") or 0),
        "cpu_percent": float(payload.get("cpu_percent") or 0),
        "memory_used_gb": float(payload.get("memory_used_gb") or 0),
        "memory_total_gb": float(payload.get("memory_total_gb") or 0),
        "running_jobs": 0,
        "waiting_jobs": 0,
        "active_jobs": (),
        "compute_root": str(payload.get("compute_root") or profile.compute_root),
        "compute_root_exists": bool(payload.get("compute_root_exists", False)),
        "allowed_roots": tuple(str(root) for root in payload.get("allowed_roots") or ()),
        "abaqus_command": profile.abaqus_command,
        "abaqus_command_available": bool(
            payload.get("abaqus_command_available", False)
        ),
        "host_fingerprint": fingerprint,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


class RemoteConnectionManager:
    """Own one verified Paramiko SSH session."""

    def __init__(self, client_factory=paramiko.SSHClient) -> None:
        self._client_factory = client_factory
        self._client: paramiko.SSHClient | None = None
        self._request: ServerConnectionRequest | None = None
        self._fingerprint = ""
        self._connecting_client: paramiko.SSHClient | None = None
        self._lock = threading.RLock()

    @property
    def connected_profile_name(self) -> str:
        request = self._request
        return request.profile.profile_name if request is not None else ""

    def connect(self, request: ServerConnectionRequest) -> dict[str, Any]:
        profile = request.profile
        if not profile.host.strip():
            raise RemoteConnectionError("请填写服务器主机名或 IP。")
        if not profile.username.strip():
            raise RemoteConnectionError("请填写服务器用户名。")

        connect_kwargs: dict[str, Any] = {
            "hostname": profile.host.strip(),
            "port": int(profile.port),
            "username": profile.username.strip(),
            "timeout": 10,
            "banner_timeout": 10,
            "auth_timeout": 15,
            "channel_timeout": 15,
            "look_for_keys": False,
            "allow_agent": False,
        }
        authentication = profile.authentication.strip()
        if authentication == "用户名/密码":
            if not request.credentials.password:
                raise RemoteConnectionError("请输入服务器密码。")
            connect_kwargs["password"] = request.credentials.password
        elif authentication == "SSH Agent":
            connect_kwargs["allow_agent"] = True
        else:
            if not profile.private_key_path.strip():
                raise RemoteConnectionError("请选择 SSH 私钥文件。")
            try:
                private_key = paramiko.PKey.from_path(
                    Path(profile.private_key_path),
                    password=request.credentials.private_key_passphrase or None,
                )
            except (OSError, paramiko.SSHException) as exc:
                raise RemoteConnectionError(f"无法读取 SSH 私钥：{exc}") from exc
            connect_kwargs["pkey"] = private_key

        client = self._client_factory()
        client.set_missing_host_key_policy(
            _PinnedHostKeyPolicy(profile.host_fingerprint)
        )
        with self._lock:
            self._connecting_client = client
        try:
            client.connect(**connect_kwargs)
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                raise RemoteConnectionError("SSH 连接建立后立即失效。")
            transport.set_keepalive(30)
            fingerprint = key_fingerprint(transport.get_remote_server_key())
            snapshot = self._read_snapshot(client, profile, fingerprint)
        except HostKeyConfirmationRequired:
            client.close()
            raise
        except RemoteConnectionError:
            client.close()
            raise
        except (OSError, paramiko.SSHException) as exc:
            client.close()
            raise RemoteConnectionError(f"SSH 连接失败：{exc}") from exc
        finally:
            with self._lock:
                if self._connecting_client is client:
                    self._connecting_client = None

        with self._lock:
            old_client = self._client
            self._client = client
            self._request = ServerConnectionRequest(
                request.with_fingerprint(fingerprint).profile
            )
            self._fingerprint = fingerprint
        if old_client is not None:
            old_client.close()
        return snapshot

    def refresh(self) -> dict[str, Any]:
        with self._lock:
            client = self._client
            request = self._request
            fingerprint = self._fingerprint
        if client is None or request is None:
            raise RemoteConnectionError("尚未连接服务器。")
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise RemoteConnectionError("SSH 连接已断开，请重新连接。")
        return self._read_snapshot(client, request.profile, fingerprint)

    def disconnect(self) -> str:
        with self._lock:
            client = self._client
            connecting_client = self._connecting_client
            request = self._request
            self._client = None
            self._connecting_client = None
            self._request = None
            self._fingerprint = ""
        if connecting_client is not None and connecting_client is not client:
            connecting_client.close()
        if client is not None:
            client.close()
        return request.profile.profile_name if request is not None else ""

    def list_directory(self, remote_path: str = "") -> dict[str, Any]:
        """List one configured, allowed Windows directory over SFTP."""
        with self._lock:
            client, profile = self._require_session_locked()
            requested = remote_path.strip() or self._default_remote_root(profile)
            normalized = self._require_allowed_remote_path(profile, requested)
            sftp_path = self._sftp_path(normalized)
            try:
                with client.open_sftp() as sftp:
                    attributes = sftp.listdir_attr(sftp_path)
            except (OSError, paramiko.SSHException) as exc:
                raise RemoteConnectionError(f"读取服务器目录失败：{exc}") from exc

        entries = []
        for item in sorted(
            attributes,
            key=lambda entry: (
                not stat.S_ISDIR(entry.st_mode or 0),
                entry.filename.casefold(),
            ),
        ):
            name = str(item.filename or "")
            if not name or name in {".", ".."}:
                continue
            item_path = ntpath.join(normalized, name)
            is_directory = stat.S_ISDIR(item.st_mode or 0)
            entries.append(
                {
                    "name": name,
                    "path": item_path,
                    "kind": "directory" if is_directory else "file",
                    "sizeBytes": 0 if is_directory else max(0, int(item.st_size or 0)),
                    "modifiedAt": datetime.fromtimestamp(
                        float(item.st_mtime or 0)
                    ).astimezone().isoformat(timespec="seconds")
                    if item.st_mtime
                    else "",
                }
            )
        parent = ntpath.dirname(normalized)
        if parent == normalized or not self._is_remote_path_allowed(profile, parent):
            parent = ""
        return {
            "profileName": profile.profile_name,
            "path": normalized,
            "parentPath": parent,
            "entries": entries,
        }

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        *,
        overwrite: bool = False,
        progress: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Upload one local file atomically inside configured remote roots."""
        source = Path(local_path).expanduser().resolve()
        if not source.is_file():
            raise RemoteConnectionError("待上传的本机文件不存在。")
        with self._lock:
            client, profile = self._require_session_locked()
            destination = self._require_allowed_remote_path(profile, remote_path)
            temporary = f"{self._sftp_path(destination)}.part-{uuid4().hex}"
            final_path = self._sftp_path(destination)
            try:
                with client.open_sftp() as sftp:
                    if self._sftp_exists(sftp, final_path) and not overwrite:
                        raise RemoteConnectionError("服务器目标文件已存在。")
                    callback = self._transfer_callback(progress, cancel_requested)
                    try:
                        sftp.put(str(source), temporary, callback=callback, confirm=True)
                        if cancel_requested is not None and cancel_requested():
                            raise RemoteTransferCancelled("文件上传已取消。")
                        self._sftp_rename(sftp, temporary, final_path, overwrite=overwrite)
                    except BaseException:
                        try:
                            sftp.remove(temporary)
                        except (OSError, paramiko.SSHException):
                            pass
                        raise
            except RemoteConnectionError:
                raise
            except (OSError, paramiko.SSHException) as exc:
                raise RemoteConnectionError(f"上传文件失败：{exc}") from exc
        return {
            "profileName": profile.profile_name,
            "direction": "upload",
            "source": str(source),
            "destination": destination,
            "sizeBytes": source.stat().st_size,
        }

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
        progress: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Download one allowed remote file with an atomic local replacement."""
        destination = Path(local_path).expanduser().resolve()
        if destination.exists() and not overwrite:
            raise RemoteConnectionError("本机目标文件已存在。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
        with self._lock:
            client, profile = self._require_session_locked()
            source = self._require_allowed_remote_path(profile, remote_path)
            try:
                with client.open_sftp() as sftp:
                    callback = self._transfer_callback(progress, cancel_requested)
                    try:
                        sftp.get(
                            self._sftp_path(source),
                            str(temporary),
                            callback=callback,
                        )
                        if cancel_requested is not None and cancel_requested():
                            raise RemoteTransferCancelled("文件下载已取消。")
                        # Windows _commit/fsync requires a writable descriptor.
                        with temporary.open("r+b") as stream:
                            os.fsync(stream.fileno())
                        if cancel_requested is not None and cancel_requested():
                            raise RemoteTransferCancelled("文件下载已取消。")
                        if overwrite:
                            os.replace(temporary, destination)
                        elif os.name == "nt":
                            # Unlike replace(), Windows rename refuses a target
                            # created by another writer after the initial check.
                            os.rename(temporary, destination)
                        else:
                            os.link(temporary, destination)
                            temporary.unlink()
                    finally:
                        temporary.unlink(missing_ok=True)
            except RemoteConnectionError:
                raise
            except (OSError, paramiko.SSHException) as exc:
                raise RemoteConnectionError(f"下载文件失败：{exc}") from exc
        return {
            "profileName": profile.profile_name,
            "direction": "download",
            "source": source,
            "destination": str(destination),
            "sizeBytes": destination.stat().st_size,
        }

    def execute_powershell(self, script: str, *, timeout: float = 30) -> str:
        """Execute one trusted application-owned PowerShell script over SSH."""
        if not script.strip():
            raise RemoteConnectionError("远端 PowerShell 脚本不能为空。")
        with self._lock:
            client, _profile = self._require_session_locked()
            try:
                _stdin, stdout, stderr = client.exec_command(
                    _powershell_encoded_script(script),
                    timeout=timeout,
                )
                exit_status = stdout.channel.recv_exit_status()
                output = decode_remote_stream(stdout.read())
                error_output = clean_remote_error_output(
                    decode_remote_stream(stderr.read())
                )
            except (OSError, paramiko.SSHException) as exc:
                raise RemoteConnectionError(f"执行服务器命令失败：{exc}") from exc
        if exit_status != 0:
            detail = error_output or f"PowerShell 退出码 {exit_status}"
            raise RemoteConnectionError(f"执行服务器命令失败：{detail}")
        return output

    @property
    def connected_profile(self) -> ServerProfileDraft | None:
        with self._lock:
            return self._request.profile if self._request is not None else None

    def validate_remote_path(self, remote_path: str) -> str:
        """Return a normalized path only when it is inside configured roots."""
        with self._lock:
            _client, profile = self._require_session_locked()
            return self._require_allowed_remote_path(profile, remote_path)

    def _require_session_locked(
        self,
    ) -> tuple[paramiko.SSHClient, ServerProfileDraft]:
        client = self._client
        request = self._request
        if client is None or request is None:
            raise RemoteConnectionError("尚未连接服务器。")
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise RemoteConnectionError("SSH 连接已断开，请重新连接。")
        return client, request.profile

    @staticmethod
    def _configured_remote_roots(profile: ServerProfileDraft) -> tuple[str, ...]:
        roots = [profile.compute_root, *profile.allowed_roots]
        return tuple(
            dict.fromkeys(
                ntpath.normpath(root.replace("/", "\\"))
                for root in roots
                if root.strip()
            )
        )

    @classmethod
    def _default_remote_root(cls, profile: ServerProfileDraft) -> str:
        roots = cls._configured_remote_roots(profile)
        if not roots:
            raise RemoteConnectionError("服务器配置没有允许访问的目录。")
        return roots[0]

    @classmethod
    def _is_remote_path_allowed(
        cls,
        profile: ServerProfileDraft,
        remote_path: str,
    ) -> bool:
        normalized = ntpath.normpath(remote_path.replace("/", "\\"))
        if not ntpath.isabs(normalized):
            return False
        for root in cls._configured_remote_roots(profile):
            try:
                if ntpath.commonpath([root, normalized]).casefold() == root.casefold():
                    return True
            except ValueError:
                continue
        return False

    @classmethod
    def _require_allowed_remote_path(
        cls,
        profile: ServerProfileDraft,
        remote_path: str,
    ) -> str:
        normalized = ntpath.normpath(remote_path.strip().replace("/", "\\"))
        if not cls._is_remote_path_allowed(profile, normalized):
            raise RemoteConnectionError("服务器路径不在配置允许的根目录内。")
        return normalized

    @staticmethod
    def _sftp_path(remote_path: str) -> str:
        return remote_path.replace("\\", "/")

    @staticmethod
    def _sftp_exists(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
        try:
            sftp.stat(remote_path)
        except OSError:
            return False
        return True

    def _sftp_rename(
        self,
        sftp: paramiko.SFTPClient,
        source: str,
        destination: str,
        *,
        overwrite: bool,
    ) -> None:
        if not overwrite:
            # Standard SFTP rename refuses an existing destination. POSIX rename
            # would silently overwrite a file created after the initial stat.
            sftp.rename(source, destination)
            return
        try:
            sftp.posix_rename(source, destination)
        except (AttributeError, OSError):
            # Windows OpenSSH may not implement the POSIX extension. Replace
            # using the verified Windows session, never remove the old target
            # first. A failed commit leaves its error visible to the caller.
            self.execute_powershell(_remote_replace_file_script(source, destination))

    @staticmethod
    def _transfer_callback(
        progress: Callable[[int, int], None] | None,
        cancel_requested: Callable[[], bool] | None,
    ) -> Callable[[int, int], None]:
        def callback(transferred: int, total: int) -> None:
            if cancel_requested is not None and cancel_requested():
                raise RemoteTransferCancelled("文件传输已取消。")
            if progress is not None:
                progress(max(0, int(transferred)), max(0, int(total)))

        return callback

    @staticmethod
    def _read_snapshot(
        client: paramiko.SSHClient,
        profile: ServerProfileDraft,
        fingerprint: str,
    ) -> dict[str, Any]:
        try:
            _stdin, stdout, stderr = client.exec_command(
                _powershell_encoded_command(profile),
                timeout=20,
            )
            exit_status = stdout.channel.recv_exit_status()
            output = decode_remote_stream(stdout.read())
            error_output = clean_remote_error_output(
                decode_remote_stream(stderr.read())
            )
        except (OSError, paramiko.SSHException) as exc:
            raise RemoteConnectionError(f"读取服务器资源失败：{exc}") from exc
        if exit_status != 0:
            detail = error_output or f"PowerShell 退出码 {exit_status}"
            raise RemoteConnectionError(f"读取服务器资源失败：{detail}")
        return parse_resource_snapshot(
            output,
            profile=profile,
            fingerprint=fingerprint,
        )


def __getattr__(name: str):
    """Load the legacy Qt service only when an old caller requests it."""
    if name == "RemoteConnectionService":
        from .remote_connection_qt import RemoteConnectionService

        return RemoteConnectionService
    raise AttributeError(name)


__all__ = [
    "HostKeyConfirmationRequired",
    "RemoteConnectionError",
    "RemoteConnectionManager",
    "RemoteConnectionService",
    "RemoteTransferCancelled",
    "ServerConnectionRequest",
    "ServerCredentials",
    "clean_remote_error_output",
    "decode_remote_stream",
    "key_fingerprint",
    "normalize_fingerprint",
    "parse_resource_snapshot",
]
