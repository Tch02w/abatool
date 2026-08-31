"""Thread-safe in-memory event history for replayable local SSE responses."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from .contracts import EventDto, utc_now_text


class EventStore:
    """Append events with one global, monotonically increasing sequence."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[EventDto] = []
        self._next_sequence = 1

    def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        attempt_id: str = "",
        version: int = 1,
    ) -> EventDto:
        with self._lock:
            event = EventDto(
                sequence=self._next_sequence,
                event_id=uuid4().hex,
                occurred_at=utc_now_text(),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                attempt_id=attempt_id,
                version=max(1, int(version)),
                kind=kind,
                payload=dict(payload or {}),
            )
            self._events.append(event)
            self._next_sequence += 1
            return event

    def replay(self, *, after_sequence: int = 0) -> tuple[tuple[EventDto, ...], int]:
        after = max(0, int(after_sequence))
        with self._lock:
            events = tuple(event for event in self._events if event.sequence > after)
            cursor = self._next_sequence - 1
        return events, cursor

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._next_sequence - 1


__all__ = ["EventStore"]
