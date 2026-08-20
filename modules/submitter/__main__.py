"""Support ``python -m modules.submitter`` and the Submitter GUI script."""

from __future__ import annotations

import time

from .diagnostics import StartupTimeline, startup_timeline_enabled


def run() -> int:
    """Start the standalone Submitter while preserving startup diagnostics."""

    startup_start = time.monotonic()
    timeline = StartupTimeline(
        "Entry",
        enabled=startup_timeline_enabled(),
        start=startup_start,
    )
    timeline.mark("script-start")

    # Keep the large Qt window module lazy so entry diagnostics include its
    # import time and metadata-only imports do not construct the GUI stack.
    from .main import main

    timeline.mark("import-main-module")
    return main(
        startup_timeline_start=startup_start,
        startup_timeline_last=timeline.last,
        startup_timeline_enabled=timeline.enabled,
    )


if __name__ == "__main__":
    raise SystemExit(run())
