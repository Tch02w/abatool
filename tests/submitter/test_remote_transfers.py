"""File preservation and Windows publication checks without SSH credentials."""
from __future__ import annotations

import base64
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.control_plane.events import EventStore
from modules.control_plane.remote_transfers import RemoteTransferOperationManager, RemoteTransferRequest
from modules.submitter.remote_connection import (
    RemoteConnectionError, RemoteConnectionManager, RemoteTransferCancelled,
    ServerConnectionRequest, _remote_replace_file_script,
)
from modules.submitter.remote_models import ServerProfileDraft


class SftpFiles:
    def __init__(self):
        self.files = {}
        self.after_transfer = lambda: None
        self.reject_posix = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def stat(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_size=len(self.files[path]))

    def put(self, source, target, callback, confirm):
        self.files[target] = Path(source).read_bytes()
        callback(len(self.files[target]), len(self.files[target]))
        self.after_transfer()

    def get(self, source, target, callback):
        Path(target).write_bytes(self.files[source])
        callback(len(self.files[source]), len(self.files[source]))
        self.after_transfer()

    def remove(self, path):
        del self.files[path]

    def rename(self, source, target):
        if target in self.files:
            raise FileExistsError(target)
        self.files[target] = self.files.pop(source)

    def posix_rename(self, source, target):
        if self.reject_posix:
            raise OSError("Operation unsupported")
        self.files[target] = self.files.pop(source)


def connected(sftp):
    manager = RemoteConnectionManager()
    manager._client = SimpleNamespace(open_sftp=lambda: sftp,
        get_transport=lambda: SimpleNamespace(is_active=lambda: True))
    manager._request = ServerConnectionRequest(ServerProfileDraft(
        "test", "fixture", "fixture", "SSH Agent", "SHA256:fixture", "abaqus", r"D:\Test", ()))
    return manager


@pytest.mark.parametrize("contents", [b"", "中文 result\n".encode()])
def test_download_flushes_and_publishes_actual_file(tmp_path, contents):
    sftp = SftpFiles()
    sftp.files["D:/Test/result.txt"] = contents
    output = tmp_path / "下载 result.txt"
    result = connected(sftp).download_file(r"D:\Test\result.txt", str(output))
    assert output.read_bytes() == contents
    assert result["sizeBytes"] == len(contents)
    assert list(tmp_path.iterdir()) == [output]


def test_download_nonoverwrite_protects_target_created_during_transfer(tmp_path):
    sftp = SftpFiles()
    sftp.files["D:/Test/result.txt"] = b"new"
    output = tmp_path / "result.txt"
    sftp.after_transfer = lambda: output.write_bytes(b"concurrent writer")
    with pytest.raises(RemoteConnectionError):
        connected(sftp).download_file(r"D:\Test\result.txt", str(output))
    assert output.read_bytes() == b"concurrent writer"
    assert list(tmp_path.iterdir()) == [output]


def test_download_cancel_before_publish_preserves_old_output(tmp_path):
    sftp = SftpFiles()
    sftp.files["D:/Test/result.txt"] = b"new"
    output = tmp_path / "result.txt"
    output.write_bytes(b"old")
    cancel = threading.Event()
    sftp.after_transfer = cancel.set
    with pytest.raises(RemoteTransferCancelled):
        connected(sftp).download_file(r"D:\Test\result.txt", str(output), overwrite=True,
                                      cancel_requested=cancel.is_set)
    assert output.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [output]


def test_upload_nonoverwrite_protects_target_created_during_transfer(tmp_path):
    sftp = SftpFiles()
    source = tmp_path / "upload.txt"
    source.write_bytes(b"new")
    sftp.after_transfer = lambda: sftp.files.update({"D:/Test/result.txt": b"concurrent writer"})
    with pytest.raises(RemoteConnectionError):
        connected(sftp).upload_file(str(source), r"D:\Test\result.txt")
    assert sftp.files == {"D:/Test/result.txt": b"concurrent writer"}


def test_upload_failed_replace_does_not_delete_old_file(tmp_path, monkeypatch):
    sftp = SftpFiles()
    sftp.files["D:/Test/result.txt"] = b"old"
    sftp.reject_posix = True
    source = tmp_path / "upload.txt"
    source.write_bytes(b"new")
    manager = connected(sftp)
    def fail(script):
        raise RemoteConnectionError("injected publish failure")
    monkeypatch.setattr(manager, "execute_powershell", fail)
    with pytest.raises(RemoteConnectionError, match="injected"):
        manager.upload_file(str(source), r"D:\Test\result.txt", overwrite=True)
    assert sftp.files == {"D:/Test/result.txt": b"old"}


@pytest.mark.skipif(os.name != "nt", reason="Real Windows file replacement fallback")
@pytest.mark.parametrize("existing,locked", [(False, False), (True, False), (True, True)])
def test_windows_upload_commit_uses_literal_paths_and_keeps_locked_target(tmp_path, existing, locked):
    source = tmp_path / "中文 '$(literal) upload.part"
    target = tmp_path / "中文 '$(literal) result.txt"
    source.write_bytes(b"new")
    if existing:
        target.write_bytes(b"old")
    script = _remote_replace_file_script(str(source), str(target))
    if locked:
        quoted = str(target).replace("'", "''")
        script = (f"$lockedStream = [IO.File]::Open('{quoted}', 'Open', 'Read', 'None')\ntry {{\n"
                  + script + "\n} finally { $lockedStream.Dispose() }")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if locked:
        assert result.returncode != 0
        assert target.read_bytes() == b"old" and source.read_bytes() == b"new"
    else:
        assert result.returncode == 0, result.stderr
        assert target.read_bytes() == b"new" and not source.exists()


@pytest.mark.parametrize("published", [False, True])
def test_transfer_cancel_reports_the_actual_publication_state(tmp_path, published):
    reached, release = threading.Event(), threading.Event()
    output = tmp_path / "result.txt"
    output.write_bytes(b"old")
    class Service:
        def transfer_file(self, **kwargs):
            if published:
                output.write_bytes(b"new")
            reached.set()
            assert release.wait(5)
            if not published and kwargs["cancel_requested"]():
                raise RemoteTransferCancelled("cancelled before commit")
            return {"sizeBytes": 3, "destination": str(output)}
    manager = RemoteTransferOperationManager(EventStore(), Service())
    try:
        initial = manager.create(RemoteTransferRequest("late-cancel", "download", "remote", str(output), True))
        assert reached.wait(5)
        manager.cancel(initial["operationId"])
        release.set()
        deadline = time.monotonic() + 5
        while True:
            result = manager.get(initial["operationId"])
            if result["status"] in ("succeeded", "failed", "cancelled"):
                break
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert result["status"] == ("succeeded" if published else "cancelled")
        assert output.read_bytes() == (b"new" if published else b"old")
        assert (result["result"] is not None) == published
    finally:
        release.set()
        manager.close()
