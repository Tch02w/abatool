"""Collect dependency notices and a verifiable inventory for a directory release."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement


def write_inventory(root: Path, bundle: Path) -> int:
    notices = bundle / "THIRD_PARTY_NOTICES"
    notices.mkdir(exist_ok=True)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
    pending = ["Pillow", "matplotlib", "numpy", "pandas", "paramiko", "psutil", "openpyxl", "XlsxWriter"]
    dependencies = {}
    while pending:
        item = distribution(pending.pop())
        name = item.metadata["Name"]
        if name in dependencies:
            continue
        copied = []
        for relative in item.files or ():
            if any(label in relative.name.upper() for label in ("LICENSE", "COPYING", "NOTICE")):
                source = Path(item.locate_file(relative))
                if source.is_file():
                    destination = notices / name / str(relative).replace("..", "__")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    copied.append(destination.relative_to(bundle).as_posix())
        dependencies[name] = {"version": item.version, "notices": copied,
                              "license": item.metadata.get("License-Expression") or item.metadata.get("License")}
        for dependency in item.requires or ():
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    (notices / "dependencies.json").write_text(json.dumps(dependencies, ensure_ascii=False, indent=2), encoding="utf-8")
    return write_release_manifest(root, bundle)


def write_release_manifest(root: Path, bundle: Path) -> int:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    template = (root / "packaging/portable-readme.md.in").read_text(encoding="utf-8")
    (bundle / "README.md").write_text(template.format(
        source_commit=revision, source_state="含未提交的改动" if dirty else "与提交一致",
    ), encoding="utf-8")
    files = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path != bundle / "release-manifest.json":
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files[path.relative_to(bundle).as_posix()] = {"bytes": path.stat().st_size, "sha256": digest}
    (bundle / "release-manifest.json").write_text(json.dumps({
        "schemaVersion": 1, "architecture": "win-x64", "sourceCommit": revision,
        "sourceDirty": dirty, "pythonVersion": sys.version, "files": files,
        "validation": "File inventory only; runtime and clean-machine acceptance are separate.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(files)
