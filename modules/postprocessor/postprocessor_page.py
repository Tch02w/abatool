"""Embeddable ODB postprocessor page for the unified workbench."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .app import MainWindow as PostProcessorWindow
from .paths import APP_NAME


class _EmbeddedPostProcessorWindow(PostProcessorWindow):
    """Report a later accepted close after an asynchronous cancellation."""

    closeAccepted = Signal()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if event.isAccepted():
            self.closeAccepted.emit()


class PostProcessorPage(QWidget):
    """Host the complete postprocessor controller as a child widget."""

    resultBrowserRequested = Signal(object)
    resultRootChanged = Signal(object)
    workspaceCloseRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("postProcessorPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._resume_workspace_close = False
        self._folder_change_timer = QTimer(self)
        self._folder_change_timer.setSingleShot(True)
        self._folder_change_timer.setInterval(200)
        self._folder_change_timer.timeout.connect(self._emit_result_root_changed)
        self.controller = _EmbeddedPostProcessorWindow()
        self.controller.setParent(self)
        self.controller.setWindowFlags(Qt.WindowType.Widget)
        self.controller.setMinimumSize(0, 0)
        layout.addWidget(self.controller)

        try:
            self.controller.result_browser_button.clicked.disconnect(
                self.controller._open_result_browser
            )
        except (RuntimeError, TypeError):
            pass
        self.controller.result_browser_button.clicked.connect(
            self._request_result_browser
        )
        self.controller.folder_edit.editingFinished.connect(
            self._folder_editing_finished
        )
        self.controller.folder_edit.textChanged.connect(
            self._schedule_result_root_changed
        )
        self.controller.closeAccepted.connect(self._controller_close_accepted)

    def current_result_root(self) -> Path:
        folder_text = self.controller.folder_edit.text().strip()
        base = Path(folder_text).expanduser() if folder_text else Path.cwd()
        return (base / f"{APP_NAME}_Results").resolve()

    def set_source_path(self, source: str | Path) -> Path:
        """Point the page at an ODB file or directory without scanning it."""

        path = Path(source).expanduser()
        folder = path.parent if path.suffix.casefold() == ".odb" else path
        self.controller.folder_edit.setText(str(folder))
        # ``textChanged`` starts the typing debounce.  This API already emits
        # the fully resolved route synchronously, so cancel that duplicate.
        self._folder_change_timer.stop()
        self.controller.folder_edit.setFocus()
        self.resultRootChanged.emit(self.current_result_root())
        return folder

    def status_text(self) -> str:
        """Return the existing scan/queue status for the shared status bar."""

        return self.controller.scan_status.text().strip()

    def _request_result_browser(self) -> None:
        result_root = self.current_result_root()
        self.resultBrowserRequested.emit(result_root)

    def _folder_editing_finished(self) -> None:
        self._folder_change_timer.stop()
        self._emit_result_root_changed()

    def _schedule_result_root_changed(self, _text: str) -> None:
        self._folder_change_timer.start()

    def _emit_result_root_changed(self) -> None:
        self.resultRootChanged.emit(self.current_result_root())

    def _controller_close_accepted(self) -> None:
        # ``closeAccepted`` is also emitted synchronously by an ordinary close.
        # Defer the decision until ``shutdown`` knows whether that request was
        # accepted or is waiting for batch cancellation to finish.
        QTimer.singleShot(0, self._resume_workspace_close_if_needed)

    def _resume_workspace_close_if_needed(self) -> None:
        if not self._resume_workspace_close:
            return
        self._resume_workspace_close = False
        self.workspaceCloseRequested.emit()

    def shutdown(self) -> bool:
        """Ask the controller to stop safely, preserving its close contract."""

        self._resume_workspace_close = False
        accepted = bool(self.controller.close())
        if not accepted:
            self._resume_workspace_close = bool(
                getattr(self.controller, "_exit_after_cancel", False)
            )
        return accepted


__all__ = ["PostProcessorPage"]
