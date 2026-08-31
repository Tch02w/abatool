"""PySide6 import seam shared by the unified desktop product."""

from __future__ import annotations

try:  # pragma: no cover - depends on the user's environment
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as pyside_error:  # pragma: no cover - environment dependent
    raise ImportError(
        "Abaqus Tools 需要 PySide6，且不支持回退到其他 Qt 绑定。"
        "请在项目虚拟环境中安装依赖：uv sync --group dev。"
    ) from pyside_error

Signal = QtCore.Signal
Slot = QtCore.Slot
QT_BINDING = "PySide6"


__all__ = ["QT_BINDING", "QtCore", "QtGui", "QtWidgets", "Signal", "Slot"]
