# ADR 0007: Durable result batches belong to the control plane

## Status

Accepted for implementation. Native workflow and real multi-stage model acceptance remain pending.

## Context

The former WinUI batch runner owned the immutable plan, completed-target list and shared-prefix cache in memory. Durable single merges could survive backend restarts, while the encompassing batch could not recover its position. A UI process must not decide to replay an uncertain file operation.

## Decision

The control plane reconstructs plans from a graph revision and selected targets, or compares a restart preview against a fresh authoritative plan. It freezes options and compiles separate ancestry paths into unique stages. Only identical ancestral prefixes share work; sibling ODBs are never merged together.

The complete batch and every stage submission intent are checkpointed before side effects. A deterministic child request ID connects each stage to the durable single-merge manager. Recovery only queries an already-submitted child; missing or interrupted records stop continuation. Confirmed successful children may be recovered across the gap before a batch checkpoint, after file validation. Backend restart pauses batches; an explicit resume validates sources and all previously completed results before advancing.

Source identity uses metadata and bounded content samples. Intermediate results and receipts use complete SHA256 identities. This deliberately avoids hashing every multi-GB source during synchronous admission; the limitation is documented. Single-step content verification and source protection remain in place.

Shared `OperationJournal` owns SQLite/checkpoint mechanics, while merge and batch validators remain separate and the existing merge schema is unchanged. Shutdown reserves batch, merge, then upgrade locks in that fixed order. New work is blocked if any journal cannot be trusted or written.

## Consequences

WinUI submits one batch and observes it; navigation does not govern execution. Stop covers all remaining stages. Recovery has conservative boundaries: a submission intent with missing child history requires manual investigation even when the child may never have started. Full-file validation adds I/O, but poll requests do not write checkpoints. The old C# runner is retained as a migration reference, not the production authority. These changes do not establish durable recovery for all other application tasks.
