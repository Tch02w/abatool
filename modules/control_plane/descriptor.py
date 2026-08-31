"""Atomic publication and conservative cleanup of the runtime descriptor."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import ControlPlaneDescriptor


def write_descriptor_atomic(
    path: str | Path,
    descriptor: ControlPlaneDescriptor,
) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor_bytes = (
        json.dumps(
            descriptor.as_payload(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(descriptor_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
        return target
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def remove_descriptor_if_owned(path: str | Path, instance_id: str) -> bool:
    """Remove a descriptor only when it still belongs to this process instance."""

    target = Path(path).expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except OSError, ValueError, TypeError:
        return False
    if not isinstance(payload, dict) or payload.get("instanceId") != instance_id:
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True


__all__ = ["remove_descriptor_if_owned", "write_descriptor_atomic"]
