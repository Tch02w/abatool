"""Legacy PySide6 asynchronous wrapper around the Qt-free SSH manager."""

from __future__ import annotations

from dataclasses import dataclass

from .qt_compat import QtCore, Signal, Slot
from .remote_connection import (
    HostKeyConfirmationRequired,
    RemoteConnectionError,
    RemoteConnectionManager,
    ServerConnectionRequest,
)


@dataclass(frozen=True)
class _RemoteOperation:
    action: str
    request: ServerConnectionRequest | None = None


class _RemoteConnectionWorker(QtCore.QObject):
    succeeded = Signal(str, object)
    confirmationRequired = Signal(object, str)
    failed = Signal(str)
    done = Signal()

    def __init__(
        self,
        manager: RemoteConnectionManager,
        operation: _RemoteOperation,
    ) -> None:
        super().__init__()
        self.manager = manager
        self.operation = operation

    @Slot()
    def run(self) -> None:
        try:
            if self.operation.action == "connect":
                if self.operation.request is None:
                    raise RemoteConnectionError("连接请求缺少服务器配置。")
                result = self.manager.connect(self.operation.request)
            elif self.operation.action == "refresh":
                result = self.manager.refresh()
            else:
                result = self.manager.disconnect()
        except HostKeyConfirmationRequired as exc:
            self.confirmationRequired.emit(self.operation.request, exc.fingerprint)
        except Exception as exc:  # noqa: BLE001 - relay unexpected worker failures
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(self.operation.action, result)
        finally:
            self.done.emit()


class RemoteConnectionService(QtCore.QObject):
    """Execute serialized SSH operations without blocking the Qt event loop."""

    busyChanged = Signal(bool)
    confirmationRequired = Signal(object, str)
    connected = Signal(object)
    snapshotReceived = Signal(object)
    disconnected = Signal(str)
    failed = Signal(str)
    idle = Signal()

    def __init__(
        self,
        manager: RemoteConnectionManager | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager or RemoteConnectionManager()
        self._thread: QtCore.QThread | None = None
        self._worker: _RemoteConnectionWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def connect_to_server(self, request: ServerConnectionRequest) -> bool:
        return self._start(_RemoteOperation("connect", request))

    def refresh(self) -> bool:
        return self._start(_RemoteOperation("refresh"))

    def disconnect(self) -> bool:
        if self._thread is not None:
            self.failed.emit("服务器操作正在进行，请稍候。")
            return False
        return self._start(_RemoteOperation("disconnect"))

    def _start(self, operation: _RemoteOperation) -> bool:
        if self._thread is not None:
            self.failed.emit("服务器操作正在进行，请稍候。")
            return False
        thread = QtCore.QThread(self)
        worker = _RemoteConnectionWorker(self.manager, operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_succeeded)
        worker.confirmationRequired.connect(self.confirmationRequired)
        worker.failed.connect(self.failed)
        worker.done.connect(worker.deleteLater)
        worker.done.connect(thread.quit)
        thread.finished.connect(self._clear_worker)
        self._thread = thread
        self._worker = worker
        self.busyChanged.emit(True)
        thread.start()
        return True

    @Slot(str, object)
    def _on_succeeded(self, action: str, result: object) -> None:
        if action == "connect":
            self.connected.emit(result)
            self.snapshotReceived.emit(result)
        elif action == "refresh":
            self.snapshotReceived.emit(result)
        else:
            self.disconnected.emit(str(result or ""))

    @Slot()
    def _clear_worker(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self.busyChanged.emit(False)
        self.idle.emit()
        if thread is not None:
            thread.deleteLater()

    def shutdown(self) -> None:
        thread = self._thread
        if thread is not None:
            self.manager.disconnect()
            thread.quit()
            if thread.isRunning():
                thread.wait(15000)
        self.manager.disconnect()


__all__ = ["RemoteConnectionService"]
