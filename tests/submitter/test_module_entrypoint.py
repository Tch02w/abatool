from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from modules.submitter import __main__ as entrypoint


class SubmitterModuleEntrypointTests(unittest.TestCase):
    def test_run_delegates_to_standalone_main_with_startup_timing(self) -> None:
        captured: dict[str, object] = {}
        fake_main_module = types.ModuleType("modules.submitter.main")

        def fake_main(**kwargs) -> int:
            captured.update(kwargs)
            return 23

        fake_main_module.main = fake_main
        with (
            patch.dict(sys.modules, {"modules.submitter.main": fake_main_module}),
            patch.object(entrypoint.time, "monotonic", return_value=125.0),
            patch.object(entrypoint, "startup_timeline_enabled", return_value=False),
        ):
            result = entrypoint.run()

        self.assertEqual(result, 23)
        self.assertEqual(captured["startup_timeline_start"], 125.0)
        self.assertEqual(captured["startup_timeline_last"], 125.0)
        self.assertFalse(captured["startup_timeline_enabled"])


if __name__ == "__main__":
    unittest.main()
