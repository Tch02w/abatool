"""Shared test isolation configured before application modules are imported."""

from __future__ import annotations

import os
import tempfile

_RUNTIME_DIR = tempfile.TemporaryDirectory(prefix="abaqus-tools-tests-")
os.environ.setdefault("ABAQUS_SUBMITTER_DATA_DIR", _RUNTIME_DIR.name)
