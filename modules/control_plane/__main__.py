"""Command-line entry point for the local WinUI control plane."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from .server import ControlPlaneRuntime

LAUNCH_TOKEN_ENV = "ABAQUS_TOOLS_LAUNCH_TOKEN"


def default_descriptor_path() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        base = (
            Path(xdg_data_home).expanduser()
            if xdg_data_home
            else Path.home() / ".local" / "share"
        )
    return base / "AbaqusTools" / "runtime" / "control-plane.json"


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Abaqus Tools local control plane"
    )
    parser.add_argument(
        "--port",
        type=valid_port,
        default=0,
        help="loopback TCP port; 0 selects an available ephemeral port",
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=default_descriptor_path(),
        help="runtime descriptor JSON path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable informational HTTP request logging",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime = ControlPlaneRuntime(
        descriptor_path=args.descriptor,
        port=args.port,
        launch_token=os.environ.get(LAUNCH_TOKEN_ENV, ""),
    )
    try:
        runtime.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LAUNCH_TOKEN_ENV",
    "build_parser",
    "default_descriptor_path",
    "main",
    "valid_port",
]
