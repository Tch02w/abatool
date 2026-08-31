from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTreeWidget,
)

from modules.postprocessor import comparison_groups as comparison_groups_module
from modules.postprocessor.app import MainWindow
from modules.postprocessor.models import OdbScan
from modules.postprocessor.naming import natural_sort_key, parse_odb_name
from modules.postprocessor.postprocessor_page import PostProcessorPage
from modules.postprocessor.ui_style import (
    AccidentalWheelGuard,
    apply_application_style,
)


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_has_a_result_browser_launch_button() -> None:
    application()
    window = MainWindow()
    button = window.findChild(QPushButton, "resultBrowserButton")
    assert button is window.result_browser_button
    assert button.text() == "结果浏览器"
    folder_card = button.parentWidget()
    assert folder_card is not None
    assert folder_card.parentWidget() is window.centralWidget()
    window.close()


def test_completed_odb_output_is_submitted_for_incremental_indexing(
    tmp_path: Path, monkeypatch
) -> None:
    application()
    window = MainWindow()
    output = (
        tmp_path
        / "AbaqusODBPostProcessor_Results"
        / "组A"
        / "20260724_120000"
        / "GJA-1-R_U100D"
    )
    output.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(
        window.result_index_coordinator,
        "enqueue_incremental",
        lambda time_directory, scope: calls.append(
            (Path(time_directory), Path(scope))
        ),
    )

    window._append_log(f"INDEX_INCREMENTAL|{output}")

    assert calls == [(output.parent.resolve(), output.resolve())]
    window.close()


def make_scan(path: Path) -> OdbScan:
    return OdbScan(
        path=path,
        steps=["Load-U", "Load-V"],
        assembly_node_sets=["SET-LOAD"],
        assembly_element_sets=[
            "SET-PILE", "SET-PILE_CON", "SET-KEY", "SET-SOIL_CUT", "SET-REBAR"
        ],
        field_outputs=["U", "S", "PEMAG"],
    )


def test_filename_metadata_and_load_direction() -> None:
    info = parse_odb_name("GJA-1-R_U100D.odb")
    assert info.sample_id == "GJA-1"
    assert info.scheme == "A方案-钢筋混凝土"
    assert info.reinforced is True
    assert info.condition == "U100D"
    assert info.load_direction == "3"
    assert info.up_displacement_mm == 100.0
    assert info.rebar_diameter_mm == 22.0

    info = parse_odb_name("GJA-20-R_U40D_V20D_miu03.odb")
    assert info.condition == "U40D_V20D"
    assert info.parameter_tags == ("miu03",)
    assert info.load_direction == "1+3"
    assert info.rebar_diameter_mm == 32.0

    info = parse_odb_name("GJA-32_V40D-old.odb")
    assert info.condition == "V40D"
    assert info.load_direction == "1"
    assert info.is_old is True


def test_d_series_diameters() -> None:
    assert parse_odb_name("D800-R_U100D.odb").rebar_diameter_mm == 22.0
    assert parse_odb_name("D1000-R_U100D.odb").rebar_diameter_mm == 28.0
    assert parse_odb_name("D1400_17-R_U40D_V20D.odb").rebar_diameter_mm == 32.0


def test_odb_names_use_natural_numeric_order() -> None:
    names = [
        "GJA-19-R_U100D.odb",
        "GJA-2-R_U100D.odb",
        "GJA-10-R_U100D.odb",
        "GJA-1-R_U100D.odb",
    ]
    assert sorted(names, key=natural_sort_key) == [
        "GJA-1-R_U100D.odb",
        "GJA-2-R_U100D.odb",
        "GJA-10-R_U100D.odb",
        "GJA-19-R_U100D.odb",
    ]


def test_condition_categories_are_browse_only_and_real_groups_are_preserved(
    tmp_path: Path,
) -> None:
    application()
    window = MainWindow()
    window.state_path = tmp_path / "project_state.json"
    folder = tmp_path / "odb"
    folder.mkdir()
    first = make_scan(folder / "GJA-1-R_U40D_V20D.odb")
    second = make_scan(folder / "GJA-2-R_U40D_V20D_miu03.odb")
    third = make_scan(folder / "GJA-4-R_U100D.odb")
    window._load_folder_state(str(folder))
    first_path = str(first.path.resolve())
    window.groups = {
        "legacy": {
            "name": "工况-U40D_V20D",
            "members": [first_path],
            "legend_overrides": {},
            "auto_condition": "U40D_V20D",
        },
        "manual": {
            "name": "人工对比组",
            "members": [first_path],
            "legend_overrides": {},
        },
    }
    window._populate([first, second, third])

    assert set(window.groups) == {"manual"}
    assert set(window.condition_categories) == {"U40D_V20D", "U100D"}
    assert len(window.condition_categories["U40D_V20D"]) == 2
    assert window.group_tree.selectionMode() == QAbstractItemView.ExtendedSelection
    all_root = window.group_tree.topLevelItem(0)
    categories_root = window.group_tree.topLevelItem(1)
    assert window.group_tree.topLevelItemCount() == 2
    assert all_root.text(0) == "全部 ODB"
    assert categories_root.text(0) == "按工况分类（仅浏览）"
    assert window.group_tabs.count() == 2
    assert window.group_tabs.tabText(0) == "全部配置"
    assert window.group_tabs.tabText(1) == "人工对比组"
    assert window.group_tabs.tabData(1) == "manual"
    assert categories_root.childCount() == 2
    assert window.group_tree.columnCount() == 1
    assert all_root.child(0).data(0, Qt.UserRole + 3) is None

    window.group_tree.setCurrentItem(categories_root.child(0))
    assert window._scope_groups("current") == []
    category_odb = categories_root.child(0).child(0)
    window._source_tree_item_activated(category_odb)
    category_plan = window._scope_groups("current")
    assert len(category_plan) == 1
    assert category_plan[0]["standalone"] is True
    assert category_plan[0]["members"] == [window.group_tree.odb_path(category_odb)]

    first_row = window.rows_by_path[first_path]
    third_row = window.rows_by_path[str(third.path.resolve())]
    assert first_row["direction"].currentText().startswith("自动")
    assert window._job_payload(first_row, tmp_path)["load_direction"] == "1+3"
    assert first_row["diameter"].value() == 22.0
    assert window._job_payload(third_row, tmp_path)["load_direction"] == "3"
    assert third_row["diameter"].value() == 28.0
    assert [
        first_row["direction"].itemText(index)
        for index in range(first_row["direction"].count())
    ] == ["X方向", "Z方向", "XZ方向", "自动（XZ方向）"]
    window.close()


def test_wheel_guard_blocks_closed_selectors() -> None:
    guard = AccidentalWheelGuard()
    event = QEvent(QEvent.Wheel)
    assert guard.eventFilter(QComboBox(), event) is True
    assert guard.eventFilter(QSpinBox(), QEvent(QEvent.Wheel)) is True


def test_application_uses_one_font_size_and_native_control_shapes() -> None:
    app = application()
    apply_application_style(app)
    window = MainWindow()
    host = window.centralWidget()
    widgets = [
        QLabel("正文", host),
        QLabel("标题", host),
        QLabel("提示", host),
        QPushButton("按钮", host),
        QLineEdit(host),
        QComboBox(host),
        QSpinBox(host),
        QTableWidget(host),
        QTreeWidget(host),
        QPlainTextEdit(host),
    ]
    widgets[1].setProperty("role", "title")
    widgets[2].setProperty("role", "hint")
    for widget in widgets:
        widget.ensurePolished()
    # 与 submitter 页面一致：所有控件按样式表统一渲染为 12px。
    assert {widget.font().pixelSize() for widget in widgets} == {12}
    stylesheet = window.styleSheet()
    assert stylesheet
    # 与 submitter 页面共享同一套设计令牌，保证两个页面风格统一。
    for token in ("#2563eb", "#f3f6fa", "QPushButton", "QTableWidget"):
        assert token in stylesheet
    window.scan_progress.ensurePolished()
    assert window.scan_progress.minimumHeight() >= 20
    assert window.scan_progress.maximumHeight() >= 20
    # 应用级不挂样式表，避免污染共享 QApplication 上的 submitter 页面。
    assert app.styleSheet() == ""
    assert app.font().family() == "Microsoft YaHei UI"
    assert app.font().pointSize() == 11
    window.close()


def test_result_browser_keeps_a_configured_root_that_does_not_exist(
    tmp_path: Path,
) -> None:
    application()
    window = MainWindow()
    configured = tmp_path / "future-project"
    window.folder_edit.setText(str(configured))

    with patch(
        "modules.postprocessor.batch_window.ResultBrowserDialog"
    ) as browser_type:
        dialog = browser_type.return_value
        window._open_result_browser()

    assert browser_type.call_args.args[0] == (
        configured / "AbaqusODBPostProcessor_Results"
    )
    dialog.setAttribute.assert_called_once()
    window.close()


def test_embedded_page_propagates_programmatic_folder_changes(
    tmp_path: Path,
) -> None:
    application()
    page = PostProcessorPage()
    emitted_roots = []
    page.resultRootChanged.connect(emitted_roots.append)

    page.controller.folder_edit.setText(str(tmp_path))
    QTest.qWait(page._folder_change_timer.interval() + 25)

    assert emitted_roots[-1] == (
        tmp_path / "AbaqusODBPostProcessor_Results"
    ).resolve()
    page.shutdown()


def test_embedded_page_source_route_emits_once_without_debounce_duplicate(
    tmp_path: Path,
) -> None:
    application()
    page = PostProcessorPage()
    emitted_roots = []
    page.resultRootChanged.connect(emitted_roots.append)

    page.set_source_path(tmp_path / "case.odb")
    QTest.qWait(page._folder_change_timer.interval() + 25)

    assert emitted_roots == [
        (tmp_path / "AbaqusODBPostProcessor_Results").resolve()
    ]
    page.shutdown()


def test_rebar_section_controls_persist_and_drive_job_payload(
    tmp_path: Path, monkeypatch
) -> None:
    application()
    state_path = tmp_path / "project_state.json"
    monkeypatch.setattr(
        comparison_groups_module,
        "state_file",
        lambda: state_path,
    )
    window = MainWindow()

    assert window.rebar_method_selector.currentData() == "element_cut"
    legacy_index = window.rebar_method_selector.findData("legacy_interpolation")
    assert legacy_index >= 0
    assert "仅对照" in window.rebar_method_selector.itemText(legacy_index)
    assert window.expected_longitudinal_rebar_count_input.value() == 0
    assert (
        window.expected_longitudinal_rebar_count_input.specialValueText()
        == "自动（按 ODB 检测）"
    )
    assert "0 表示自动采用 ODB 检测" in (
        window.expected_longitudinal_rebar_count_input.toolTip()
    )
    assert "不校验" not in window.expected_longitudinal_rebar_count_input.toolTip()
    assert window.rebar_cut_tolerance_mm_input.value() == pytest.approx(0.0001)

    window.rebar_method_selector.setCurrentIndex(legacy_index)
    window.expected_longitudinal_rebar_count_input.setValue(24)
    window.rebar_cut_tolerance_mm_input.setValue(0.0015)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["rebar_method"] == "legacy_interpolation"
    assert saved["expected_longitudinal_rebar_count"] == 24
    assert saved["rebar_cut_tolerance_mm"] == pytest.approx(0.0015)

    folder = tmp_path / "odb"
    folder.mkdir()
    item = make_scan(folder / "GJA-1-R_U100D.odb")
    window._load_folder_state(str(folder))
    window._populate([item])
    row = window.rows_by_path[str(item.path.resolve())]
    payload = window._job_payload(row, tmp_path / "result")
    assert payload["rebar_method"] == "legacy_interpolation"
    assert payload["expected_longitudinal_rebar_count"] == 24
    assert payload["settings"]["rebar_cut_tolerance_mm"] == pytest.approx(
        0.0015
    )

    window._set_busy(True)
    assert not window.rebar_method_selector.isEnabled()
    assert not window.expected_longitudinal_rebar_count_input.isEnabled()
    assert not window.rebar_cut_tolerance_mm_input.isEnabled()
    window._set_busy(False)
    assert window.rebar_method_selector.isEnabled()
    assert window.expected_longitudinal_rebar_count_input.isEnabled()
    assert window.rebar_cut_tolerance_mm_input.isEnabled()
    window.close()

    restored = MainWindow()
    assert restored.rebar_method_selector.currentData() == "legacy_interpolation"
    assert restored.expected_longitudinal_rebar_count_input.value() == 24
    assert restored.rebar_cut_tolerance_mm_input.value() == pytest.approx(0.0015)
    restored.close()


def test_manual_direction_and_diameter_are_persisted(tmp_path: Path) -> None:
    application()
    window = MainWindow()
    window.state_path = tmp_path / "project_state.json"
    folder = tmp_path / "odb"
    folder.mkdir()
    item = make_scan(folder / "GJA-1-R_U100D.odb")
    window._load_folder_state(str(folder))
    window._populate([item])
    row = window.rows_by_path[str(item.path.resolve())]
    row["direction"].setCurrentText("X方向")
    row["diameter"].setValue(25.0)
    saved = window._serialize_row(row)
    assert saved["direction_manual"] is True
    assert saved["direction"] == "X方向"
    assert saved["diameter_manual"] is True
    assert window._job_payload(row, tmp_path)["load_direction"] == "1"
    window.close()


def test_unrecognized_direction_requires_manual_selection(tmp_path: Path) -> None:
    application()
    window = MainWindow()
    window.state_path = tmp_path / "project_state.json"
    folder = tmp_path / "odb"
    folder.mkdir()
    item = make_scan(folder / "unknown-model.odb")
    window._load_folder_state(str(folder))
    window._populate([item])
    row = window.rows_by_path[str(item.path.resolve())]
    assert row["direction"].currentText() == "（未识别）"
    with pytest.raises(ValueError, match="加载方向未识别"):
        window._job_payload(row, tmp_path)
    row["direction"].setCurrentText("Z方向")
    assert window._job_payload(row, tmp_path)["load_direction"] == "3"
    window.close()


def test_window_title_shows_only_valid_odb_root(tmp_path: Path) -> None:
    application()
    window = MainWindow()
    window.folder_edit.setText(str(tmp_path))
    assert str(tmp_path.resolve()) in window.windowTitle()
    assert "0.8" in window.windowTitle()
    window.folder_edit.setText(str(tmp_path / "missing"))
    assert str(tmp_path.resolve()) not in window.windowTitle()
    window.close()
