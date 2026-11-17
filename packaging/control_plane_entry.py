"""Console entry for the WinUI-owned, Qt-free frozen control plane."""

import sys
from multiprocessing import freeze_support

from modules.control_plane.__main__ import main

if __name__ == "__main__":
    freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--check-bundle":
        from bundle_probe import probe
        probe(sys.argv[2])
        raise SystemExit(0)
    raise SystemExit(main())
