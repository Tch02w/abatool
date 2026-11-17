"""Admission and worker-completion fence for in-memory operation managers."""

from __future__ import annotations

from typing import Any


class OperationShutdownGuard:
    """Reserve only idle managers without bypassing their later close/cleanup.

    Implementers use an RLock, keep futures until completion, and check
    ``_shutdown_reserved`` under that lock before submitting new work.
    """

    _shutdown_reserved = False
    shutdown_kind = "operation"

    def prepare_shutdown(self, *, reserve: bool = True) -> dict[str, Any]:
        with self._lock:
            active = self.list_snapshots(active_only=True)
            active_ids = {item["operationId"] for item in active}
            # A terminal snapshot can precede the worker's final cleanup.
            for operation_id, future in self._futures.items():
                if not future.done() and operation_id not in active_ids:
                    active.append({"operationId": operation_id,
                                   "kind": self.shutdown_kind,
                                   "status": "finishing"})
            safe = not active
            if safe and reserve:
                self._shutdown_reserved = True
            return {"schemaVersion": 1, "safeToStop": safe, "operations": active}
