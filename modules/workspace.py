"""Single-window entry point for the Abaqus tools workspace."""

from __future__ import annotations

import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QStyleFactory, QTabWidget

from .postprocessor.app import MainWindow as OdbPostProcessorWindow
from .postprocessor.ui_style import apply_application_style
from .submitter.main import MainWindow as SubmitterWindow


class AbaqusToolsWindow(QMainWindow):
    """Host the two Abaqus workflows in one desktop window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Abaqus Tools")
        self.resize(1600, 1000)
        self.setMinimumSize(1200, 760)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setTabsClosable(False)
        self.setCentralWidget(self.tabs)

        self.submitter = SubmitterWindow(parent=self, embedded=True)
        self.postprocessor = OdbPostProcessorWindow(parent=self)
        self.tabs.addTab(self.submitter, "作业提交与调度")
        self.tabs.addTab(self.postprocessor, "ODB 后处理")
        self.tabs.currentChanged.connect(self._update_title)

        tools_menu = self.menuBar().addMenu("工具")
        show_submitter = QAction("作业提交与调度", self)
        show_submitter.setShortcut("Ctrl+1")
        show_submitter.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        tools_menu.addAction(show_submitter)
        show_postprocessor = QAction("ODB 后处理", self)
        show_postprocessor.setShortcut("Ctrl+2")
        show_postprocessor.triggered.connect(lambda: self.tabs.setCurrentIndex(1))
        tools_menu.addAction(show_postprocessor)
        self._update_title(0)

    def _update_title(self, index: int) -> None:
        self.setWindowTitle(f"Abaqus Tools — {self.tabs.tabText(index)}")

    def closeEvent(self, event) -> None:
        for tool in (self.submitter, self.postprocessor):
            tool.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    """Run the unified Qt desktop application."""

    application = QApplication(list(sys.argv if argv is None else argv))
    application.setApplicationName("Abaqus Tools")
    application.setStyle(QStyleFactory.create("Fusion"))
    apply_application_style(application)
    window = AbaqusToolsWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
