"""Single-window PySide6 composition root for all Abaqus workflows."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .postprocessor.ui_style import apply_application_style
from .routes import odb_candidate_for_job
from .submitter.constants import (
    ACTIVE_STATUSES,
    STATUS_CANCELED,
    STATUS_DATACHECK_FAILED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING_RUN,
    STATUS_TERMINATED,
    STATUS_UNKNOWN,
    STATUS_WAITING_DEPENDENCY,
)
from .submitter.main import MainWindow as SubmitterWindow
from .submitter.queue_scheduler import queue_status_counts
from .submitter.ui_components import configure_popup_menu, format_run_status


class AbaqusToolsWindow(SubmitterWindow):
    """Restore the Submitter workbench shell and add ODB tool pages."""

    APP_TITLE = "Abaqus Workbench"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(self.APP_TITLE)
        self.window_chrome.title_label.setText(self.APP_TITLE)
        self.window_chrome.set_menu_bar(self.workbench_menu_bar)

        # Keep the established Submitter shell (menus, sidebars, properties and
        # log dock) and extend its primary page stack, matching the pre-merge
        # workbench instead of nesting two QMainWindows in a second tab bar.
        self.tabs = self.workbench_tabs
        self.postprocessor_page = None
        self.result_browser_page = None
        self._loading_tool_page = False

        self.postprocessor_placeholder = self._loading_placeholder(
            "首次打开时加载 ODB 后处理模块…"
        )
        self.result_browser_placeholder = self._loading_placeholder(
            "首次打开时加载结果浏览模块…"
        )
        self.postprocessor_tab_index = self.workbench_tabs.addTab(
            self.postprocessor_placeholder,
            "ODB 后处理",
        )
        self.result_browser_tab_index = self.workbench_tabs.addTab(
            self.result_browser_placeholder,
            "结果浏览",
        )
        self.workbench_tabs.currentChanged.connect(self._tool_page_changed)
        self.workbench_tabs.currentChanged.connect(self._update_window_context)

        self._add_postprocessing_menu()
        self._build_workspace_status_bar()
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_workspace_status)
        self._status_timer.start()
        self._update_window_context(self.workbench_tabs.currentIndex())

    @staticmethod
    def _loading_placeholder(text: str) -> QtWidgets.QWidget:
        placeholder = QtWidgets.QWidget()
        placeholder.setObjectName("toolLoadingPlaceholder")
        layout = QtWidgets.QVBoxLayout(placeholder)
        label = QtWidgets.QLabel(text)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setObjectName("emptyState")
        layout.addWidget(label)
        return placeholder

    def _replace_tool_tab(
        self,
        index: int,
        widget: QtWidgets.QWidget,
        title: str,
    ) -> None:
        current_index = self.workbench_tabs.currentIndex()
        signals_blocked = self.workbench_tabs.blockSignals(True)
        try:
            self.workbench_tabs.removeTab(index)
            self.workbench_tabs.insertTab(index, widget, title)
            if current_index == index:
                self.workbench_tabs.setCurrentIndex(index)
        finally:
            self.workbench_tabs.blockSignals(signals_blocked)

    def _ensure_postprocessor_page(self):
        if self.postprocessor_page is not None:
            return self.postprocessor_page
        from .postprocessor.postprocessor_page import PostProcessorPage

        page = PostProcessorPage(self)
        self.postprocessor_page = page
        page.resultBrowserRequested.connect(self.show_result_browser)
        page.resultRootChanged.connect(self._postprocessor_root_changed)
        page.workspaceCloseRequested.connect(self.close)
        self._replace_tool_tab(self.postprocessor_tab_index, page, "ODB 后处理")
        return page

    def _ensure_result_browser_page(self):
        if self.result_browser_page is not None:
            return self.result_browser_page
        from .postprocessor.result_browser_page import ResultBrowserPage

        postprocessor_page = self._ensure_postprocessor_page()
        page = ResultBrowserPage(
            postprocessor_page.current_result_root(),
            coordinator=postprocessor_page.controller.result_index_coordinator,
            parent=self,
        )
        self.result_browser_page = page
        self._replace_tool_tab(self.result_browser_tab_index, page, "结果浏览")
        return page

    def _add_postprocessing_menu(self) -> None:
        menu = configure_popup_menu(
            self.workbench_menu_bar.addMenu("后处理(&P)")
        )
        self.open_current_job_postprocessor_action = menu.addAction(
            "在 ODB 后处理中打开当前作业",
            self.open_current_job_in_postprocessor,
        )
        menu.addSeparator()
        self.show_postprocessor_action = menu.addAction(
            "打开 ODB 后处理",
            self.show_postprocessor,
        )
        self.show_postprocessor_action.setShortcut("Ctrl+7")
        self.show_result_browser_action = menu.addAction(
            "打开结果浏览",
            self.show_result_browser,
        )
        self.show_result_browser_action.setShortcut("Ctrl+8")

    def show_postprocessor(self, source: str | Path | None = None) -> None:
        page = self._ensure_postprocessor_page()
        if source is not None:
            page.set_source_path(source)
        self.workbench_tabs.setCurrentWidget(page)
        self._refresh_workspace_status()

    def open_current_job_in_postprocessor(self) -> None:
        run = self.run_records.get(self.selected_job_key())
        candidate = odb_candidate_for_job(
            run,
            fallback_work_dir=self.current_work_dir,
            fallback_job_name=self.current_job_name,
        )
        if candidate is None:
            QtWidgets.QMessageBox.information(
                self,
                "ODB 后处理",
                "当前没有可用的作业目录。请先选择或提交一个作业。",
            )
            return
        self.show_postprocessor(candidate)

    @QtCore.Slot()
    @QtCore.Slot(object)
    def show_result_browser(self, result_root=None) -> None:
        page = self._ensure_result_browser_page()
        if result_root is not None and not isinstance(result_root, bool):
            page.set_result_root(Path(result_root))
        self.workbench_tabs.setCurrentWidget(page)
        self._refresh_workspace_status()

    def _postprocessor_root_changed(self, result_root: object) -> None:
        if self.result_browser_page is not None:
            self.result_browser_page.set_result_root(Path(result_root))
        self._refresh_workspace_status()

    def _tool_page_changed(self, index: int) -> None:
        tool_page = index in {
            self.postprocessor_tab_index,
            self.result_browser_tab_index,
        }
        self.project_explorer.setVisible(not tool_page)
        self.properties_panel.setVisible(not tool_page)
        self.log_dock.setVisible(not tool_page)
        if not tool_page or self._loading_tool_page:
            self._refresh_workspace_status()
            return
        self._loading_tool_page = True
        try:
            if index == self.postprocessor_tab_index:
                self._ensure_postprocessor_page()
            elif index == self.result_browser_tab_index:
                self._ensure_result_browser_page()
        finally:
            self._loading_tool_page = False
        self._refresh_workspace_status()

    def _build_workspace_status_bar(self) -> None:
        status_bar = QtWidgets.QStatusBar(self)
        status_bar.setObjectName("workspaceStatusBar")
        status_bar.setSizeGripEnabled(False)
        self.setStatusBar(status_bar)

        self.module_status_label = QtWidgets.QLabel()
        self.module_status_label.setObjectName("workspaceStatusModule")
        self.context_status_label = QtWidgets.QLabel()
        self.context_status_label.setObjectName("workspaceStatusContext")
        self.context_status_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.queue_summary_status_label = QtWidgets.QLabel()
        self.queue_summary_status_label.setObjectName("workspaceStatusQueue")
        self.remote_summary_status_label = QtWidgets.QLabel()
        self.remote_summary_status_label.setObjectName("workspaceStatusRemote")
        self.abaqus_summary_status_label = QtWidgets.QLabel()
        self.abaqus_summary_status_label.setObjectName("workspaceStatusAbaqus")
        self.qt_binding_status_label = QtWidgets.QLabel("PySide6")
        self.qt_binding_status_label.setObjectName("workspaceStatusBinding")

        status_bar.addWidget(self.module_status_label)
        status_bar.addWidget(self.context_status_label, 1)
        status_bar.addPermanentWidget(self.queue_summary_status_label)
        status_bar.addPermanentWidget(self.remote_summary_status_label)
        status_bar.addPermanentWidget(self.abaqus_summary_status_label)
        status_bar.addPermanentWidget(self.qt_binding_status_label)

    def _refresh_workspace_status(self) -> None:
        if not hasattr(self, "module_status_label"):
            return
        index = self.workbench_tabs.currentIndex()
        page_title = self.workbench_tabs.tabText(index)
        self._sync_window_context_title(index, page_title)
        self.module_status_label.setText(f"● {page_title}")

        if index == self.postprocessor_tab_index and self.postprocessor_page is not None:
            folder = self.postprocessor_page.controller.folder_edit.text().strip()
            detail = self.postprocessor_page.status_text()
            self.context_status_label.setText(
                " · ".join(value for value in (detail, folder) if value)
            )
        elif index == self.result_browser_tab_index and self.result_browser_page is not None:
            root = str(self.result_browser_page.browser.result_root)
            detail = self.result_browser_page.status_text()
            self.context_status_label.setText(
                " · ".join(value for value in (detail, root) if value)
            )
        else:
            run = self.run_records.get(self.selected_job_key())
            if run is None:
                self.context_status_label.setText("当前未选择作业")
            else:
                status = format_run_status(run) or "状态未知"
                name = str(run.get("job_name") or self.current_job_name or "未命名作业")
                self.context_status_label.setText(f"{name} · {status}")

        counts = queue_status_counts(self.queue_items)
        running = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
        waiting = counts.get(STATUS_PENDING_RUN, 0) + counts.get(
            STATUS_WAITING_DEPENDENCY, 0
        )
        failed = sum(
            counts.get(status, 0)
            for status in (
                STATUS_FAILED,
                STATUS_DATACHECK_FAILED,
                STATUS_INTERRUPTED,
                STATUS_UNKNOWN,
            )
        )
        cancelled = counts.get(STATUS_CANCELED, 0) + counts.get(
            STATUS_TERMINATED, 0
        )
        self.queue_summary_status_label.setText(
            f"队列 {len(self.queue_items)} · 运行 {running} · 等待 {waiting}"
            + (f" · 异常 {failed}" if failed else "")
            + (f" · 取消 {cancelled}" if cancelled else "")
        )

        profile_name = (
            self.remote_connection_service.manager.connected_profile_name
        )
        self.remote_summary_status_label.setText(
            f"远端 ● {profile_name}" if profile_name else "远端 ○ 未连接"
        )
        abaqus_text = self.abaqus_status_label.text().strip()
        self.abaqus_summary_status_label.setText(
            abaqus_text.replace("Abaqus 状态：", "Abaqus ")
        )

    def _sync_window_context_title(self, index: int, page_title: str) -> None:
        """Keep project/result context visible after embedding child windows."""

        title = f"{self.APP_TITLE} — {page_title}"
        if index == self.postprocessor_tab_index and self.postprocessor_page is not None:
            controller = self.postprocessor_page.controller
            child_title = ""
            title_getter = getattr(controller, "windowTitle", None)
            if callable(title_getter):
                child_title = str(title_getter()).strip()
            folder = controller.folder_edit.text().strip()
            if child_title:
                title = f"{self.APP_TITLE} — {child_title}"
            elif folder:
                title = f"{self.APP_TITLE} — {page_title} — {folder}"
        elif index == self.result_browser_tab_index and self.result_browser_page is not None:
            result_root = str(self.result_browser_page.browser.result_root)
            if result_root:
                title = f"{self.APP_TITLE} — {page_title} — {result_root}"

        if self.windowTitle() != title:
            self.setWindowTitle(title)
        self.window_chrome.title_label.setText(title)
        self.window_chrome.title_label.setToolTip(title)

    def _update_window_context(self, index: int) -> None:
        self._refresh_workspace_status()

    def closeEvent(self, event) -> None:
        self._status_timer.stop()
        result_page_closed = False
        if (
            self.result_browser_page is not None
            and not self.result_browser_page.prepare_shutdown()
        ):
            self._status_timer.start()
            event.ignore()
            return
        if self.result_browser_page is not None:
            if not self.result_browser_page.shutdown():
                self._status_timer.start()
                event.ignore()
                return
            result_page_closed = True
        if (
            self.postprocessor_page is not None
            and not self.postprocessor_page.shutdown()
        ):
            if result_page_closed:
                self.result_browser_page.restore_after_failed_shutdown()
            self._status_timer.start()
            event.ignore()
            return
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    """Run the unified Qt desktop application."""

    application = QtWidgets.QApplication(list(sys.argv if argv is None else argv))
    application.setApplicationName(AbaqusToolsWindow.APP_TITLE)
    application.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    apply_application_style(application)
    window = AbaqusToolsWindow()
    window.showMaximized()
    QtCore.QTimer.singleShot(
        0,
        window.request_restored_status_scan_after_main_window_render,
    )
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
