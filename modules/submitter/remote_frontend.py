"""Frontend contracts for Windows SSH execution and ODB merging.

The immutable payloads in this module keep Qt forms independent from the SSH
adapter.  Credentials intentionally live in a separate, non-persistent request.
"""

from __future__ import annotations

from .qt_compat import QtCore, Signal
from .remote_models import (
    ExecutionLocation,
    OdbMergeDraft,
    RemoteJobDraft,
    ServerProfileDraft,
)


class RemoteFrontendBridge(QtCore.QObject):
    """Signals reserved for the future remote execution and merge Adapters."""

    testConnectionRequested = Signal(object)
    reconnectRequested = Signal(str)
    resourceRefreshRequested = Signal(str)
    resourceSnapshotReceived = Signal(object)
    browseRemoteDirectoryRequested = Signal(object)
    submitRemoteJobRequested = Signal(object)
    cancelRemoteJobRequested = Signal(str, bool)
    mergeOdbRequested = Signal(object)
    mergeValidationSnapshotReceived = Signal(object)
    transferEventReceived = Signal(object)
    mergeEventReceived = Signal(object)
    problemEventReceived = Signal(object)


__all__ = [
    "ExecutionLocation",
    "OdbMergeDraft",
    "RemoteFrontendBridge",
    "RemoteJobDraft",
    "ServerProfileDraft",
]
