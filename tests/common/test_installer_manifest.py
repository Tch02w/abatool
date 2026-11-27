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
    for relative in ("AbaqusTools.WinUI.exe", "control-plane/AbaqusTools.ControlPlane.exe", "docs/readme.txt",
                     *installer.required_winui_resources()):
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
    assert report["fileCount"] == 4 + len(installer.required_winui_resources())
    assert "{{payload}" in script
    rows = [line for line in script.splitlines() if line.startswith("Source:")]
    assert len(rows) == report["fileCount"] + 1
    for line in rows:
        source = Path(line.split('"')[1].replace("{{", "{"))
        assert f'Hash: "{installer.digest(source)}"' in line
        assert "AfterInstall:" not in line and "dontverifychecksum" not in line.lower()
    assert "[InstallDelete]" not in script and "[UninstallDelete]" not in script
    assert "[Run]" not in script
    assert "CloseApplications=no" in script and "PrivilegesRequired=lowest" in script
    assert "[Icons]" in script and "BeforeInstall: GuardInstall" in script


@pytest.mark.parametrize("warning", ["Exception message:", "Defaulting to OK for suppressed message box (OK):"])
def test_silent_installer_cannot_hide_dialogs_in_a_success_log(tmp_path, monkeypatch, warning):
    monkeypatch.syspath_prepend(str(Path(SPEC.origin).parent))
    from verify_installer import check_install_log

    log = tmp_path / "setup.log"
    log.write_text(warning + "\nInstallation process succeeded.\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="suppressed dialogs"):
        check_install_log(log)
    assert sum(check_install_log(log, historical=True).values()) == 1


@pytest.mark.parametrize("version", ['1.2', '1.2.65536', '1.2.3\nAppId=other', 'alpha'])
def test_version_cannot_inject_or_overflow(bundle, tmp_path, version):
    with pytest.raises(ValueError):
        installer.render(bundle, tmp_path / "output", version)


@pytest.mark.parametrize("resource", [
    "AbaqusTools.WinUI.pri", "MainWindow.xbf", "Pages/NewJobPage.xbf", "Controls/WorkbenchNumberBoxResources.xbf",
])
@pytest.mark.parametrize("fault", ["missing", "empty"])
def test_self_consistent_manifest_cannot_hide_missing_ui_resources(bundle, resource, fault):
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    path = bundle / resource
    if fault == "missing":
        path.unlink()
        del manifest["files"][resource]
    else:
        path.write_bytes(b"")
        manifest["files"][resource] = {"bytes": 0, "sha256": installer.digest(path)}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="compiled WinUI resource"):
        installer.verified_bundle(bundle)


def test_legacy_inventory_verification_cannot_build_an_incomplete_installer(bundle, tmp_path):
    path = bundle / "release-manifest.json"
    manifest = json.loads(path.read_text())
    (bundle / "MainWindow.xbf").unlink()
    del manifest["files"]["MainWindow.xbf"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    installer.verified_bundle(bundle, require_ui_resources=False)
    with pytest.raises(ValueError, match="compiled WinUI resource"):
        installer.render(bundle, tmp_path / "legacy-output", "0.1.0", test_id="abcdef123456")
