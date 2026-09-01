# ADR 0003: Use a page-aware workbench explorer

## Status

Accepted.

## Context

The WinUI shell previously owned a fixed project tree and rebuilt it from queue snapshots. That made `MainWindow` responsible for file discovery, queue interpretation, selection, activation, and refresh timing. The same rail could not express the different tasks of job creation, queue management, job monitoring, remote resources, restart chains, ODB processing, and result browsing. Rebuilding the tree also discarded selection and expansion state and could produce visible refresh flicker.

## Decision

Create a deep `WorkbenchExplorer` module with one stable interface between the shell and each page.

- `WorkbenchExplorerHost` owns rendering, search, selection restoration, expansion restoration, and incremental node synchronization.
- `IWorkbenchExplorerAdapter` owns page-specific discovery and activation semantics and publishes immutable snapshots with stable item IDs.
- `IWorkbenchExplorerPage` is the seam used by `MainWindow` to attach the current page adapter.
- New job uses a workspace-file adapter, job queue uses a queue adapter, and job overview uses a job-monitor adapter.
- Pages not migrated yet use a compatibility project adapter until their dedicated adapters are connected.
- Single selection only changes page context. Double activation performs the page's normal navigation or load action; destructive operations remain in the main page and keep their existing confirmation rules.
- Background updates synchronize nodes by stable ID and do not enter the shell's foreground busy state.

The Python control plane remains the source of truth. The explorer may discover local files for presentation, but it does not persist queue, scheduler, remote, or operation state.

## Consequences

`MainWindow` no longer knows how a page's domain hierarchy is built. Each adapter can evolve independently while the shell provides consistent interaction, accessibility, and refresh behavior. The additional adapter boundary requires stable identifiers and explicit activation handling, but it prevents page-specific rules from leaking back into the shell.
