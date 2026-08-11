"""Small desktop GUI for one- or two-pass axial-force plot smoothing."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

from modules.common.qt_compat import QtCore, QtGui, QtWidgets
from modules.postprocessor.axial_smoothing import (
    DEFAULT_DEPTH_COLUMN,
    DEFAULT_SHEET,
    export_batch_smoothed_axial_plot,
    export_paired_batch_smoothed_axial_plot,
)


class AxialSmoothingWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("轴力曲线双重平滑工具")
        self.resize(800, 650)
        self._all_columns: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.path_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("选择文件…")
        browse.clicked.connect(self._choose_file)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("CSV / XLSX 文件：", path_row)

        self.sheet_combo = QtWidgets.QComboBox()
        self.sheet_combo.setEditable(True)
        self.sheet_combo.setEditText(DEFAULT_SHEET)
        self.sheet_combo.currentTextChanged.connect(self._load_columns)
        form.addRow("工作表（CSV 忽略）：", self.sheet_combo)

        self.depth_combo = QtWidgets.QComboBox()
        form.addRow("深度列：", self.depth_combo)
        self.paired_depth = QtWidgets.QCheckBox("按列后缀自动配对埋深（推荐：不同桩长）")
        self.paired_depth.setChecked(True)
        self.paired_depth.setToolTip("例如“桩体轴力.12”自动使用“基础埋深.12”，而不是所有曲线共用同一埋深列。")
        form.addRow("批量埋深匹配：", self.paired_depth)
        layout.addLayout(form)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("列名筛选："))
        self.column_filter = QtWidgets.QLineEdit()
        self.column_filter.setPlaceholderText("例如：桩体轴力、V50、或任意列名片段")
        self.column_filter.textChanged.connect(self._apply_column_filter)
        filter_row.addWidget(self.column_filter, 1)
        self.axis_only = QtWidgets.QCheckBox("仅显示含“轴力”的列")
        self.axis_only.toggled.connect(self._apply_column_filter)
        filter_row.addWidget(self.axis_only)
        layout.addLayout(filter_row)

        self.column_list = QtWidgets.QListWidget()
        self.column_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        select_row = QtWidgets.QHBoxLayout()
        select_visible = QtWidgets.QPushButton("全选筛选结果")
        select_visible.clicked.connect(self._select_visible)
        select_row.addWidget(select_visible)
        select_row.addWidget(QtWidgets.QLabel("每隔"))
        self.interval_spin = QtWidgets.QSpinBox()
        self.interval_spin.setRange(1, 999)
        self.interval_spin.setValue(1)
        select_row.addWidget(self.interval_spin)
        select_row.addWidget(QtWidgets.QLabel("列选择一次"))
        select_interval = QtWidgets.QPushButton("按间隔选择")
        select_interval.clicked.connect(self._select_by_interval)
        select_row.addWidget(select_interval)
        clear_selection = QtWidgets.QPushButton("清空选择")
        clear_selection.clicked.connect(self.column_list.clearSelection)
        select_row.addWidget(clear_selection)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        layout.addWidget(QtWidgets.QLabel("待平滑的数值列（轴力 / 弯矩，可多选）："))
        layout.addWidget(self.column_list, 1)

        steps = QtWidgets.QGroupBox("平滑设置")
        step_grid = QtWidgets.QGridLayout(steps)
        step_grid.setColumnStretch(1, 1)
        step_grid.setColumnMinimumWidth(0, 64)
        step_grid.setColumnMinimumWidth(2, 38)
        self.first_method = QtWidgets.QComboBox()
        self.first_method.addItems(["median", "mean"])
        self.first_window = QtWidgets.QSpinBox()
        self.first_window.setRange(1, 99)
        self.first_window.setSingleStep(2)
        self.first_window.setValue(5)
        step_grid.addWidget(QtWidgets.QLabel("第一轮："), 0, 0)
        step_grid.addWidget(self.first_method, 0, 1)
        step_grid.addWidget(QtWidgets.QLabel("窗口："), 0, 2)
        step_grid.addWidget(self.first_window, 0, 3)

        self.second_enabled = QtWidgets.QCheckBox("启用第二轮平滑")
        self.second_enabled.toggled.connect(self._set_second_enabled)
        self.second_method = QtWidgets.QComboBox()
        self.second_method.addItems(["mean", "median"])
        self.second_window = QtWidgets.QSpinBox()
        self.second_window.setRange(1, 99)
        self.second_window.setSingleStep(2)
        self.second_window.setValue(5)
        step_grid.addWidget(self.second_enabled, 1, 0)
        step_grid.addWidget(self.second_method, 1, 1)
        step_grid.addWidget(QtWidgets.QLabel("窗口："), 1, 2)
        step_grid.addWidget(self.second_window, 1, 3)
        self._set_second_enabled(False)
        layout.addWidget(steps)

        self.output_edit = QtWidgets.QLineEdit()
        output_browse = QtWidgets.QPushButton("输出目录…")
        output_browse.clicked.connect(self._choose_output)
        output_row = QtWidgets.QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(output_browse)
        form.addRow("输出目录（可留空）：", output_row)

        self.status = QtWidgets.QLabel("选择文件后，勾选需要比较的轴力列。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        button_row = QtWidgets.QHBoxLayout()
        preview = QtWidgets.QPushButton("预览平滑图")
        preview.clicked.connect(self._preview)
        button_row.addWidget(preview)
        export = QtWidgets.QPushButton("直接导出（原始 + 平滑）")
        export.clicked.connect(self._generate)
        button_row.addWidget(export)
        layout.addLayout(button_row)

    def _choose_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择数据文件", "", "Data (*.csv *.xlsx *.xlsm)")
        if not path:
            return
        self.path_edit.setText(path)
        source = Path(path)
        self.output_edit.setText(str(source.parent / "smoothing_preview"))
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        if source.suffix.lower() in {".xlsx", ".xlsm"}:
            self.sheet_combo.addItems(pd.ExcelFile(source).sheet_names)
            index = self.sheet_combo.findText(DEFAULT_SHEET)
            self.sheet_combo.setCurrentIndex(max(index, 0))
            self.sheet_combo.setEnabled(True)
        else:
            self.sheet_combo.addItem("CSV（无工作表）")
            self.sheet_combo.setEnabled(False)
        self.sheet_combo.blockSignals(False)
        self._load_columns()

    def _load_columns(self) -> None:
        source = Path(self.path_edit.text())
        if not source.is_file():
            return
        try:
            if source.suffix.lower() == ".csv":
                frame = pd.read_csv(source, encoding="utf-8-sig", nrows=5)
            else:
                frame = pd.read_excel(source, sheet_name=self.sheet_combo.currentText(), nrows=5)
        except Exception as error:  # noqa: BLE001 - GUI must show reader errors to the user.
            self.status.setText(f"无法读取列：{error}")
            return
        columns = [str(column) for column in frame.columns]
        self.depth_combo.clear()
        self.depth_combo.addItems(columns)
        index = self.depth_combo.findText(DEFAULT_DEPTH_COLUMN)
        self.depth_combo.setCurrentIndex(max(index, 0))
        self.column_list.clear()
        self._all_columns = columns
        for column in columns:
            item = QtWidgets.QListWidgetItem(column)
            self.column_list.addItem(item)
            if "PileTotalAxial" in column:
                item.setSelected(True)
        self._apply_column_filter()
        self.status.setText(f"已读取 {len(columns)} 列；可筛选、全选或按间隔批量选择。")

    def _apply_column_filter(self) -> None:
        query = self.column_filter.text().strip().casefold()
        axis_only = self.axis_only.isChecked()
        for index in range(self.column_list.count()):
            item = self.column_list.item(index)
            name = item.text().casefold()
            item.setHidden((bool(query) and query not in name) or (axis_only and "轴力" not in item.text()))

    def _select_visible(self) -> None:
        for index in range(self.column_list.count()):
            item = self.column_list.item(index)
            if not item.isHidden():
                item.setSelected(True)

    def _select_by_interval(self) -> None:
        interval = self.interval_spin.value()
        visible = [
            self.column_list.item(index)
            for index in range(self.column_list.count())
            if not self.column_list.item(index).isHidden()
        ]
        self.column_list.clearSelection()
        for index, item in enumerate(visible):
            item.setSelected(index % interval == 0)
        self.status.setText(f"已从 {len(visible)} 个筛选结果中每隔 {interval} 列选择一次。")

    def _choose_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def _set_second_enabled(self, enabled: bool) -> None:
        self.second_method.setEnabled(enabled)
        self.second_window.setEnabled(enabled)

    @staticmethod
    def _odd(window: int) -> int:
        return window if window % 2 else window + 1

    def _generate(self) -> None:
        options = self._options()
        if options is None:
            return
        source, columns, steps = options
        try:
            exporter = export_paired_batch_smoothed_axial_plot if self.paired_depth.isChecked() else export_batch_smoothed_axial_plot
            png, csv = exporter(
                source, force_columns=columns, sheet_name=self.sheet_combo.currentText(),
                depth_column=self.depth_combo.currentText(), smoothing_steps=steps,
                output_dir=self.output_edit.text().strip() or None, display_mode="both",
            )
        except Exception as error:  # noqa: BLE001 - GUI must show generation errors to the user.
            self.status.setText(f"生成失败：{error}")
            return
        self.status.setText(f"已生成图：{png}\n已生成数据：{csv}")

    def _options(self) -> tuple[str, list[str], list[tuple[str, int]]] | None:
        columns = [item.text() for item in self.column_list.selectedItems()]
        if not columns:
            self.status.setText("请至少选择一列轴力数据。")
            return None
        source = self.path_edit.text().strip()
        if not source:
            self.status.setText("请先选择 CSV 或 XLSX 文件。")
            return None
        steps = [(self.first_method.currentText(), self._odd(self.first_window.value()))]
        if self.second_enabled.isChecked():
            steps.append((self.second_method.currentText(), self._odd(self.second_window.value())))
        return source, columns, steps

    def _preview(self) -> None:
        options = self._options()
        if options is None:
            return
        source, columns, steps = options
        dialog = PreviewDialog(
            self, source, columns, steps, self.sheet_combo.currentText(),
            self.depth_combo.currentText(), self.paired_depth.isChecked(),
            self.output_edit.text().strip() or None,
        )
        dialog.exec()


class ZoomablePreview(QtWidgets.QGraphicsView):
    """Pixmap preview with mouse-wheel zoom and left-drag panning."""

    def __init__(self, pixmap: QtGui.QPixmap) -> None:
        super().__init__()
        self._minimum_scale = 0.0
        self._at_minimum = True
        self._scene = QtWidgets.QGraphicsScene(self)
        self._item = self._scene.addPixmap(pixmap)
        self.setScene(self._scene)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.reset_view()

    def reset_view(self) -> None:
        self.resetTransform()
        self.fitInView(self._scene.itemsBoundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self._minimum_scale = self.transform().m11()
        self._at_minimum = True

    def set_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(self._item.boundingRect())
        self.reset_view()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        current = self.transform().m11()
        if event.angleDelta().y() > 0:
            self.scale(1.15, 1.15)
            self._at_minimum = False
            return
        if current <= self._minimum_scale * 1.001:
            return
        target = max(self._minimum_scale, current / 1.15)
        self.scale(target / current, target / current)
        self._at_minimum = target <= self._minimum_scale * 1.001

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        was_at_minimum = self._at_minimum
        super().resizeEvent(event)
        if was_at_minimum:
            QtCore.QTimer.singleShot(0, self.reset_view)


class PreviewDialog(QtWidgets.QDialog):
    """Interactive preview that controls its own display mode and export."""

    def __init__(self, parent, source, columns, steps, sheet, depth, paired, output_dir) -> None:
        super().__init__(parent)
        self.setWindowTitle("平滑预览（确认后再导出）")
        self.resize(1040, 820)
        self.source, self.columns, self.steps = source, columns, steps
        self.sheet, self.depth, self.paired, self.output_dir = sheet, depth, paired, output_dir
        self._temporary = tempfile.TemporaryDirectory(prefix="axial_smoothing_preview_")
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("滚轮缩放；按住左键拖动平移。选择展示方式后将即时刷新预览。"))
        modes = QtWidgets.QHBoxLayout()
        modes.addWidget(QtWidgets.QLabel("曲线展示方式："))
        self.mode_group = QtWidgets.QButtonGroup(self)
        for label, value in (("原始 + 平滑", "both"), ("仅原始", "raw"), ("仅平滑", "smoothed")):
            button = QtWidgets.QRadioButton(label)
            button.setProperty("display_mode", value)
            button.toggled.connect(self._render)
            self.mode_group.addButton(button)
            modes.addWidget(button)
            if value == "both":
                button.setChecked(True)
        modes.addStretch(1)
        layout.addLayout(modes)
        self.image = ZoomablePreview(QtGui.QPixmap())
        layout.addWidget(self.image, 1)
        self.status = QtWidgets.QLabel()
        layout.addWidget(self.status)
        controls = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton("复位视图")
        reset.clicked.connect(self.image.reset_view)
        controls.addWidget(reset)
        self.fullscreen = QtWidgets.QPushButton("全屏预览")
        self.fullscreen.clicked.connect(self._toggle_fullscreen)
        controls.addWidget(self.fullscreen)
        controls.addStretch(1)
        export = QtWidgets.QPushButton("按当前方式导出 PNG 与 CSV")
        export.clicked.connect(self._export)
        controls.addWidget(export)
        close = QtWidgets.QPushButton("返回修改")
        close.clicked.connect(self.accept)
        controls.addWidget(close)
        layout.addLayout(controls)
        QtCore.QTimer.singleShot(0, self.image.reset_view)

    def _mode(self) -> str:
        button = self.mode_group.checkedButton()
        return str(button.property("display_mode")) if button else "both"

    def _exporter(self):
        return export_paired_batch_smoothed_axial_plot if self.paired else export_batch_smoothed_axial_plot

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen.setText("全屏预览")
        else:
            self.showFullScreen()
            self.fullscreen.setText("退出全屏")
        QtCore.QTimer.singleShot(0, self.image.reset_view)

    def _render(self) -> None:
        if not hasattr(self, "image"):
            return
        try:
            png, _csv = self._exporter()(
                self.source, force_columns=self.columns, sheet_name=self.sheet,
                depth_column=self.depth, smoothing_steps=self.steps,
                output_dir=self._temporary.name, display_mode=self._mode(),
            )
            pixmap = QtGui.QPixmap(str(png))
            if pixmap.isNull():
                raise ValueError("预览图未生成")
        except Exception as error:  # noqa: BLE001 - GUI must show preview errors to the user.
            self.status.setText(f"预览失败：{error}")
            return
        self.image.set_pixmap(pixmap)
        self.status.setText("预览为临时文件；点击导出后才会写入所选输出目录。")

    def _export(self) -> None:
        try:
            png, csv = self._exporter()(
                self.source, force_columns=self.columns, sheet_name=self.sheet,
                depth_column=self.depth, smoothing_steps=self.steps,
                output_dir=self.output_dir, display_mode=self._mode(),
            )
        except Exception as error:  # noqa: BLE001 - GUI must show export errors to the user.
            self.status.setText(f"导出失败：{error}")
            return
        self.status.setText(f"已导出图：{png}\n已导出数据：{csv}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._temporary.cleanup()
        super().closeEvent(event)


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = AxialSmoothingWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
