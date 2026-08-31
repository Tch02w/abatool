# ADR 0002: Use a native WinUI client over a local Python control plane

## Status

Accepted.

## Context

The merged PySide6 application restored the mature submitter and ODB postprocessor, but its large UI classes mixed presentation with scheduling, SSH, file, and Abaqus process concerns. The product is Windows-specific and needs a maintainable native interface without rewriting the trusted Python domain logic.

## Decision

Use C#/.NET 10 and WinUI 3 for the product UI. Keep business rules in a Python 3.14 control plane bound only to `127.0.0.1` with a random port and bearer token.

- WinUI owns views, interaction state, and versioned DTOs.
- The Python control plane is the only writer of queue, scheduler, remote, ODB, and result state.
- Long operations expose IDs, progress, logs, cancellation, structured errors, and recovery snapshots.
- The control plane must remain Qt-free.
- PySide6 remains temporarily available as a compatibility and rollback entry until release validation is complete.

## Consequences

The native frontend can evolve independently from Abaqus and Python runtime constraints. Domain behavior stays testable without a GUI, while the extra process boundary requires explicit protocol versioning, lifecycle management, and failure recovery tests.
