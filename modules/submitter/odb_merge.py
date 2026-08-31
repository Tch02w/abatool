"""PySide6 adapter for the shared, Qt-free protected ODB merge service."""

from __future__ import annotations

from modules.postprocessor.process_runner import ProcessCancelled, ProcessController

from .odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeError,
    OdbMergePlan,
    OdbMergeRequest,
    OdbMergeResult,
    build_merge_plan,
    format_command,
    normalize_joined_output,
)
from .odb_merge_execution import execute_odb_merge
from .qt_compat import QtCore, Signal


class _OdbMergeWorker(QtCore.QObject):
    """Translate the shared executor callbacks into the legacy Qt signals."""

    phaseChanged = Signal(str)
    progressChanged = Signal(int)
    outputReceived = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, request: OdbMergeRequest) -> None:
        super().__init__()
        self.request = request
        self._controller = ProcessController()

    def cancel(self) -> None:
        self._controller.cancel()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = execute_odb_merge(
                self.request,
                self._report_progress,
                self.outputReceived.emit,
                self._controller,
            )
            self.succeeded.emit(result)
        except ProcessCancelled:
            self.cancelled.emit()
        except (OSError, OdbMergeError, RuntimeError) as exc:
            self.failed.emit(str(exc))

    def _report_progress(self, percent: int, phase: str) -> None:
        self.phaseChanged.emit(phase)
        self.progressChanged.emit(percent)


class OdbMergeService(QtCore.QObject):
    """Run one protected merge at a time without blocking the Qt UI thread."""

    busyChanged = Signal(bool)
    phaseChanged = Signal(str)
    progressChanged = Signal(int)
    outputReceived = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QtCore.QThread | None = None
        self._worker: _OdbMergeWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, request: OdbMergeRequest) -> bool:
        if self.is_busy:
            self.failed.emit("已有 ODB 合并正在执行。")
            return False
        try:
            build_merge_plan(request)
        except OdbMergeError as exc:
            self.failed.emit(str(exc))
            return False

        thread = QtCore.QThread(self)
        worker = _OdbMergeWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.phaseChanged.connect(self.phaseChanged)
        worker.progressChanged.connect(self.progressChanged)
        worker.outputReceived.connect(self.outputReceived)
        worker.succeeded.connect(self.succeeded)
        worker.failed.connect(self.failed)
        worker.cancelled.connect(self.cancelled)
        for signal in (worker.succeeded, worker.failed, worker.cancelled):
            signal.connect(worker.deleteLater)
            signal.connect(thread.quit)
        thread.finished.connect(self._clear_worker)
        self._thread = thread
        self._worker = worker
        self.busyChanged.emit(True)
        thread.start()
        return True

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    @QtCore.Slot()
    def _clear_worker(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self.busyChanged.emit(False)
        if thread is not None:
            thread.deleteLater()

    def shutdown(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self.cancel()
        thread.quit()
        if thread.isRunning():
            thread.wait(15000)


__all__ = [
    "MergeConflictPolicy",
    "OdbMergeError",
    "OdbMergePlan",
    "OdbMergeRequest",
    "OdbMergeResult",
    "OdbMergeService",
    "build_merge_plan",
    "format_command",
    "normalize_joined_output",
]
