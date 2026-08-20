"""Embeddable result-browser page for the unified workbench."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from .result_browser import ResultBrowserDialog
from .ui_style import build_main_stylesheet


class ResultBrowserPage(QWidget):
    """Wrap the full result browser without creating another window."""

    def __init__(self, result_root: Path, *, coordinator, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("resultBrowserPage")
        self.setStyleSheet(build_main_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = ResultBrowserDialog(
            result_root,
            self,
            coordinator=coordinator,
            prompt_for_unindexed=True,
        )
        self.browser.setWindowFlags(Qt.WindowType.Widget)
        self.browser.setWindowModality(Qt.WindowModality.NonModal)
        self.browser.setSizeGripEnabled(False)
        self.browser.setMinimumSize(0, 0)
        layout.addWidget(self.browser)

    def set_result_root(self, result_root: Path) -> None:
        resolved = Path(result_root).resolve()
        if resolved == self.browser.result_root:
            return
        self.browser.set_result_root(resolved)

    def status_text(self) -> str:
        """Return browse/index state for the shared status bar."""

        browse_status = self.browser.status_label.text().strip()
        return browse_status or self.browser.index_status_label.text().strip()

    def prepare_shutdown(self) -> bool:
        """Wait for preview readers without yet hiding this embedded page."""

        if self.browser.prepare_close(30000):
            return True
        QMessageBox.warning(
            self,
            "结果读取仍在退出",
            "后台目录读取或文件预览尚未安全结束，请稍后再关闭工作台。",
        )
        return False

    def restore_after_failed_shutdown(self) -> None:
        """Undo the reversible close when another tool rejects root shutdown."""

        self.browser.show()
        # ``prepare_close`` invalidates pending read/preview callbacks.  Start a
        # fresh directory refresh so a rejected workspace close cannot leave
        # this page permanently showing an obsolete "正在读取" state.
        self.browser.set_result_root(self.browser.result_root)

    def shutdown(self) -> bool:
        return bool(self.browser.close())


__all__ = ["ResultBrowserPage"]
