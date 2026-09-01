# ADR 0004: Separate restart computation graphs from result materialization

## Status

Accepted.

## Context

Restart dependencies describe how jobs are scheduled, while `restartjoin` describes how ODB artifacts are materialized. Showing both relationships in one graph makes a branch look as if sibling results can be joined and couples queue editing to file operations.

## Decision

The restart page displays only the computation graph. Every restart job has at most one parent, while one parent may have multiple child branches. Selecting a valid restart node can create an immutable result-materialization plan for that node's unique ancestry.

The ODB merge page owns and executes the materialization plan. It performs protected pairwise joins in ancestry order, validates every published intermediate ODB, and never includes sibling branches. Manual pairwise merge remains available as a separate mode. Empty or invalid computation nodes never enter a materialization plan.

The control plane resolves ancestry and source paths. WinUI renders the graph and plan, while the existing queue and ODB merge operation managers remain the execution authorities.

## Consequences

Users can reason about scheduling without merge-operation noise and can generate the complete result for any selected restart node. Multi-stage materialization creates intermediate verified results and may reuse them in a later cache implementation. Cross-branch comparison remains a postprocessing/result-set concern rather than an unsafe physical ODB join.
