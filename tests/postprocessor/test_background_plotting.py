"""File-only plots must not initialize the desktop backend in executor threads."""
import os
from pathlib import Path
import subprocess
import sys


def test_plot_export_ignores_interactive_backend_in_worker_thread(tmp_path):
    root = Path(__file__).resolve().parents[2]
    program = r'''
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import warnings
import matplotlib
matplotlib.use("QtAgg")
from modules.postprocessor.postprocess_core import plot_load_resistance, write_csv
output = Path(sys.argv[1])
write_csv(output / "History_Output" / "load_resistance_processed.csv", [
    dict(PileTopDisplacementAbs_mm=i, PileTopReaction_kN=i*10,
         RootKeyTotalBearing_kN=i*3, PileShaftFriction_kN=i*6, UnresolvedResistance_kN=i)
    for i in (0, 1)
])
warnings.filterwarnings("error", message="Starting a Matplotlib GUI.*")
with ThreadPoolExecutor(max_workers=1) as pool:
    result = pool.submit(plot_load_resistance, output).result()
assert result.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
assert matplotlib.get_backend().lower() == "qtagg", "Export must not change caller's backend"
'''
    result = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)], cwd=root,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
