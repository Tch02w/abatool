"""Shared Qt design tokens and base stylesheet for the unified workspace.

Both domain modules (submitter and postprocessor) build their window
stylesheets on top of these tokens so the two pages stay visually unified.
Domain modules must import tokens from here instead of redefining them.
"""

from __future__ import annotations

# --- Colors ---------------------------------------------------------------

APP_BG = "#f3f6fa"
CARD_BG = "#ffffff"
LOG_BG = "#f8fafc"
TEXT = "#111827"
HINT = "#64748b"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
PRIMARY_PRESSED = "#1e40af"
LIGHT = "#e7edf6"
LIGHT_HOVER = "#d8e2ef"
LIGHT_PRESSED = "#cbd5e1"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
DANGER_PRESSED = "#991b1b"
DISABLED_BG = "#e5e7eb"
DISABLED_TEXT = "#94a3b8"
BORDER = "#c7d2e1"
BORDER_SOFT = "#dbe4ef"
FOCUS = "#60a5fa"
FIELD_BG = "#ffffff"
FIELD_MUTED_BG = "#f8fafc"
FIELD_DISABLED_BG = "#f1f5f9"
FIELD_SELECTION_BG = "#bfdbfe"
TABLE_HEADER_BG = "#edf2f8"
TABLE_GRID = "#e5e7eb"
TABLE_ALTERNATE_BG = "#f8fafc"
SELECTION_BG = "#dbeafe"
SELECTION_TEXT = "#0f172a"
TAB_BG = "#eef2f7"
TAB_TEXT = "#475569"
TOOLTIP_BG = "#0f172a"
RUNTIME_SELECTOR_FALLBACK_BG = "#e2e8f0"

# --- Geometry -------------------------------------------------------------

RADIUS_CARD = 10
RADIUS_CONTROL = 7
CONTROL_HEIGHT = 32
BUTTON_HEIGHT = 28

SCROLLBAR_BG = "#f8fafc"
SCROLLBAR_HANDLE = "#cbd5e1"
SCROLLBAR_HANDLE_HOVER = "#94a3b8"

FONT_STACK = '"Microsoft YaHei", "Segoe UI", sans-serif'
MONO_STACK = '"Cascadia Mono", Consolas, "Microsoft YaHei", monospace'


def build_base_stylesheet() -> str:
    """Domain-free control styling shared by every page of the workspace.

    Supports both button variant conventions used in the codebase:
    ``setObjectName("primary")`` (submitter) and
    ``setProperty("primary", True)`` (postprocessor).
    """

    return f"""
            QWidget {{
                background: {APP_BG};
                color: {TEXT};
                font-family: {FONT_STACK};
                font-size: 12px;
            }}
            QLabel,
            QCheckBox,
            QRadioButton {{
                background: transparent;
            }}
            QLabel[role="title"] {{
                color: {TEXT};
                font-weight: 600;
            }}
            QLabel[role="hint"] {{
                color: {HINT};
            }}
            QLabel[role="emphasis"] {{
                color: {TEXT};
                font-weight: 600;
            }}
            QDialog,
            QMessageBox {{
                background: {APP_BG};
            }}
            QPushButton {{
                background: {LIGHT};
                color: {TEXT};
                border: 1px solid transparent;
                border-radius: {RADIUS_CONTROL}px;
                min-height: {BUTTON_HEIGHT}px;
                max-height: {BUTTON_HEIGHT}px;
                padding: 0 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {LIGHT_HOVER};
            }}
            QPushButton:pressed {{
                background: {LIGHT_PRESSED};
                padding-top: 1px;
            }}
            QPushButton:disabled {{
                background: {DISABLED_BG};
                color: {DISABLED_TEXT};
                border-color: transparent;
            }}
            QPushButton#primary,
            QPushButton[primary="true"] {{
                background: {PRIMARY};
                color: #ffffff;
            }}
            QPushButton#primary:hover,
            QPushButton[primary="true"]:hover {{
                background: {PRIMARY_HOVER};
            }}
            QPushButton#primary:pressed,
            QPushButton[primary="true"]:pressed {{
                background: {PRIMARY_PRESSED};
            }}
            QPushButton#danger,
            QPushButton[danger="true"] {{
                background: {DANGER};
                color: #ffffff;
            }}
            QPushButton#danger:hover,
            QPushButton[danger="true"]:hover {{
                background: {DANGER_HOVER};
            }}
            QPushButton#danger:pressed,
            QPushButton[danger="true"]:pressed {{
                background: {DANGER_PRESSED};
            }}
            QLineEdit,
            QSpinBox,
            QDoubleSpinBox,
            QComboBox {{
                background: {FIELD_BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_CONTROL}px;
                min-height: {CONTROL_HEIGHT}px;
                max-height: {CONTROL_HEIGHT}px;
                padding: 0 8px;
                selection-background-color: {FIELD_SELECTION_BG};
            }}
            QSpinBox,
            QDoubleSpinBox {{
                padding: 0 20px 0 8px;
            }}
            QComboBox {{
                padding: 0 24px 0 8px;
            }}
            QLineEdit:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus,
            QComboBox:focus {{
                border-color: {FOCUS};
            }}
            QLineEdit:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled,
            QComboBox:disabled {{
                background: {FIELD_DISABLED_BG};
                color: {DISABLED_TEXT};
                border-color: {BORDER_SOFT};
            }}
            QSpinBox::up-button,
            QSpinBox::down-button,
            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                width: 16px;
            }}
            QSpinBox::up-button,
            QDoubleSpinBox::up-button {{
                subcontrol-position: top right;
            }}
            QSpinBox::down-button,
            QDoubleSpinBox::down-button {{
                subcontrol-position: bottom right;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                border: 0;
                border-left: 1px solid {BORDER_SOFT};
                margin: 1px 1px 1px 0;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background: {FIELD_BG};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_CONTROL}px;
                padding: 4px;
                outline: 0;
                selection-background-color: {SELECTION_BG};
                selection-color: {SELECTION_TEXT};
            }}
            QTableWidget,
            QTableView,
            QTreeWidget,
            QTreeView,
            QListWidget {{
                background: {CARD_BG};
                alternate-background-color: {TABLE_ALTERNATE_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: {RADIUS_CONTROL}px;
                gridline-color: {TABLE_GRID};
                selection-background-color: {SELECTION_BG};
                selection-color: {SELECTION_TEXT};
                outline: 0;
            }}
            QTreeWidget::item,
            QTreeView::item,
            QListWidget::item {{
                min-height: 25px;
                padding: 1px 3px;
            }}
            QTreeWidget::item:hover,
            QTreeView::item:hover,
            QListWidget::item:hover {{
                background: {FIELD_DISABLED_BG};
                color: {TEXT};
            }}
            QTreeWidget::item:selected,
            QTreeView::item:selected,
            QListWidget::item:selected {{
                background: {SELECTION_BG};
                color: {SELECTION_TEXT};
            }}
            QHeaderView::section {{
                background: {TABLE_HEADER_BG};
                color: {TEXT};
                border: 0;
                border-right: 1px solid {TABLE_GRID};
                padding: 7px 6px;
                font-weight: 600;
            }}
            QTabWidget::pane {{
                background: {CARD_BG};
                border: 1px solid {BORDER_SOFT};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {TAB_BG};
                color: {TAB_TEXT};
                border: 1px solid {BORDER_SOFT};
                padding: 7px 15px;
                min-width: 104px;
            }}
            QTabBar::tab:selected {{
                background: {CARD_BG};
                color: {PRIMARY};
                border-top: 2px solid {PRIMARY};
                border-bottom-color: {CARD_BG};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{
                background: {LIGHT};
            }}
            QGroupBox {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                margin-top: 10px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 9px;
                padding: 0 5px;
                background: {CARD_BG};
            }}
            QProgressBar {{
                background: #e2e8f0;
                color: {TEXT};
                border: 0;
                border-radius: 4px;
                min-height: 22px;
                max-height: 22px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {PRIMARY};
                border-radius: 4px;
            }}
            QPlainTextEdit,
            QTextEdit {{
                background: {CARD_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: {RADIUS_CONTROL}px;
                selection-background-color: {FIELD_SELECTION_BG};
            }}
            QMenu {{
                background: {CARD_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                padding: 3px;
            }}
            QMenu::item {{
                background: transparent;
                border: 0;
                border-radius: 3px;
                padding: 6px 26px 6px 10px;
            }}
            QMenu::item:selected {{
                background: {SELECTION_BG};
                color: {SELECTION_TEXT};
            }}
            QMenu::item:disabled {{
                color: {DISABLED_TEXT};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER_SOFT};
                margin: 3px 6px;
            }}
            QMenuBar {{
                background: {CARD_BG};
                color: {TEXT};
                border: 0;
                padding: 2px 6px;
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 5px 9px;
            }}
            QMenuBar::item:selected {{
                background: #e2e8f0;
                border-radius: 4px;
            }}
            QSplitter::handle {{
                background: {BORDER_SOFT};
            }}
            QToolTip {{
                background: {TOOLTIP_BG};
                color: #ffffff;
                border: 0;
                padding: 5px 7px;
            }}
            QScrollBar:vertical,
            QScrollBar:horizontal {{
                background: {SCROLLBAR_BG};
                border: 0;
                width: 9px;
                height: 9px;
                margin: 0;
            }}
            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {{
                background: {SCROLLBAR_HANDLE};
                border-radius: 4px;
                min-height: 24px;
                min-width: 24px;
            }}
            QScrollBar::handle:vertical:hover,
            QScrollBar::handle:horizontal:hover {{
                background: {SCROLLBAR_HANDLE_HOVER};
            }}
            QScrollBar::add-line,
            QScrollBar::sub-line {{
                width: 0;
                height: 0;
                border: 0;
                background: transparent;
            }}
            QScrollBar::add-page,
            QScrollBar::sub-page {{
                background: transparent;
            }}
            """
