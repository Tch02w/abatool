"""Shared, readable Qt styling for the desktop application.

The visual language (palette, radii, control heights, card surfaces) is the
same one the submitter page uses; design tokens come from
``modules.common.qt_theme`` so both pages stay unified.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QMainWindow,
)

from modules.common import qt_theme as _theme


class AccidentalWheelGuard(QObject):
    """Prevent a hovered closed selector from changing a saved setting."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Wheel and isinstance(
            watched, (QComboBox, QAbstractSpinBox)
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def build_main_stylesheet() -> str:
    """Postprocessor window stylesheet: shared base plus page-specific cards."""

    return _theme.build_base_stylesheet() + _page_styles()


def _page_styles() -> str:
    return f"""
            QFrame#ppCard {{
                background: {_theme.CARD_BG};
                border: 1px solid {_theme.BORDER_SOFT};
                border-radius: {_theme.RADIUS_CARD}px;
            }}
            QFrame#ppCard QLabel,
            QFrame#ppCard QCheckBox {{
                background: transparent;
            }}
            QWidget#progressPanel {{
                background: {_theme.CARD_BG};
                border: 1px solid {_theme.BORDER_SOFT};
                border-radius: {_theme.RADIUS_CARD}px;
            }}
            QWidget#progressPanel QLabel {{
                background: transparent;
            }}
            QWidget#outputImageSettings {{
                background: {_theme.CARD_BG};
                border: 1px solid {_theme.BORDER_SOFT};
                border-radius: {_theme.RADIUS_CARD}px;
            }}
            QWidget#outputImageSettings QLabel,
            QWidget#outputImageSettings QCheckBox {{
                background: transparent;
            }}
            QWidget#sourceHeader,
            QWidget#tabsHeader {{
                background: transparent;
            }}
            QLabel#panelTitle {{
                color: {_theme.TEXT};
                font-weight: 600;
            }}
            QTabBar#groupTabs::tab {{
                min-width: 160px;
            }}
            QPlainTextEdit#ppLog {{
                background: {_theme.LOG_BG};
                color: {_theme.TEXT};
                border: 1px solid {_theme.BORDER_SOFT};
                border-radius: {_theme.RADIUS_CONTROL}px;
                padding: 6px 8px;
                font-family: {_theme.MONO_STACK};
                font-size: 12px;
                selection-background-color: {_theme.FIELD_SELECTION_BG};
                selection-color: {_theme.SELECTION_TEXT};
            }}
            QLabel#resultPreview {{
                background: {_theme.CARD_BG};
                color: {_theme.TEXT};
                border: 1px solid {_theme.BORDER_SOFT};
                border-radius: {_theme.RADIUS_CONTROL}px;
                padding: 8px;
            }}
            """


def apply_application_style(application: QApplication) -> None:
    """Use Qt's Fusion controls with one font and the shared base stylesheet."""

    application.setStyle("Fusion")
    application.setPalette(application.style().standardPalette())
    font = QFont("Microsoft YaHei UI")
    font.setPointSize(11)
    application.setFont(font)
    wheel_guard = AccidentalWheelGuard(application)
    application.installEventFilter(wheel_guard)
    application._accidental_wheel_guard = wheel_guard
    # 样式表只挂在 postprocessor 主窗口上（见 build_main_stylesheet），
    # 不污染共享的 QApplication，避免影响 submitter 页面。
    application.setStyleSheet("")


def configure_main_window(window: QMainWindow) -> None:
    """Set useful size constraints while remaining friendly to smaller screens."""

    window.setMinimumSize(1120, 700)
    screen = QApplication.primaryScreen()
    if screen is None:
        window.resize(1500, 880)
        return
    available = screen.availableGeometry()
    window.resize(min(1600, available.width()), min(950, available.height()))
