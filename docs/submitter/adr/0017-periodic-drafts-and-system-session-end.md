# ADR 0017: Periodic UI checkpoints and system session end

## Status

Implemented in source on 2026-11-18. On 2026-11-28 the Windows release received query, cancelled, confirmed and repeated session messages at its own HWND on a private desktop. A second instance restored the new-job draft and reattached to the same backend. The test left the Windows session running. [Native verification and scope](../../08-handoff/ACTIVE_TASKS/TASK-002-migration.md#窗口关不掉或系统结束会话时的草稿). Extends [ADR 0009](0009-reversible-workbench-close.md).

## Decision

- Sample restored, allowlisted page inputs and window/route state every two seconds. Keep raw incomplete strings; exclude credentials and backend runtime truth. A page constructed but not yet restored must not overwrite the previous checkpoint.
- Serialize on the UI thread, then enqueue immutable JSON on one ordered background writer. Failed writes do not prevent later retries. Skip identical successful contents while the file still exists. Flush the temporary file before replacing the checkpoint; preserve unreadable originals. Display a persistent, separate warning on routine save failure.
- Install an HWND subclass on the UI thread, keep its callback rooted, and remove it on close/destruction. `WM_QUERYENDSESSION` returns true immediately without disk, network, or dialogs. `WM_ENDSESSION(false)` changes no timers or drafts. On confirmed end, capture the allowlist and wait at most two seconds for queued disk writes; duplicate messages do not repeat the save. Timeout/failure is not success, and the prior successful checkpoint remains the recovery baseline.
- Confirmed OS session end skips interactive close/dispose cancellation. Do not send a new backend shutdown/stop request or kill any solver. This does not promise that Windows will keep background work alive during logoff/reboot. A stop already explicitly requested by the user is not revoked.
- Routine checkpoints do not invoke page `Save` callbacks: those may await network or in-flight file operations. Postprocessing workspaces and result-graph drafts keep their existing persistence rules. Their full unsaved-edit crash recovery is a separate remaining item, not implied by this allowlist checkpoint.

## Limits and verification

The result graph uses disk-only checkpoint participants as described in [ADR 0018](0018-result-graph-recovery-drafts.md). Postprocessing workspaces and four unconfirmed dialogs also register checkpoints. Their recovery after an actual OS session end needs separate verification.

A busy UI thread can delay the two-second periodic capture. The final budget applies to the wait for disk writes. A hung disk or immediate termination can leave the previous checkpoint as the most recent recoverable edit. The Windows package identified above contains the session hook.

`tests/winui_host/SystemSessionEndChecks.cs` runs the production message state and store using synthetic messages, a held task, and real files in a fresh evidence directory. It does not call OS shutdown APIs, create a native window, or establish HWND integration acceptance. Existing shutdown HTTP tests continue to verify ordinary-close task ownership independently.

Official references: [WM_QUERYENDSESSION](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-queryendsession), [WM_ENDSESSION](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-endsession), [SetWindowSubclass](https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-setwindowsubclass).
