"""A relocated release must identify itself and have usable offline documentation."""

import hashlib
import importlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release_tools(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "packaging"))
    return importlib.import_module("build_release"), importlib.import_module("release_inventory")


def test_release_readme_and_manifest_use_the_same_source(release_tools, tmp_path, monkeypatch):
    _, inventory = release_tools
    previous = "a" * 40
    current = "b" * 40
    replies = iter((previous, "", current, " M README.md"))
    monkeypatch.setattr(inventory.subprocess, "check_output", lambda *args, **kwargs: next(replies))

    for revision, dirty in ((previous, False), (current, True)):
        assert inventory.write_release_manifest(ROOT, tmp_path) == 1
        manifest = json.loads((tmp_path / "release-manifest.json").read_bytes())
        raw = (tmp_path / "README.md").read_bytes()
        readme = raw.decode("utf-8")
        assert manifest["sourceCommit"] == revision and revision in readme
        assert manifest["sourceDirty"] is dirty
        assert ("含未提交的改动" if dirty else "与提交一致") in readme
        assert manifest["files"]["README.md"] == {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert previous not in readme


def test_shipped_documentation_links_resolve_inside_relocated_package(release_tools, tmp_path):
    build, inventory = release_tools
    bundle = tmp_path / "任意位置 工作台"
    bundle.mkdir()
    (bundle / "AbaqusTools.WinUI.exe").touch()
    build.copy_release_docs(ROOT, bundle)
    inventory.write_release_manifest(ROOT, bundle)

    entry = (bundle / "README.md").read_text(encoding="utf-8")
    for target in ("AbaqusTools.WinUI.exe", "release-manifest.json", "docs/repowiki/user-guide.md",
                   "docs/repowiki/postprocessor.md"):
        assert f"]({target})" in entry
    assert "GPTWork" not in entry
    for document in bundle.rglob("*.md"):
        for target in re.findall(r"\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")):
            url = urlsplit(target.strip("<>"))
            if url.scheme or not url.path:
                continue
            resolved = (document.parent / unquote(url.path)).resolve()
            assert resolved.is_relative_to(bundle) and resolved.exists(), f"{document}: {target}"
