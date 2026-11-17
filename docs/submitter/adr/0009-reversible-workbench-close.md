# ADR 0009: Reversible workbench close and backend-owned exit

## Status

Accepted for implementation, 2026-11-18. Production HTTP client and isolated backend checks pass; native eight-page close/reopen and real SSH acceptance remain pending. Extends [ADR 0008](0008-all-worker-shutdown-fence.md).

## Problem

The all-worker fence prevents unsafe process termination but does not express a user's choice to retain background work. Disposing the old host cancels tracked tasks before checking the fence. Page drafts and synchronous file/SSH requests also need coordination. A client-side idle response followed by killing a process has a stale-decision risk.

## Decision

1. Save allowlisted UI drafts and await active editing/file operations before preparing a close. Failure keeps the window open and restores interaction. Persist raw input strings separately from backend runtime truth; do not save passwords or tokens.
2. Drain client task creation, then prepare against the actual connected backend. Pin all subsequent close calls to that instance. A creation that starts the backend while draining must appear in the decision.
3. Use an authenticated Prepare/Get/Stop/Commit/Abort protocol. A 60-second renewable lease blocks new POST operations while counting already admitted requests. Reads continue. Abort or lease expiry restores admission; previously issued stop requests are not undone.
4. Offer background continuation, cooperative stop-and-close, or cancel. Background commit releases the lease and leaves all workers/dispatch alive. Stop first disables local dispatch, requests cancellation through each manager, and waits for worker cleanup and pending HTTP requests.
5. Idle/stop commit requires all nine managers idle and no admitted HTTP request. It seals admission; the backend shuts its HTTP server down and performs its own cleanup. The UI detaches without sending automatic cancellation or killing the backend. A lost response does not reverse an accepted commit, strand a sealed backend, or authorize killing any PID.
6. Completion receipts are bounded to 32 and make matching commit retries idempotent. A lost client acknowledgement queries the same instance; it neither repeats a stop nor starts a replacement backend to interpret the old decision.

## Persistence and recovery boundary

`WorkbenchSessionStore` atomically stores route, restored window bounds/maximized state, and selected page inputs in local application data. An unreadable original is retained and blocks overwrite. ODB postprocessing retains its existing workspace store; result-graph edits must be saved successfully before close. Timers pause during preparation and resume on cancellation.

Background continuation means the same backend process remains alive. Reopening reconnects and retrieves current operations; the resources page now observes active transfers as well. It does not imply durable restart of every local/remote job or transfer after a crash/reboot. Existing merge/upgrade/batch journals remain separate.

The legacy all-worker reservation endpoint remains for older clients/default non-window host disposal. It refuses reservation during a prepared close or in-flight POST. Native window close and File/Exit use the new protocol. Old backends without it offer only an explicit keep-background fallback after drafts are saved.

## Evidence

See `tests/control_plane/test_shutdown_protocol.py`, `tests/winui_host/test_shutdown_api.py`, `tests/winui_host/ShutdownClientChecks.cs`, `tests/winui_host/WorkbenchSessionChecks.cs`, and `tests/winui/test_session_bindings.py`. Checks use controlled runners, HTTP and owned helper processes; they do not establish real SSH, solver or native UI acceptance. Exact results and continuation are recorded in [TASK-002](../../08-handoff/ACTIVE_TASKS/TASK-002-migration.md).
