from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "ABAQUS_SUBMITTER_DATA_DIR",
    os.path.join(tempfile.gettempdir(), "AbaqusToolsUnifiedTest"),
)

from PySide6.QtWidgets import QApplication

from modules.workspace import AbaqusToolsWindow


class UnifiedAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_workspace_hosts_both_tools_as_tabs(self) -> None:
        window = AbaqusToolsWindow()
        try:
            self.assertEqual(window.tabs.count(), 2)
            self.assertEqual(window.tabs.tabText(0), "作业提交与调度")
            self.assertEqual(window.tabs.tabText(1), "ODB 后处理")
            self.assertIs(window.tabs.widget(0), window.submitter)
            self.assertIs(window.tabs.widget(1), window.postprocessor)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
