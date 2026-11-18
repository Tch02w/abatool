"""Installer generation rejects incomplete or redirected release payloads."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("build_installer", Path(__file__).resolve().parents[2] / "packaging/build_installer.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "中文 空格 {payload}"
    entries = {}
    for relative in ("AbaqusTools.WinUI.exe", "control-plane/AbaqusTools.ControlPlane.exe", "docs/readme.txt"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Installer fixture; not an executable")
        entries[relative] = {"bytes": path.stat().st_size, "sha256": installer.digest(path)}
    manifest = {"schemaVersion": 1, "architecture": "win-x64", "sourceDirty": False,
                "sourceCommit": "1" * 40, "files": entries}
    (root / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


@pytest.mark.parametrize("fault", ["dirty", "changed", "extra", "missing", "escape", "duplicate"])
def test_rejects_inconsistent_release(bundle, fault):
    path = bundle / "release-manifest.json"
    manifest = json.loads(path.read_text())
    if fault == "dirty":
        manifest["sourceDirty"] = True
    elif fault == "changed":
        (bundle / "docs/readme.txt").write_bytes(b"changed")
    elif fault == "extra":
        (bundle / "extra.txt").touch()
    elif fault == "missing":
        (bundle / "docs/readme.txt").unlink()
    else:
        manifest["files"]["../outside" if fault == "escape" else "DOCS/README.TXT"] = {
            "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest(),
        }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        installer.verified_bundle(bundle)


def test_render_uses_versioned_payload_and_exact_hashes(bundle, tmp_path):
    output = tmp_path / "output"
    report = installer.render(bundle, output, "0.1.0", test_id="abcdef123456")
    script = (output / "installer.iss").read_text(encoding="utf-8-sig")
    assert report["testOnly"] and report["appId"].endswith(".Test.abcdef123456")
    assert report["fileCount"] == 4
    assert "{{payload}" in script
    for entry in json.loads((bundle / "release-manifest.json").read_text())["files"].values():
        assert f"VerifyInstalledFile('{entry['sha256']}')" in script
    assert "[InstallDelete]" not in script and "[UninstallDelete]" not in script
    assert "[Run]" not in script
    assert "CloseApplications=no" in script and "PrivilegesRequired=lowest" in script
    assert "[Icons]" in script and "BeforeInstall: GuardInstall" in script


@pytest.mark.parametrize("version", ['1.2', '1.2.65536', '1.2.3\nAppId=other', 'alpha'])
def test_version_cannot_inject_or_overflow(bundle, tmp_path, version):
    with pytest.raises(ValueError):
        installer.render(bundle, tmp_path / "output", version)
