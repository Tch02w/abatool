# ADR 0008: Reserve shutdown across all managed background work

## Status

Accepted, 2026-11-18. Native close interaction and the full migration shutdown contract remain pending.

## Problem

The host may terminate its owned backend process tree after receiving an idle ODB merge/upgrade response. That response did not account for local solver execution, queue dispatch, postprocessing, compatibility checks, indexing, SFTP transfers or remote job observation. A terminal operation status can also precede its worker's final persistence or cleanup.

## Decision

Retain the authenticated `POST /api/v1/odb-upgrade-shutdown-check` route for older clients. Its response now includes `scope: all-workers-v1`. Only a response with that scope, schema 1, `safeToStop: true` and an empty operations list authorizes the new host to end an owned backend. An older response, failed request or active work leaves the backend and descriptor available for reattachment.

Reserve the nine managers under a fixed lock order: result batch, merge, upgrade, local queue, postprocessing, compatibility, result indexing, remote transfer, remote job. First inspect all managers without reserving; reserve all only when every check succeeds. A failed check must not disable later submissions to an otherwise idle manager. This preserves the batch-to-merge lock order.

The five in-memory operation managers share `OperationShutdownGuard`. Both nonterminal snapshots and unfinished futures prevent shutdown. A separate admission flag rejects new submissions without bypassing the manager's normal executor cleanup. Local queue activity, an in-flight dispatch pass and live job threads also prevent shutdown. Local launch checks dispatch state again and fences persisted STARTING, worker registration and launch together; stopping during dependency selection cannot launch another job afterward.

## Boundaries

This is a managed-worker lifetime fence, not the complete Prepare/Commit/Abort application-close protocol. It does not add durable recovery to local/remote jobs or other in-memory operations. The current host still requests cancellation of tracked compatibility/index/postprocess/merge/batch work on disposal; final confirmation, retain-versus-stop choices, page draft persistence and native close interactions require separate work. Remote solver processes are never killed by this check.

The check does not discover or terminate unrelated user processes. Synchronous settings edits, SSH commands and external file changes are outside this manager fence; the complete application close protocol must coordinate these separately. A lost successful reservation can leave an idle backend refusing new submissions; this favors safety and requires a later explicit close/reconnect policy.

## Evidence

`tests/control_plane/test_shutdown_guard.py` covers a running local job, persistence after terminal status, stop during dispatch, five worker-completion gaps, postprocess cancellation cleanup, an active transfer and admission after reservation. These use controlled test runners, never an Abaqus solver or real SSH server. `tests/winui_host/Program.cs` checks owned helper process and descriptor lifetime, including old and malformed replies. Current executed results are recorded in [TASK-002](../../08-handoff/ACTIVE_TASKS/TASK-002-migration.md).
