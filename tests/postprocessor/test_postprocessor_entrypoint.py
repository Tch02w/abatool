from __future__ import annotations

import sys
import types

from modules.postprocessor import __main__ as entrypoint


def test_postprocessor_module_entrypoint_delegates_lazily(monkeypatch) -> None:
    fake_app = types.ModuleType("modules.postprocessor.app")
    calls = []

    def fake_main() -> int:
        calls.append(True)
        return 23

    fake_app.main = fake_main
    monkeypatch.setitem(sys.modules, "modules.postprocessor.app", fake_app)

    assert entrypoint.run() == 23
    assert calls == [True]
