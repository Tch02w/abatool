"""Single Qt binding compatibility seam for the unified desktop product."""

from __future__ import annotations

try:  # pragma: no cover - depends on the user's environment
    from PySide6 import QtCore, QtGui, QtWidgets

    Signal = QtCore.Signal
    Slot = QtCore.Slot
    QT_BINDING = "PySide6"
except ImportError:  # pragma: no cover - depends on the user's environment
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets

        Signal = QtCore.pyqtSignal
        Slot = QtCore.pyqtSlot
        QT_BINDING = "PyQt6"
    except ImportError as pyqt_error:
        raise ImportError(
            "未安装 Qt 绑定。请先安装 PySide6 或 PyQt6。"
        ) from pyqt_error


__all__ = ["QT_BINDING", "QtCore", "QtGui", "QtWidgets", "Signal", "Slot"]
