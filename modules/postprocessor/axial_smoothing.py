"""Export an editable display-only smoothing plot from postprocess XLSX or CSV."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

DEFAULT_SHEET = "Pile_Axial"
DEFAULT_DEPTH_COLUMN = "DepthFromGround_mm"
DEFAULT_FORCE_COLUMN = "PileTotalAxial_CompressionPositive_N"
DISPLAY_MODES = {"both", "raw", "smoothed"}
EXPORT_DPI = 300
BATCH_FIGURE_SIZE = (12.0, 10.0)


def configure_plot_font() -> None:
    """Prefer an installed CJK font so Chinese spreadsheet labels render cleanly."""

    available = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ("Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"):
        if font_name in available:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


def configure_legend_below(axis: plt.Axes, count: int) -> None:
    """Place long legends below the plot, filling each row to its real width."""

    axis.figure.set_layout_engine(None)
    labels = [line.get_label() for line in axis.get_lines() if not line.get_label().startswith("_")]
    if not labels:
        return
    axis.figure.canvas.draw()
    renderer = axis.figure.canvas.get_renderer()
    properties = font_manager.FontProperties(family=plt.rcParams["font.sans-serif"][0], size=8)
    widths = [renderer.get_text_width_height_descent(label, properties, False)[0] + 42.0 for label in labels]
    available_width = axis.figure.get_size_inches()[0] * axis.figure.dpi * 0.90
    columns = 1
    for candidate in range(1, len(labels) + 1):
        row_widths = [0.0] * candidate
        for index, width in enumerate(widths):
            row_widths[index % candidate] = max(row_widths[index % candidate], width)
        if sum(row_widths) <= available_width:
            columns = candidate
        else:
            break
    rows = (len(labels) + columns - 1) // columns
    handles, labels = axis.get_legend_handles_labels()
    # Matplotlib fills legend columns first. Reorder handles so the displayed
    # legend reads left-to-right across each row before wrapping.
    order = []
    for column in range(columns):
        for row in range(rows):
            index = row * columns + column
            if index < len(handles):
                order.append(index)
    axis.legend(
        [handles[index] for index in order],
        [labels[index] for index in order],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=columns,
        fontsize=8,
        frameon=True,
    )
    axis.figure.subplots_adjust(bottom=min(0.60, 0.11 + 0.035 * rows))


def display_flags(display_mode: str) -> tuple[bool, bool]:
    if display_mode not in DISPLAY_MODES:
        raise ValueError("display_mode must be both, raw, or smoothed")
    return display_mode in {"both", "raw"}, display_mode in {"both", "smoothed"}


def depth_plot_values(values: pd.Series, column: str) -> tuple[pd.Series, str]:
    """Convert explicitly millimetre-labelled depth columns; preserve engineering tables."""

    base = re.sub(r"\.\d+$", "", str(column)).casefold()
    if base.endswith("_mm") or "depthfromground_mm" in base:
        return values / 1000.0, "Depth (m)"
    return values, "Depth (m)"


def engineering_plot_values(values: pd.Series, column: str) -> tuple[pd.Series, str]:
    """Infer safe plot conversion from explicit units or known engineering-table names."""

    base = re.sub(r"\.\d+$", "", str(column)).casefold()
    if "_nmm" in base or base.endswith("nmm"):
        return values / 1.0e6, "Bending moment (kN·m)"
    if "弯矩" in base or "moment" in base:
        return values, "Bending moment (kN·m)"
    if base.endswith("_n") or "force_n" in base:
        return values / 1000.0, "Axial force (kN)"
    if "轴力" in base or "axial" in base or "force" in base:
        return values, "Axial force (kN)"
    return values, "Value (source unit)"


def common_value_axis_label(columns: Sequence[str]) -> str:
    labels = {engineering_plot_values(pd.Series(dtype=float), column)[1] for column in columns}
    return labels.pop() if len(labels) == 1 else "Value (mixed source units)"


def smooth(values: pd.Series, method: str, window: int) -> pd.Series:
    """Return a centred display-only smoother without extrapolation."""

    if window < 1 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer, for example 5")
    roller = values.rolling(window=window, center=True, min_periods=1)
    if method == "median":
        return roller.median()
    if method == "mean":
        return roller.mean()
    raise ValueError("method must be 'median' or 'mean'")


def smooth_in_steps(values: pd.Series, steps: Sequence[tuple[str, int]]) -> tuple[pd.Series, str]:
    """Apply one or two explicit display-only smoothing passes."""

    if not steps or len(steps) > 2:
        raise ValueError("Use one or two smoothing steps")
    result = values
    labels = []
    for method, window in steps:
        result = smooth(result, method, window)
        labels.append(f"{method}_w{window}")
    return result, "_then_".join(labels)


def export_smoothed_axial_plot(
    input_path: str | Path,
    *,
    sheet_name: str = DEFAULT_SHEET,
    depth_column: str = DEFAULT_DEPTH_COLUMN,
    force_column: str = DEFAULT_FORCE_COLUMN,
    method: str = "median",
    window: int = 5,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write a PNG and CSV beside an input table without changing it."""

    configure_plot_font()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source, encoding="utf-8-sig")
    elif source.suffix.lower() in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(source, sheet_name=sheet_name)
    else:
        raise ValueError("Input must be a .csv, .xlsx, or .xlsm file")
    missing = {depth_column, force_column}.difference(frame.columns)
    if missing:
        available = ", ".join(str(column) for column in frame.columns)
        raise KeyError(f"Missing columns: {', '.join(sorted(missing))}. Available: {available}")

    data = frame[[depth_column, force_column]].apply(pd.to_numeric, errors="coerce").dropna()
    data = data.sort_values(depth_column).reset_index(drop=True)
    if data.empty:
        raise ValueError("No numeric axial-force rows were found")
    smoothed_column = f"{force_column}_Smoothed_{method}_window{window}"
    data[smoothed_column] = smooth(data[force_column], method, window)

    target_dir = Path(output_dir).expanduser().resolve() if output_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{source.stem}_{sheet_name}_smoothed_{method}_w{window}"
    csv_path = target_dir / f"{stem}.csv"
    png_path = target_dir / f"{stem}.png"
    data.to_csv(csv_path, index=False, encoding="utf-8-sig")

    depth_values, depth_label = depth_plot_values(data[depth_column], depth_column)
    raw_values, value_label = engineering_plot_values(data[force_column], force_column)
    smooth_values, _ = engineering_plot_values(data[smoothed_column], force_column)
    figure, axis = plt.subplots(figsize=(8.6, 9.0), constrained_layout=True)
    axis.plot(raw_values, depth_values, color="#9CA3AF", linewidth=1.0, label="Raw pile total")
    axis.plot(smooth_values, depth_values, color="#15803D", linewidth=2.2, label=f"{method.title()} smoothing (window={window})")
    axis.axvline(0.0, color="black", linewidth=0.8)
    axis.invert_yaxis()
    axis.grid(True, alpha=0.25)
    axis.set_xlabel(value_label)
    axis.set_ylabel(depth_label)
    axis.legend()
    figure.savefig(png_path, dpi=EXPORT_DPI, bbox_inches="tight", pad_inches=0.08)
    plt.close(figure)
    return png_path, csv_path


def export_batch_smoothed_axial_plot(
    input_path: str | Path,
    *,
    force_columns: list[str],
    sheet_name: str = DEFAULT_SHEET,
    depth_column: str = DEFAULT_DEPTH_COLUMN,
    method: str = "median",
    window: int = 5,
    smoothing_steps: Sequence[tuple[str, int]] | None = None,
    display_mode: str = "both",
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Smooth several force columns from one table and export one comparison plot."""

    configure_plot_font()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source, encoding="utf-8-sig")
    elif source.suffix.lower() in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(source, sheet_name=sheet_name)
    else:
        raise ValueError("Input must be a .csv, .xlsx, or .xlsm file")
    if not force_columns:
        raise ValueError("At least one force column is required")
    missing = {depth_column, *force_columns}.difference(frame.columns)
    if missing:
        available = ", ".join(str(column) for column in frame.columns)
        raise KeyError(f"Missing columns: {', '.join(sorted(missing))}. Available: {available}")

    data = frame[[depth_column, *force_columns]].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=[depth_column]).sort_values(depth_column).reset_index(drop=True)
    if data.empty:
        raise ValueError("No numeric depth rows were found")
    steps = list(smoothing_steps) if smoothing_steps else [(method, window)]
    _, smoothing_label = smooth_in_steps(pd.Series([0.0]), steps)
    for column in force_columns:
        result, _ = smooth_in_steps(data[column], steps)
        data[f"{column}_Smoothed_{smoothing_label}"] = result

    target_dir = Path(output_dir).expanduser().resolve() if output_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{source.stem}_{sheet_name}_batch_smoothed_{smoothing_label}"
    csv_path = target_dir / f"{stem}.csv"
    png_path = target_dir / f"{stem}.png"
    data.to_csv(csv_path, index=False, encoding="utf-8-sig")

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    depth_values, depth_label = depth_plot_values(data[depth_column], depth_column)
    value_label = common_value_axis_label(force_columns)
    figure, axis = plt.subplots(figsize=BATCH_FIGURE_SIZE)
    show_raw, show_smooth = display_flags(display_mode)
    for index, column in enumerate(force_columns):
        color = colors[index % len(colors)]
        smoothed_column = f"{column}_Smoothed_{smoothing_label}"
        if show_raw:
            plot_values, _ = engineering_plot_values(data[column], column)
            axis.plot(plot_values, depth_values, color=color, alpha=0.25 if show_smooth else 0.9, linewidth=0.9)
        if show_smooth:
            plot_values, _ = engineering_plot_values(data[smoothed_column], column)
            axis.plot(plot_values, depth_values, color=color, linewidth=2.0, label=column)
    axis.axvline(0.0, color="black", linewidth=0.8)
    axis.invert_yaxis()
    axis.grid(True, alpha=0.25)
    axis.set_xlabel(value_label)
    axis.set_ylabel(depth_label)
    axis.set_title(f"Smoothing: {smoothing_label}; display: {display_mode}")
    if show_smooth:
        configure_legend_below(axis, len(force_columns))
    figure.savefig(png_path, dpi=EXPORT_DPI, bbox_inches="tight", pad_inches=0.08)
    plt.close(figure)
    return png_path, csv_path


def paired_depth_columns(columns: Sequence[str], force_columns: Sequence[str], depth_column: str) -> dict[str, str]:
    """Pair ``force.12`` with ``depth.12``; fall back to the base depth column."""

    available = set(columns)
    match = re.match(r"^(.*?)(\.\d+)?$", depth_column)
    depth_base = match.group(1) if match else depth_column
    pairs = {}
    for force_column in force_columns:
        suffix_match = re.search(r"(\.\d+)$", force_column)
        candidate = f"{depth_base}{suffix_match.group(1)}" if suffix_match else depth_base
        pairs[force_column] = candidate if candidate in available else depth_column
    return pairs


def export_paired_batch_smoothed_axial_plot(
    input_path: str | Path,
    *,
    force_columns: list[str],
    depth_column: str,
    sheet_name: str = DEFAULT_SHEET,
    smoothing_steps: Sequence[tuple[str, int]],
    display_mode: str = "both",
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Export curves with a distinct automatically paired depth column each."""

    configure_plot_font()
    source = Path(input_path).expanduser().resolve()
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source, encoding="utf-8-sig")
    elif source.suffix.lower() in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(source, sheet_name=sheet_name)
    else:
        raise ValueError("Input must be a .csv, .xlsx, or .xlsm file")
    pairs = paired_depth_columns([str(column) for column in frame.columns], force_columns, depth_column)
    missing = set(force_columns).difference(frame.columns)
    if missing:
        raise KeyError(f"Missing force columns: {', '.join(sorted(missing))}")
    _, smoothing_label = smooth_in_steps(pd.Series([0.0]), smoothing_steps)

    exported = []
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    figure, axis = plt.subplots(figsize=BATCH_FIGURE_SIZE)
    show_raw, show_smooth = display_flags(display_mode)
    for index, force_column in enumerate(force_columns):
        paired_depth = pairs[force_column]
        if paired_depth not in frame.columns:
            raise KeyError(f"No depth column available for {force_column}")
        curve = frame[[paired_depth, force_column]].apply(pd.to_numeric, errors="coerce").dropna()
        curve = curve.sort_values(paired_depth).reset_index(drop=True)
        if curve.empty:
            continue
        smooth_column = f"{force_column}_Smoothed_{smoothing_label}"
        curve[smooth_column], _ = smooth_in_steps(curve[force_column], smoothing_steps)
        curve = curve.rename(columns={paired_depth: f"Depth_for_{force_column}"})
        exported.append(curve)
        color = colors[index % len(colors)]
        depth_values, depth_label = depth_plot_values(curve[f"Depth_for_{force_column}"], paired_depth)
        if show_raw:
            plot_values, _ = engineering_plot_values(curve[force_column], force_column)
            axis.plot(plot_values, depth_values, color=color, alpha=0.25 if show_smooth else 0.9, linewidth=0.9)
        if show_smooth:
            plot_values, _ = engineering_plot_values(curve[smooth_column], force_column)
            axis.plot(plot_values, depth_values, color=color, linewidth=2.0, label=force_column)
    if not exported:
        raise ValueError("No numeric paired depth/force rows were found")
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{source.stem}_{sheet_name}_paired_smoothed_{smoothing_label}"
    csv_path = target_dir / f"{stem}.csv"
    png_path = target_dir / f"{stem}.png"
    pd.concat(exported, axis=1).to_csv(csv_path, index=False, encoding="utf-8-sig")
    axis.axvline(0.0, color="black", linewidth=0.8)
    axis.invert_yaxis()
    axis.grid(True, alpha=0.25)
    axis.set_xlabel(common_value_axis_label(force_columns))
    axis.set_ylabel(depth_label)
    axis.set_title(f"Paired-depth smoothing: {smoothing_label}; display: {display_mode}")
    if show_smooth:
        configure_legend_below(axis, len(force_columns))
    figure.savefig(png_path, dpi=EXPORT_DPI, bbox_inches="tight", pad_inches=0.08)
    plt.close(figure)
    return png_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a display-only smoothed pile axial-force plot from XLSX or CSV.")
    parser.add_argument("input_path", help="Path to summary.xlsx, pile axial CSV, or another compatible table")
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help=f"XLSX worksheet name; ignored for CSV (default: {DEFAULT_SHEET})")
    parser.add_argument("--method", choices=("median", "mean"), default="median")
    parser.add_argument("--window", type=int, default=5, help="Positive odd point count (default: 5)")
    parser.add_argument("--force-columns", help="Comma-separated force columns for one batch comparison plot")
    parser.add_argument("--output-dir", help="Folder for PNG and CSV; defaults to the XLSX folder")
    arguments = parser.parse_args()
    if arguments.force_columns:
        columns = [column.strip() for column in arguments.force_columns.split(",") if column.strip()]
        png, csv = export_batch_smoothed_axial_plot(
            arguments.input_path,
            force_columns=columns,
            sheet_name=arguments.sheet,
            method=arguments.method,
            window=arguments.window,
            output_dir=arguments.output_dir,
        )
    else:
        png, csv = export_smoothed_axial_plot(
            arguments.input_path,
            sheet_name=arguments.sheet,
            method=arguments.method,
            window=arguments.window,
            output_dir=arguments.output_dir,
        )
    print(f"PNG: {png}")
    print(f"CSV: {csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
