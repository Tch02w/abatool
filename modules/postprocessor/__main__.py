"""Run the full standalone ODB postprocessor with PySide6."""

from __future__ import annotations


def run() -> int:
    """Import the heavy Qt frontend only when this entry point is invoked."""

    from .app import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
