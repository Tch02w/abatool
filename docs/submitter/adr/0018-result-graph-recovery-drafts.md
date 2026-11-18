# ADR 0018: Recover result-graph edits without publishing them

## Status

Implemented in source, 2026-11-18. Store/state checks, production-client HTTP conflict checks, and WinUI build pass; native recovery buttons and complete release packaging remain unverified. Extends [ADR 0017](0017-periodic-drafts-and-system-session-end.md).

## Decision

- Add disk-only checkpoint participants to `WorkbenchSession`. The UI thread captures immutable values before returning background write tasks. One participant's failure does not prevent other checkpoints from being attempted. No participant invokes backend save or solver actions.
- Store the formal base, edited graph, selected node, and checked targets in `%LOCALAPPDATA%/AbaqusTools/result-graph-draft.json`. This is JSON metadata containing paths, not an ODB copy. Preserve incomplete strings; enforce 256 nodes, a valid forest, bounded strings and a 4 MiB file limit. Do not store credentials or job runtime state.
- Offer recovery only after the formal graph loads. Automatic eligibility requires the same runtime descriptor path and the same base schema/revision/content, canonicalized by node ID. A changed revision, same-revision changed content, or another runtime context blocks recovery. Viewing/copying the draft and preserving a separate copy remain available.
- Restoring affects only the editor. It retains the formal revision and remains unsaved. The normal backend save API still rejects a revision conflict if the formal graph changes after the eligibility check. Generate actions remain unavailable until normal save succeeds.
- Preserve unreadable or unresolved originals. The explicit preserve-and-ignore action flushes a unique JSON copy before clearing the active checkpoint. Reloading after confirmed discard does the same; periodic checkpoint capture pauses during the archive/reload interval so a timer cannot recreate the discarded draft. Failure leaves the current editor and active original recoverable.
- Writers are ordered, use immutable serialized captures, skip unchanged content, and replace flushed temporary files. This provides the same bounded session-end behavior as other checkpoints, without a network wait.

## Verification and limits

`ResultGraphDraftChecks.cs` tests round-trip raw fields, immutable capture, context/revision/content checks, canonical ordering, malformed forest rejection, 256-node recovery, archive failure, byte-preserved normal/corrupt archives, retry and unchanged writes. The `--graph-draft-api` mode uses the production client against an isolated real HTTP backend: a local checkpoint does not publish a graph, another edit creates a conflict, and a stale save cannot overwrite it or delete the local draft.

This does not establish native mouse/keyboard recovery, power-loss guarantees, automatic conflict merging, or postprocessing-dialog recovery. Conflicting drafts remain visible/copyable and preservable, rather than being silently rebased onto another graph. Existing complete installer candidates do not contain this change until rebuilt.
