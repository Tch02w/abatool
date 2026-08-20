from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "ABAQUS_SUBMITTER_DATA_DIR",
    os.path.join(tempfile.gettempdir(), "AbaqusToolsUnifiedTest"),
)

from PySide6 import QtCore, QtGui, QtWidgets

import modules.workspace as workspace_module
from modules.submitter.constants import (
    STATUS_FAILED,
    STATUS_PENDING_RUN,
    STATUS_RUNNING,
)
from modules.submitter.models import QueueItem
from modules.workspace import AbaqusToolsWindow

ORIGINAL_PAGE_TITLES = [
    "新建作业",
    "作业队列",
    "作业概览",
    "计算资源",
    "重启动链",
    "ODB 合并",
]
UNIFIED_PAGE_TITLES = ORIGINAL_PAGE_TITLES + ["ODB 后处理", "结果浏览"]


def _without_mnemonic(text: str) -> str:
    return text.replace("&", "")


class _FakePostProcessorPage(QtWidgets.QWidget):
    resultBrowserRequested = QtCore.Signal(object)
    resultRootChanged = QtCore.Signal(object)
    workspaceCloseRequested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.controller = SimpleNamespace(
            folder_edit=QtWidgets.QLineEdit(self),
            result_index_coordinator=object(),
        )
        self.controller.folder_edit.setText(str(Path.cwd()))
        self.shutdown_calls = 0

    def current_result_root(self) -> Path:
        return Path.cwd() / "AbaqusODBPostProcessor_Results"

    def set_source_path(self, source: str | Path) -> Path:
        path = Path(source)
        folder = path.parent if path.suffix.casefold() == ".odb" else path
        self.controller.folder_edit.setText(str(folder))
        return folder

    def status_text(self) -> str:
        return "后处理测试状态"

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        return True


class _FakeResultBrowserPage(QtWidgets.QWidget):
    def __init__(self, result_root: Path, *, coordinator, parent=None) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.browser = SimpleNamespace(result_root=Path(result_root))
        self.shutdown_calls = 0
        self.prepare_shutdown_calls = 0
        self.restore_calls = 0

    def set_result_root(self, result_root: Path) -> None:
        self.browser.result_root = Path(result_root)

    def status_text(self) -> str:
        return "结果浏览测试状态"

    def prepare_shutdown(self) -> bool:
        self.prepare_shutdown_calls += 1
        return True

    def restore_after_failed_shutdown(self) -> None:
        self.restore_calls += 1

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        return True


class UnifiedAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_window(self, *, show: bool = False) -> AbaqusToolsWindow:
        window = AbaqusToolsWindow()
        if show:
            window.show()
            self.application.processEvents()
        self.addCleanup(self._close_window, window)
        return window

    def _close_window(self, window: AbaqusToolsWindow) -> None:
        # A close-protocol test may temporarily install a rejecting test double.
        if not isinstance(window.result_browser_page, QtWidgets.QWidget):
            window.result_browser_page = None
        if not isinstance(window.postprocessor_page, QtWidgets.QWidget):
            window.postprocessor_page = None
        window.close()
        self.application.processEvents()

    @staticmethod
    def menu_map(window: AbaqusToolsWindow) -> dict[str, QtGui.QAction]:
        # Keep the top-level QAction wrappers alive.  On PySide6, retaining only
        # QAction.menu() can release the underlying QMenu in an offscreen test.
        result: dict[str, QtGui.QAction] = {}
        for action in window.workbench_menu_bar.actions():
            if action.menu() is not None:
                result[_without_mnemonic(action.text())] = action
        return result

    @staticmethod
    def action_map(menu_action: QtGui.QAction) -> dict[str, QtGui.QAction]:
        menu = menu_action.menu()
        assert menu is not None
        return {
            _without_mnemonic(action.text()): action
            for action in menu.actions()
            if not action.isSeparator()
        }

    def test_workspace_preserves_six_submitter_pages_and_appends_two_tools(self) -> None:
        window = self.make_window()

        self.assertIs(window.tabs, window.workbench_tabs)
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            UNIFIED_PAGE_TITLES,
        )
        self.assertEqual(window.postprocessor_tab_index, 6)
        self.assertEqual(window.result_browser_tab_index, 7)
        self.assertIs(window.tabs.widget(6), window.postprocessor_placeholder)
        self.assertIs(window.tabs.widget(7), window.result_browser_placeholder)
        self.assertIsNone(window.postprocessor_page)
        self.assertIsNone(window.result_browser_page)
        self.assertEqual(
            window.window_chrome.title_label.text(),
            "Abaqus Workbench — 新建作业",
        )

        window.workbench_tabs.setCurrentIndex(2)
        self.assertEqual(
            window.window_chrome.title_label.text(),
            "Abaqus Workbench — 作业概览",
        )

    def test_primary_tabs_fit_without_overflow_buttons_at_minimum_width(self) -> None:
        window = self.make_window(show=True)
        tab_bar = window.workbench_tabs.tabBar()
        self.assertTrue(tab_bar.usesScrollButtons())
        self.assertEqual(tab_bar.count(), len(UNIFIED_PAGE_TITLES))
        for width, height in (
            (1600, 1000),
            (window.minimumWidth(), window.minimumHeight()),
        ):
            window.resize(width, height)
            self.application.processEvents()
            self.assertLessEqual(
                max(
                    tab_bar.tabRect(index).right()
                    for index in range(tab_bar.count())
                ),
                tab_bar.width() - 1,
            )
            self.assertFalse(
                any(
                    button.isVisibleTo(window)
                    for button in tab_bar.findChildren(QtWidgets.QToolButton)
                    if button.objectName()
                    in {"ScrollLeftButton", "ScrollRightButton"}
                )
            )

    def test_original_menus_are_visible_and_primary_actions_remain_reachable(self) -> None:
        window = self.make_window(show=True)
        menu_actions = self.menu_map(window)

        self.assertEqual(
            list(menu_actions),
            ["文件(F)", "作业(J)", "服务器(S)", "后处理(P)"],
        )
        self.assertTrue(window.workbench_menu_bar.isVisibleTo(window))
        self.assertIs(window.workbench_menu_bar.parentWidget(), window.window_chrome)

        file_actions = self.action_map(menu_actions["文件(F)"])
        job_actions = self.action_map(menu_actions["作业(J)"])
        server_actions = self.action_map(menu_actions["服务器(S)"])
        post_actions = self.action_map(menu_actions["后处理(P)"])
        self.assertEqual(list(file_actions), ["新建作业", "退出"])
        self.assertEqual(list(job_actions), ["管理队列", "开始队列", "终止队列"])
        self.assertEqual(
            list(server_actions),
            ["连接 / 配置服务器", "刷新服务器资源", "断开服务器"],
        )
        self.assertEqual(
            list(post_actions),
            ["在 ODB 后处理中打开当前作业", "打开 ODB 后处理", "打开结果浏览"],
        )

        window.workbench_tabs.setCurrentIndex(2)
        file_actions["新建作业"].trigger()
        self.assertIs(window.workbench_tabs.currentWidget(), window.job_configuration)

        job_actions["管理队列"].trigger()
        self.assertIs(window.workbench_tabs.currentWidget(), window.queue_manager_dialog)

        fake_server_dialog = MagicMock()
        window._server_dialog = fake_server_dialog
        server_actions["连接 / 配置服务器"].trigger()
        fake_server_dialog.show.assert_called_once_with()
        fake_server_dialog.raise_.assert_called_once_with()
        fake_server_dialog.activateWindow.assert_called_once_with()
        window._server_dialog = None

        with patch.object(
            window,
            "_ensure_postprocessor_page",
            return_value=window.postprocessor_placeholder,
        ) as ensure_page:
            post_actions["打开 ODB 后处理"].trigger()
        ensure_page.assert_called()
        self.assertEqual(window.workbench_tabs.currentIndex(), 6)

    def test_workspace_status_bar_exposes_module_context_and_runtime_summaries(self) -> None:
        window = self.make_window(show=True)

        self.assertEqual(window.statusBar().objectName(), "workspaceStatusBar")
        self.assertFalse(window.statusBar().isSizeGripEnabled())
        self.assertEqual(window.qt_binding_status_label.text(), "PySide6")
        self.assertIn("新建作业", window.module_status_label.text())
        self.assertEqual(window.context_status_label.text(), "当前未选择作业")
        self.assertEqual(window.remote_summary_status_label.text(), "远端 ○ 未连接")
        self.assertIn("Abaqus", window.abaqus_summary_status_label.text())

        window.queue_items[:] = [
            QueueItem(job_name="running", status=STATUS_RUNNING),
            QueueItem(job_name="waiting", status=STATUS_PENDING_RUN),
            QueueItem(job_name="failed", status=STATUS_FAILED),
        ]
        window._refresh_workspace_status()
        self.assertEqual(
            window.queue_summary_status_label.text(),
            "队列 3 · 运行 1 · 等待 1 · 异常 1",
        )

    def test_tool_pages_load_lazily_hide_shell_panels_and_restore_them(self) -> None:
        window = self.make_window(show=True)
        postprocessor_module = types.ModuleType(
            "modules.postprocessor.postprocessor_page"
        )
        postprocessor_module.PostProcessorPage = _FakePostProcessorPage
        result_browser_module = types.ModuleType(
            "modules.postprocessor.result_browser_page"
        )
        result_browser_module.ResultBrowserPage = _FakeResultBrowserPage

        self.assertIsNone(window.postprocessor_page)
        self.assertIsNone(window.result_browser_page)
        for panel in (window.project_explorer, window.properties_panel, window.log_dock):
            self.assertTrue(panel.isVisibleTo(window))

        with patch.dict(
            sys.modules,
            {
                postprocessor_module.__name__: postprocessor_module,
                result_browser_module.__name__: result_browser_module,
            },
        ):
            window.workbench_tabs.setCurrentIndex(window.postprocessor_tab_index)
            self.application.processEvents()
            self.assertIsInstance(window.postprocessor_page, _FakePostProcessorPage)
            self.assertIsNone(window.result_browser_page)
            self.assertIs(
                window.workbench_tabs.widget(window.postprocessor_tab_index),
                window.postprocessor_page,
            )
            self.assertIn(str(Path.cwd()), window.windowTitle())
            self.assertEqual(
                window.window_chrome.title_label.toolTip(),
                window.windowTitle(),
            )
            for panel in (
                window.project_explorer,
                window.properties_panel,
                window.log_dock,
            ):
                self.assertFalse(panel.isVisibleTo(window))

            window.workbench_tabs.setCurrentIndex(window.result_browser_tab_index)
            self.application.processEvents()
            self.assertIsInstance(window.result_browser_page, _FakeResultBrowserPage)
            self.assertIs(
                window.workbench_tabs.widget(window.result_browser_tab_index),
                window.result_browser_page,
            )
            self.assertIn(
                str(Path.cwd() / "AbaqusODBPostProcessor_Results"),
                window.windowTitle(),
            )

        window.workbench_tabs.setCurrentIndex(0)
        self.application.processEvents()
        for panel in (window.project_explorer, window.properties_panel, window.log_dock):
            self.assertTrue(panel.isVisibleTo(window))
        self.assertEqual(
            [window.workbench_tabs.tabText(index) for index in range(8)],
            UNIFIED_PAGE_TITLES,
        )

    def test_close_event_is_ignored_when_a_tool_page_refuses_shutdown(self) -> None:
        window = self.make_window()
        rejecting_page = MagicMock()
        rejecting_page.prepare_shutdown.return_value = False
        rejecting_page.shutdown.return_value = False
        window.result_browser_page = rejecting_page
        event = QtGui.QCloseEvent()

        window.closeEvent(event)

        rejecting_page.prepare_shutdown.assert_called_once_with()
        rejecting_page.shutdown.assert_not_called()
        self.assertFalse(event.isAccepted())
        self.assertTrue(window._status_timer.isActive())

    def test_result_page_is_restored_when_postprocessor_refuses_shutdown(self) -> None:
        window = self.make_window()
        result_page = MagicMock()
        result_page.prepare_shutdown.return_value = True
        result_page.shutdown.return_value = True
        postprocessor_page = MagicMock()
        postprocessor_page.shutdown.return_value = False
        window.result_browser_page = result_page
        window.postprocessor_page = postprocessor_page
        event = QtGui.QCloseEvent()

        window.closeEvent(event)

        result_page.prepare_shutdown.assert_called_once_with()
        result_page.shutdown.assert_called_once_with()
        postprocessor_page.shutdown.assert_called_once_with()
        result_page.restore_after_failed_shutdown.assert_called_once_with()
        self.assertFalse(event.isAccepted())
        self.assertTrue(window._status_timer.isActive())

    def test_main_schedules_restored_queue_status_scan_after_first_show(self) -> None:
        application = MagicMock()
        application.exec.return_value = 17
        window = MagicMock()
        window_factory = MagicMock(return_value=window)
        window_factory.APP_TITLE = "Abaqus Workbench"
        fusion_style = object()

        with (
            patch.object(
                workspace_module.QtWidgets,
                "QApplication",
                return_value=application,
            ),
            patch.object(
                workspace_module.QtWidgets.QStyleFactory,
                "create",
                return_value=fusion_style,
            ),
            patch.object(workspace_module, "apply_application_style") as apply_style,
            patch.object(workspace_module, "AbaqusToolsWindow", window_factory),
            patch.object(workspace_module.QtCore.QTimer, "singleShot") as single_shot,
        ):
            result = workspace_module.main(["abaqus-tools-test"])

        self.assertEqual(result, 17)
        application.setApplicationName.assert_called_once_with("Abaqus Workbench")
        application.setStyle.assert_called_once_with(fusion_style)
        apply_style.assert_called_once_with(application)
        window.showMaximized.assert_called_once_with()
        single_shot.assert_called_once_with(
            0,
            window.request_restored_status_scan_after_main_window_render,
        )


if __name__ == "__main__":
    unittest.main()
