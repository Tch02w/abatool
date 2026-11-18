"""Compile an Inno Setup installer from a verified, clean directory bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "AbaqusTools.Workbench.WinUI3"


def required_winui_resources() -> tuple[str, ...]:
    """Include every current page/control, rather than checking the launcher alone."""
    project = ROOT / "winui/AbaqusTools.WinUI"
    sources = sorted(path for directory in (project, project / "Pages", project / "Controls")
                     for path in directory.glob("*.xaml"))
    return ("AbaqusTools.WinUI.pri", *(path.relative_to(project).with_suffix(".xbf").as_posix()
                                      for path in sources))


def verify_winui_resources(bundle: Path) -> None:
    for relative in required_winui_resources():
        path = bundle / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty compiled WinUI resource: {relative}")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_bundle(bundle: Path, *, require_ui_resources: bool = True) -> tuple[dict, dict[str, dict]]:
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schemaVersion") != 1 or manifest.get("architecture") != "win-x64"
            or manifest.get("sourceDirty") is not False
            or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("sourceCommit", ""))):
        raise ValueError("Installer requires a clean Windows x64 release manifest")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("Release manifest has no files")
    seen = set()
    for relative, entry in entries.items():
        parts = PurePosixPath(relative).parts
        if (not parts or relative != PurePosixPath(relative).as_posix() or relative.startswith("/")
                or any(part in (".", "..") or part.endswith((".", " ")) for part in parts)
                or any(character in relative for character in ':\\\r\n\x00')
                or relative.casefold() in seen):
            raise ValueError(f"Unsafe or duplicate manifest path: {relative}")
        seen.add(relative.casefold())
        path = bundle / relative
        if not path.resolve().is_relative_to(bundle.resolve()) or path.is_symlink():
            raise ValueError(f"Release path escapes bundle: {relative}")
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"Release content differs from manifest: {relative}")
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    if actual != set(entries) | {"release-manifest.json"}:
        raise ValueError("Release has missing or unlisted files")
    for required in ("AbaqusTools.WinUI.exe", "control-plane/AbaqusTools.ControlPlane.exe"):
        if required not in entries:
            raise ValueError(f"Missing required executable: {required}")
    if require_ui_resources:
        verify_winui_resources(bundle)
    entries = dict(entries)
    entries["release-manifest.json"] = {"bytes": manifest_path.stat().st_size, "sha256": digest(manifest_path)}
    return manifest, entries


def quoted(value: str) -> str:
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control character in installer input")
    return '"' + value.replace('"', '""') + '"'


def render(bundle: Path, output: Path, version: str, *, test_id: str | None = None) -> dict:
    if not re.fullmatch(r"\d{1,5}(?:\.\d{1,5}){2,3}", version) or any(int(v) > 65535 for v in version.split('.')):
        raise ValueError("Version must have three or four numeric components (0..65535)")
    if test_id is not None and not re.fullmatch(r"[a-f0-9]{12}", test_id):
        raise ValueError("Test identity must contain 12 lowercase hex digits")
    manifest, entries = verified_bundle(bundle)
    payload_id = manifest["sourceCommit"][:12] + "-" + entries["release-manifest.json"]["sha256"][:12]
    app_id = APP_ID if test_id is None else f"{APP_ID}.Test.{test_id}"
    app_name = "Abaqus Workbench" if test_id is None else f"Abaqus Workbench Test {test_id}"
    output.mkdir(parents=True, exist_ok=False)
    marker = output / "installation-marker"
    marker.write_text(app_id, encoding="ascii")
    files = []
    for relative, entry in sorted(entries.items()):
        directory = str(PurePosixPath(relative).parent).replace('/', '\\')
        destination = "{app}\\versions\\" + payload_id + ("" if directory == "." else "\\" + directory.replace('{', '{{'))
        source = str(bundle / relative).replace('{', '{{')
        files.append(f'Source: {quoted(source)}; DestDir: {quoted(destination)}; Flags: ignoreversion; '
                     f'AfterInstall: VerifyInstalledFile(\'{entry["sha256"]}\')')
    files.append(f'Source: {quoted(str(marker).replace("{", "{{"))}; DestDir: "{{app}}"; '
                 f'DestName: ".abatool-installation"; Flags: ignoreversion; AfterInstall: VerifyInstalledFile(\'{digest(marker)}\')')
    substitutions = {
        "APP_ID": app_id, "APP_NAME": app_name, "VERSION": version,
        "VERSION_INFO": ".".join((version.split('.') + ['0'])[:4]),
        "PAYLOAD_ID": payload_id, "OUTPUT_DIR": str(output).replace('{', '{{'), "FILES": "\n".join(files),
    }
    script = Path(__file__).with_name("installer.iss.in").read_text(encoding="utf-8")
    for name, value in substitutions.items():
        script = script.replace(f"@{name}@", value)
    (output / "installer.iss").write_text(script, encoding="utf-8-sig")
    return {"schemaVersion": 1, "status": "prepared", "version": version, "appId": app_id,
            "testOnly": test_id is not None, "payloadId": payload_id, "bundle": str(bundle),
            "bundleSourceCommit": manifest["sourceCommit"], "bundleManifestSha256": entries["release-manifest.json"]["sha256"],
            "fileCount": len(entries), "installer": str(output / f"AbaqusTools-{version}-win-x64-setup.exe")}


def build(bundle: Path, compiler: Path, version: str, *, test_id: str | None = None) -> Path:
    if os.name != "nt" or not compiler.is_file():
        raise ValueError("An existing Windows Inno Setup compiler is required")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    if dirty and test_id is None:
        raise ValueError("Commit installer sources and documentation before building a distributable installer")
    output = ROOT / "GPTWork" / f"installer-win-x64-{uuid4().hex[:12]}"
    report = render(bundle.resolve(), output, version, test_id=test_id)
    report.update(builderSourceCommit=revision, builderSourceDirty=dirty)
    receipt = output / "build-report.json"
    receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"INSTALLER_DIRECTORY={output}", flush=True)
    try:
        with (output / "compiler.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([str(compiler.resolve()), str(output / "installer.iss")],
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError(f"Installer compilation failed: {output / 'compiler.log'}")
        # Reject a bundle changed while the compiler was reading it.
        _, entries = verified_bundle(bundle)
        if entries["release-manifest.json"]["sha256"] != report["bundleManifestSha256"]:
            raise RuntimeError("Bundle manifest changed during compilation")
        installer = Path(report["installer"])
        report.update(status="compiled", sha256=digest(installer), bytes=installer.stat().st_size,
                      compiler=str(compiler.resolve()), compilerSha256=digest(compiler))
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--test-id", help="Separate installation identity for isolated lifecycle checks")
    args = parser.parse_args()
    build(args.bundle, args.compiler, args.version, test_id=args.test_id)
