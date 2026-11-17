"""Disposable crash-test process: no Abaqus invocation or model writes."""
import os
import sys
import threading
from pathlib import Path

from modules.control_plane.odb_upgrade_operations import OdbUpgradeOperationManager


def runner(preview, *, on_result, **kwargs):
    on_result({'source_path': 'case.odb', 'status': 'upgraded'})
    print('receipt-ready' if manager._storage_error is None else 'receipt-error', flush=True)
    threading.Event().wait()


manager = OdbUpgradeOperationManager(journal_path=Path(sys.argv[1]), runner=runner)
print(os.getpid(), flush=True)  # Windows venv launcher PID can differ from this worker.
manager.create({'schemaVersion': 1, 'clientRequestId': 'crash-test', 'confirmed': True,
                'preview': {'entries': [{'sourcePath': 'case.odb'}, {'sourcePath': 'next.odb'}]}})
threading.Event().wait()
