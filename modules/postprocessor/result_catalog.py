"""Qt-free result classification, catalog, and lightweight preview helpers."""

from __future__ import annotations

import csv
import os
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from .result_assets import ASSET_MANIFEST_NAME, resolve_group_member_asset

VARIABLE_LABELS = {
    "PILE_U_MAG": "桩身位移大小",
    "PILE_CON_S_MISES": "桩身混凝土 Mises 应力",
    "PILE_STEEL_S_MISES": "钢管/型钢 Mises 应力",
    "PILE_CON_DAMAGET": "桩身混凝土拉伸损伤",
    "PILE_CON_DAMAGEC": "桩身混凝土压缩损伤",
    "SOIL_PEEQ_XZ": "土体等效塑性应变切片",
    "SOIL_PEMAG_XZ": "土体塑性应变大小切片",
    "SOIL_S33_XZ": "土体竖向应力切片",
    "SOIL_S_MISES_XZ": "土体 Mises 应力切片",
    "REBAR_LONG_S_MISES_UNDEFORMED": "纵筋 Mises 应力",
    "REBAR_LONG_S11_UNDEFORMED": "纵筋轴向应力 S11",
}

FILE_DESCRIPTIONS = {
    "summary.xlsx": ("综合汇总", "推荐入口：可直接在 Excel 中查看主要数据表"),
    "timeline_alignment.csv": ("荷载与位移", "Step、帧号、增量与总时间的对照表"),
    "load_point_raw.csv": ("荷载与位移", "加载点的原始荷载和位移全过程"),
    "load_resistance_processed.csv": (
        "荷载分担",
        "推荐使用：桩顶反力、各根键承载力、根键合力与平均值、桩侧摩阻及平衡余量，统一为 kN",
    ),
    "contact_history_raw.csv": (
        "根键历程输出",
        "从 ODB History Output 对齐到加载帧的根键和桩—土接触原始有符号力，单位 N",
    ),
    "contact_history_sources.json": (
        "配置和说明",
        "根键与桩—土接触历程列对应的 Abaqus History Output 来源",
    ),
    "load_resistance_notes.json": (
        "荷载分担",
        "处理后荷载分担表的单位、符号约定、计算公式和使用注意事项",
    ),
    "load_resistance_sharing.png": (
        "荷载分担",
        "桩顶、各层根键合力、桩侧摩阻及其余承载分量曲线",
    ),
    "damage_scan.csv": ("模型状态与损伤", "损伤变量随正式加载过程的扫描结果"),
    "pile_total_axial_force_time_aligned.csv": (
        "桩轴力",
        "桩身总轴力：混凝土/钢管自由体力与纵筋轴力之和",
    ),
    "pile_total_force_moment_time_aligned.csv": (
        "桩弯矩",
        "桩身总弯矩沿深度分布，包含混凝土/钢管、纵筋及合计值",
    ),
    "pile_bending_moment_maxima.csv": (
        "桩弯矩",
        "各加载帧的最大弯矩及其所在深度",
    ),
    "concrete_axial_force_time_aligned.csv": (
        "桩轴力",
        "混凝土/钢管自由体轴力沿深度分布",
    ),
    "rebar_section_diagnostics.csv": (
        "桩轴力",
        "每个 Free Body Cut 的纵筋截面力、交叉单元数量及轴力平衡诊断",
    ),
    "freebody_last_raw.csv": ("桩轴力", "自由体切片原始结果"),
    "rebar_element_stress_force_timehistory.csv": (
        "钢筋结果",
        "逐钢筋单元的应力、轴力及时间历程，文件通常较大",
    ),
    "rebar_force_by_element_level_timehistory.csv": (
        "钢筋结果",
        "按钢筋单元高度汇总的轴力时间历程",
    ),
    "rebar_metadata.json": ("钢筋结果", "钢筋材料、截面及空间范围说明"),
    "metadata.json": ("配置和说明", "本次 ODB、Step、帧和集合等提取说明"),
    "job_config.json": ("配置和说明", "本次提取使用的完整任务配置"),
    "host_postprocess_manifest.json": ("配置和说明", "宿主机后处理生成文件清单"),
    "abaqus_worker.log": ("运行日志", "该 ODB 的 Abaqus 提取日志"),
}

RECOMMENDED_NAMES = {
    "summary.xlsx",
    "load_point_raw.csv",
    "load_resistance_processed.csv",
    "load_resistance_sharing.png",
    "pile_total_axial_force_time_aligned.csv",
    "pile_total_force_moment_time_aligned.csv",
    "pile_bending_moment_maxima.csv",
}

SECTION_TABS = (
    ("common", "常用"),
    ("data", "数据"),
    ("plots", "曲线图"),
    ("contours", "云图"),
    ("animations", "动画"),
    ("info", "说明与日志"),
    ("all", "全部"),
)


@dataclass(frozen=True)
class ResultRecord:
    path: Path
    use_case: str
    description: str
    recommended: bool = False
    section: str = ""
    size: int = -1
    mtime_ns: int = 0
    error: str = ""
    internal: bool = False
    is_directory: bool = False


def _variable_from_path(path: Path) -> str:
    upper_parts = [part.upper() for part in path.parts]
    upper_stem = path.stem.upper()
    for variable in VARIABLE_LABELS:
        if variable in upper_parts or upper_stem.startswith(variable):
            return variable
    return ""


def classify_result(path: Path) -> ResultRecord:
    """Translate an internal result filename into a user-facing purpose."""

    name = path.name.casefold()
    if name in FILE_DESCRIPTIONS:
        use_case, description = FILE_DESCRIPTIONS[name]
        return ResultRecord(path, use_case, description, name in RECOMMENDED_NAMES)

    suffix = path.suffix.casefold()
    parents = {part.casefold() for part in path.parts}
    variable = _variable_from_path(path)
    variable_label = VARIABLE_LABELS.get(variable, variable or "场变量")
    transparent = any(part.endswith("_transparent") for part in parents)

    if suffix == ".gif" or "animations" in parents:
        return ResultRecord(
            path,
            "动画",
            f"{variable_label}的完整正式加载过程动画",
            True,
        )
    if suffix == ".png" and "plots" in parents:
        if "load_resistance" in name:
            return ResultRecord(path, "荷载分担", "桩顶、根键、桩侧摩阻及其余承载分量曲线", True)
        if "axial_force" in name:
            return ResultRecord(path, "桩轴力", "桩身轴力沿深度分布曲线", True)
        if "bending_moment" in name:
            return ResultRecord(path, "桩弯矩", "桩身弯矩沿深度分布曲线", True)
        return ResultRecord(path, "曲线图", "后处理生成的结果曲线", True)
    if suffix == ".png" and (
        "frames" in parents
        or "contours" in parents
        or "frames_transparent" in parents
        or "contours_transparent" in parents
    ):
        kind = "透明背景云图" if transparent else "Abaqus 原始云图"
        return ResultRecord(path, "云图", f"{variable_label}；{kind}")
    if suffix == ".csv":
        if "rebar" in parents:
            return ResultRecord(path, "钢筋结果", "钢筋应力、内力或高度汇总数据")
        if "freebody" in parents:
            return ResultRecord(path, "桩轴力与弯矩", "自由体切片及桩身内力数据")
        if "data" in parents:
            return ResultRecord(path, "荷载与位移", "加载历程或帧对照数据")
        return ResultRecord(path, "其他表格数据", "可用 Excel 打开的 CSV 数据")
    if suffix == ".xlsx":
        return ResultRecord(path, "综合汇总", "可直接使用的 Excel 工作簿", True)
    if suffix in {".json", ".ndjson"}:
        return ResultRecord(path, "配置和说明", "配置、元数据或处理清单")
    if suffix in {".log", ".rpy", ".txt"}:
        return ResultRecord(path, "运行日志", "运行记录或诊断信息")
    if suffix in {".png", ".jpg", ".jpeg"}:
        return ResultRecord(path, "其他图片", "结果图片")
    return ResultRecord(path, "其他文件", "未分类的辅助文件")


def collect_result_records(scope: Path) -> list[ResultRecord]:
    if not scope.is_dir():
        return []
    records = [
        classify_result(path)
        for path in scope.rglob("*")
        if path.is_file()
    ]
    return sorted(
        records,
        key=lambda record: (
            not record.recommended,
            record.use_case.casefold(),
            record.path.name.casefold(),
            str(record.path).casefold(),
        ),
    )


def shared_assets_for_scope(scope: Path) -> list[Path]:
    """Resolve shared ODB data referenced by one group member or batch."""

    candidates: list[Path] = []
    direct = resolve_group_member_asset(scope)
    if direct is not None:
        candidates.append(direct)
    elif scope.is_dir():
        try:
            children = [path for path in scope.iterdir() if path.is_dir()]
        except OSError:
            children = []
        for child in children:
            resolved = resolve_group_member_asset(child)
            if resolved is not None:
                candidates.append(resolved)
    unique: dict[str, Path] = {}
    for candidate in candidates:
        unique[os.path.normcase(str(candidate.resolve()))] = candidate.resolve()
    return list(unique.values())


def collect_shared_asset_records(scope: Path) -> list[ResultRecord]:
    records: list[ResultRecord] = []
    seen: set[str] = set()
    for asset in shared_assets_for_scope(scope):
        for record in collect_result_records(asset):
            if record.path.name == ASSET_MANIFEST_NAME:
                continue
            key = os.path.normcase(str(record.path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            try:
                stat = record.path.stat()
                size = stat.st_size
                mtime_ns = stat.st_mtime_ns
            except OSError:
                size = -1
                mtime_ns = 0
            records.append(
                ResultRecord(
                    record.path,
                    record.use_case,
                    record.description + "（ODB 公共数据）",
                    record.recommended,
                    result_section(record),
                    size,
                    mtime_ns,
                )
            )
    return records


def result_section(record: ResultRecord) -> str:
    """Return the primary horizontal-tab section for one result."""

    if record.section:
        return record.section
    suffix = record.path.suffix.casefold()
    parents = {part.casefold() for part in record.path.parts}
    if suffix == ".gif" or "animations" in parents:
        return "animations"
    if suffix in {".png", ".jpg", ".jpeg"} and "plots" in parents:
        return "plots"
    if suffix == ".png" and any(
        folder in parents
        for folder in (
            "frames",
            "contours",
            "frames_transparent",
            "contours_transparent",
        )
    ):
        return "contours"
    if suffix in {".csv", ".xlsx"}:
        return "data"
    if suffix in {".json", ".ndjson", ".log", ".rpy", ".txt"}:
        return "info"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "plots"
    return "other"


def record_matches_section(record: ResultRecord, section: str) -> bool:
    if section == "common":
        return record.recommended
    if section == "all":
        return True
    return result_section(record) == section


def format_file_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def preview_row_limit(path: Path) -> int:
    try:
        size = path.stat().st_size
    except OSError:
        return 12
    if size <= 1024 * 1024:
        return 50
    if size <= 20 * 1024 * 1024:
        return 25
    return 12


def read_csv_preview(
    path: Path, max_rows: int = 50
) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        rows = []
        for row_index, row in enumerate(reader):
            if row_index >= max_rows:
                break
            rows.append([str(value) for value in row])
    return [str(value) for value in header], rows


def _excel_column_index(reference: str) -> int:
    letters = ""
    for character in reference:
        if not character.isalpha():
            break
        letters += character.upper()
    index = 0
    for character in letters:
        index = index * 26 + ord(character) - ord("A") + 1
    return max(index - 1, 0)


def _excel_column_name(index: int) -> str:
    name = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def read_xlsx_preview(
    path: Path, max_rows: int = 50
) -> tuple[list[str], list[list[str]]]:
    """Read a small first-sheet preview using only the Python standard library."""

    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{main_ns}}}si"):
                shared_strings.append(
                    "".join(
                        node.text or ""
                        for node in item.iter()
                        if node.tag == f"{{{main_ns}}}t"
                    )
                )

        sheet_path = "xl/worksheets/sheet1.xml"
        if (
            "xl/workbook.xml" in archive.namelist()
            and "xl/_rels/workbook.xml.rels" in archive.namelist()
        ):
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            first_sheet = workbook.find(f".//{{{main_ns}}}sheet")
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            if first_sheet is not None:
                relationship_id = first_sheet.attrib.get(f"{{{rel_ns}}}id", "")
                for relationship in relationships.findall(
                    f"{{{package_rel_ns}}}Relationship"
                ):
                    if relationship.attrib.get("Id") != relationship_id:
                        continue
                    target = relationship.attrib.get("Target", "")
                    sheet_path = (
                        target.lstrip("/")
                        if target.startswith("/")
                        else posixpath.normpath(posixpath.join("xl", target))
                    )
                    break

        worksheet = ElementTree.fromstring(archive.read(sheet_path))
        preview_cells: list[dict[int, str]] = []
        maximum_column = 0
        dimension = worksheet.find(f"{{{main_ns}}}dimension")
        if dimension is not None:
            final_reference = dimension.attrib.get("ref", "A1").split(":")[-1]
            maximum_column = _excel_column_index(final_reference)
        for row_node in worksheet.findall(
            f".//{{{main_ns}}}sheetData/{{{main_ns}}}row"
        ):
            if len(preview_cells) >= max_rows:
                break
            values: dict[int, str] = {}
            for cell in row_node.findall(f"{{{main_ns}}}c"):
                column = _excel_column_index(cell.attrib.get("r", "A1"))
                maximum_column = max(maximum_column, column)
                value_node = cell.find(f"{{{main_ns}}}v")
                cell_type = cell.attrib.get("t", "")
                if cell_type == "inlineStr":
                    value = "".join(
                        node.text or ""
                        for node in cell.iter()
                        if node.tag == f"{{{main_ns}}}t"
                    )
                else:
                    value = "" if value_node is None else value_node.text or ""
                    if cell_type == "s" and value:
                        value = shared_strings[int(value)]
                values[column] = value
            preview_cells.append(values)
    column_count = maximum_column + 1
    headers = [_excel_column_name(index) for index in range(column_count)]
    preview_rows = [
        [values.get(index, "") for index in range(column_count)]
        for values in preview_cells
    ]
    return headers, preview_rows


__all__ = [
    "FILE_DESCRIPTIONS",
    "RECOMMENDED_NAMES",
    "SECTION_TABS",
    "VARIABLE_LABELS",
    "ResultRecord",
    "classify_result",
    "collect_result_records",
    "collect_shared_asset_records",
    "format_file_size",
    "preview_row_limit",
    "read_csv_preview",
    "read_xlsx_preview",
    "record_matches_section",
    "result_section",
    "shared_assets_for_scope",
]
