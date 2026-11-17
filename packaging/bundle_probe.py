"""Offline checks executed inside the shipped Python runtime, without Abaqus."""

import json
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import paramiko
import psutil
from matplotlib import pyplot as plt
from openpyxl import Workbook
from PIL import Image

from modules.postprocessor.config import PACKAGE_DIR, load_defaults
from modules.postprocessor.postprocess_core import finalize_render_output
from modules.postprocessor.result_catalog import read_xlsx_preview


def probe(output: str) -> None:
    parent = Path(output).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="bundle-probe-", dir=parent))
    scripts = sorted((PACKAGE_DIR / "abaqus_scripts").glob("*.py"))
    if not scripts or not load_defaults():
        raise RuntimeError("Packaged defaults or Abaqus scripts are missing")
    frames = work / "frames" / "CHECK"
    frames.mkdir(parents=True)
    for index, color in enumerate(("red", "green", "blue")):
        Image.new("RGB", (32, 24), color).save(frames / f"{index:04d}.png")
    finalize_render_output(work, fps=25, export_transparent_background_png=False)
    with Image.open(work / "animations/CHECK.gif") as animation:
        if animation.n_frames != 3 or animation.info["duration"] != 40:
            raise RuntimeError("Bundled GIF export failed")
    figure, axis = plt.subplots()
    axis.plot([0, 1], [0, 2])
    figure.savefig(work / "plot.png")
    plt.close(figure)
    workbook = Workbook()
    workbook.active.append(["时间", "力"])
    workbook.active.append([0, 12.5])
    workbook.save(work / "table.xlsx")
    preview = read_xlsx_preview(work / "table.xlsx")
    if "12.5" not in str(preview):
        raise RuntimeError("Bundled spreadsheet preview failed")
    if any(name.startswith(("PySide6", "PyQt", "shiboken")) for name in sys.modules):
        raise RuntimeError("Qt was loaded by the packaged control plane")
    # Validate native SSH crypto imports without transmitting data or reading keys.
    key = paramiko.RSAKey.generate(1024)
    report = {"frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable,
              "worker_script_count": len(scripts), "cpu_count": psutil.cpu_count(),
              "checks": ["defaults", "worker-assets", "gif", "agg-plot", "xlsx-preview", "ssh-crypto", "qt-free"],
              "ssh_key_bits": key.get_bits()}
    (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(work), **report}), flush=True)
