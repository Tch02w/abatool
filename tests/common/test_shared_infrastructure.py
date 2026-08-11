from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.common.app_paths import resolve_app_data_dir
from modules.common.json_io import load_json_mapping, save_json_mapping


class SharedInfrastructureTests(unittest.TestCase):
    def test_json_mapping_round_trip_preserves_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            payload = {"状态": "待运行", "workers": 2}
            save_json_mapping(path, payload)
            self.assertEqual(load_json_mapping(path), payload)
            self.assertFalse(path.with_name("settings.json.tmp").exists())

    def test_json_mapping_handles_missing_or_invalid_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_json_mapping(path), {})
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(load_json_mapping(path), {})

    def test_data_directory_honors_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            variable = "ABAQUS_TOOLS_SHARED_TEST_DIR"
            with patch.dict(os.environ, {variable: directory}, clear=False):
                self.assertEqual(
                    resolve_app_data_dir("Ignored", environment_variable=variable),
                    Path(directory).resolve(),
                )


if __name__ == "__main__":
    unittest.main()
