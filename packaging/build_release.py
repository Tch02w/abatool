"""Build a new Windows x64 directory bundle; preserve all prior build outputs."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from build_installer import verify_winui_resources
from release_inventory import write_inventory

ROOT = Path(__file__).resolve().parents[1]


def copy_release_docs(root: Path, bundle: Path) -> None:
    shutil.copytree(root / "docs", bundle / "docs")
    # The feature index also links to this test's instructions outside docs/.
    for relative in ("AGENTS.md", "tests/winui_explorer/README.md"):
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)


def run(arguments: list[str], log: Path, environment: dict[str, str]) -> None:
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(arguments, cwd=ROOT, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"Build failed ({result.returncode}): {log}\n"
                           + "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-35:]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-restore", action="store_true", help="Use already restored .NET self-contained runtime packages")
    args = parser.parse_args()
    if os.name != "nt" or Path(sys.executable).resolve() != (ROOT / ".venv/Scripts/python.exe").resolve():
        raise RuntimeError("Use this project's .venv/Scripts/python.exe on Windows.")
    work = ROOT / "GPTWork"
    work.mkdir(exist_ok=True)
    # A distributable directory must inherit the workspace's normal access.
    # tempfile uses mode 0700 on Windows Python 3.14, hiding it from the user
    # when a separate build account creates the release.
    output = work / f"release-win-x64-{uuid4().hex[:12]}"
    output.mkdir()
    bundle = output / "AbaqusTools"
    environment = dict(os.environ)
    environment.update(DOTNET_CLI_HOME=str(work / "dotnet-home"),
                       DOTNET_CLI_UI_LANGUAGE="en-US",
                       PYINSTALLER_CONFIG_DIR=str(output / "pyinstaller-cache"),
                       MPLBACKEND="Agg", PYTHONUTF8="1")
    print(f"BUILD_DIRECTORY={output}", flush=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(bundle),
         "--workpath", str(output / "freeze-work"), str(ROOT / "packaging/control_plane.spec")],
        output / "control-plane-build.log", environment)
    print("Frozen control plane built", flush=True)
    run(["dotnet", "publish", str(ROOT / "winui/AbaqusTools.WinUI/AbaqusTools.WinUI.csproj"),
         "-c", "Release", "-r", "win-x64", "--self-contained", "true", "-p:Platform=x64",
         "-o", str(bundle), *(["--no-restore"] if args.no_restore else [])], output / "winui-publish.log", environment)
    print("Self-contained WinUI published", flush=True)
    copy_release_docs(ROOT, bundle)
    required = ["AbaqusTools.WinUI.exe", "coreclr.dll", "hostfxr.dll", "Microsoft.UI.Xaml.dll",
                "control-plane/AbaqusTools.ControlPlane.exe",
                "control-plane/_internal/modules/postprocessor/defaults.json",
                "control-plane/_internal/modules/postprocessor/abaqus_scripts/scan_odb.py",
                "control-plane/_internal/modules/postprocessor/abaqus_scripts/validate_odb_merge.py",
                "control-plane/_internal/modules/postprocessor/abaqus_scripts/restore_odb_history.py"]
    for relative in required:
        if not (bundle / relative).is_file():
            raise RuntimeError(f"Missing required release file: {relative}")
    verify_winui_resources(bundle)
    forbidden = [p for p in bundle.rglob("*") if p.name.lower() in {"pyside6", "shiboken6", ".venv"}]
    if forbidden:
        raise RuntimeError(f"Unexpected development/Qt dependency: {forbidden}")
    count = write_inventory(ROOT, bundle)
    print(f"BUNDLE={bundle}\nFILES={count}", flush=True)


if __name__ == "__main__":
    main()
