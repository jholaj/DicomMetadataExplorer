"""Dark theme: colors via QPalette (Fusion style), details via a stylesheet."""

from PySide6.QtGui import QColor, QPalette

# COLORS
BACKGROUND_COLOR = "#15181b"
SURFACE_COLOR = "#1e2328"
SURFACE_ALT_COLOR = "#232930"
BORDER_COLOR = "#333a42"
TEXT_COLOR = "#e6e9ec"
TEXT_MUTED_COLOR = "#9aa4ad"
ACCENT_COLOR = "#3b82f6"
ACCENT_HOVER_COLOR = "#2f6fd6"
ACCENT_PRESSED_COLOR = "#265bb0"
HOVER_COLOR = "#2a313a"
SELECTED_COLOR = "#264a7a"
DISABLED_COLOR = "#3a4149"
VIEWER_BACKGROUND = "#101214"

# Status colors (always combined with a symbol or text, never color alone)
OK_COLOR = "#2fb344"
WARNING_COLOR = "#fab219"
ERROR_COLOR = "#e5484d"


def application_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.Window: BACKGROUND_COLOR,
        QPalette.WindowText: TEXT_COLOR,
        QPalette.Base: SURFACE_COLOR,
        QPalette.AlternateBase: SURFACE_ALT_COLOR,
        QPalette.ToolTipBase: SURFACE_ALT_COLOR,
        QPalette.ToolTipText: TEXT_COLOR,
        QPalette.PlaceholderText: TEXT_MUTED_COLOR,
        QPalette.Text: TEXT_COLOR,
        QPalette.Button: SURFACE_COLOR,
        QPalette.ButtonText: TEXT_COLOR,
        QPalette.BrightText: "#ffffff",
        QPalette.Highlight: SELECTED_COLOR,
        QPalette.HighlightedText: TEXT_COLOR,
        QPalette.Link: ACCENT_COLOR,
        QPalette.LinkVisited: ACCENT_COLOR,
        QPalette.Mid: BORDER_COLOR,
        QPalette.Dark: BACKGROUND_COLOR,
        QPalette.Light: HOVER_COLOR,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(TEXT_MUTED_COLOR))
    return palette


def get_application_style():
    return f"""
        /* Tree views */
        QTreeView {{
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            background-color: {SURFACE_COLOR};
            alternate-background-color: {SURFACE_ALT_COLOR};
            outline: none;
        }}
        QTreeView::item {{
            padding: 4px 6px;
        }}
        QTreeView::item:hover {{
            background-color: {HOVER_COLOR};
        }}
        QTreeView::item:selected {{
            background-color: {SELECTED_COLOR};
        }}
        QTreeView#thumbnail_tree {{
            border: none;
            background-color: {BACKGROUND_COLOR};
        }}
        QTreeView#thumbnail_tree::item {{
            padding: 3px 4px;
            border-radius: 6px;
        }}
        QTreeView#thumbnail_tree::item:selected {{
            background-color: {SELECTED_COLOR};
            border: 1px solid {ACCENT_COLOR};
        }}
        QHeaderView::section {{
            background-color: {SURFACE_ALT_COLOR};
            color: {TEXT_MUTED_COLOR};
            padding: 6px 8px;
            border: none;
            border-right: 1px solid {BORDER_COLOR};
            border-bottom: 1px solid {BORDER_COLOR};
            font-weight: bold;
        }}
        QHeaderView::section:last {{
            border-right: none;
        }}

        /* Line edit styling */
        QLineEdit {{
            padding: 7px 10px;
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            background-color: {SURFACE_COLOR};
            color: {TEXT_COLOR};
            selection-background-color: {SELECTED_COLOR};
        }}
        QLineEdit:focus {{
            border: 1px solid {ACCENT_COLOR};
        }}
        QLineEdit:read-only {{
            color: {TEXT_MUTED_COLOR};
            background-color: {BACKGROUND_COLOR};
        }}
        /* Inline editors in tables have only the row height */
        QAbstractItemView QLineEdit {{
            padding: 0px 4px;
            border: 1px solid {ACCENT_COLOR};
            border-radius: 0px;
            background-color: {SURFACE_ALT_COLOR};
        }}

        /* Standard buttons */
        QPushButton {{
            padding: 7px 16px;
            background-color: {ACCENT_COLOR};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {ACCENT_HOVER_COLOR};
        }}
        QPushButton:pressed {{
            background-color: {ACCENT_PRESSED_COLOR};
        }}
        QPushButton:disabled {{
            background-color: {DISABLED_COLOR};
            color: {TEXT_MUTED_COLOR};
        }}

        /* Report / text views */
        QTextBrowser {{
            background-color: {SURFACE_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            padding: 12px;
        }}

        /* Image tools hint */
        QLabel#image_tools_hint {{
            color: {TEXT_MUTED_COLOR};
            font-size: 12px;
        }}

        /* Labels */
        QLabel#hint_label, QLabel#muted_label, QLabel#card_key {{
            color: {TEXT_MUTED_COLOR};
        }}
        QLabel#hint_label {{
            font-size: 12px;
        }}
        QLabel#error_label {{
            color: {ERROR_COLOR};
        }}
        QLabel#warning_label {{
            color: {WARNING_COLOR};
        }}
        QLabel#content_message {{
            color: {TEXT_MUTED_COLOR};
            background-color: {VIEWER_BACKGROUND};
            padding: 24px;
        }}

        /* Overview */
        QLabel#section_title {{
            color: {TEXT_MUTED_COLOR};
            font-weight: bold;
            font-size: 12px;
            letter-spacing: 1px;
            margin-top: 10px;
        }}
        QFrame#overview_card {{
            background-color: {SURFACE_COLOR};
            border-radius: 6px;
        }}
        QLabel#issue_category {{
            color: {TEXT_MUTED_COLOR};
            font-size: 12px;
            padding-left: 8px;
            margin-top: 4px;
        }}
        QLabel#issue_label {{
            padding-left: 8px;
        }}
        QLabel#issue_label[indent="true"] {{
            padding-left: 24px;
        }}
        QLabel#issue_label[severity="ok"] {{
            color: {OK_COLOR};
        }}
        QLabel#issue_label[severity="error"] {{
            color: {ERROR_COLOR};
        }}
        QLabel#issue_label[severity="warning"] {{
            color: {WARNING_COLOR};
        }}

        /* Tab widget styling */
        QTabWidget::pane {{
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            background: {BACKGROUND_COLOR};
            top: -1px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_MUTED_COLOR};
            padding: 8px 20px;
            border: none;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:hover {{
            color: {TEXT_COLOR};
        }}
        QTabBar::tab:selected {{
            color: {TEXT_COLOR};
            border-bottom: 2px solid {ACCENT_COLOR};
        }}

        /* Toolbar styling */
        QToolBar {{
            background: {SURFACE_COLOR};
            border: none;
            border-bottom: 1px solid {BORDER_COLOR};
            spacing: 4px;
            padding: 4px 6px;
        }}
        QToolBar::separator {{
            background: {BORDER_COLOR};
            width: 1px;
            margin: 4px 6px;
        }}
        QToolButton {{
            background: transparent;
            color: {TEXT_COLOR};
            padding: 5px 10px;
            border: none;
            border-radius: 6px;
        }}
        QToolButton:hover {{
            background: {HOVER_COLOR};
        }}
        QToolButton:pressed {{
            background: {SELECTED_COLOR};
        }}

        /* Menu bar */
        QMenuBar {{
            background: {SURFACE_COLOR};
            border-bottom: 1px solid {BORDER_COLOR};
            padding: 2px 4px;
        }}
        QMenuBar::item {{
            padding: 5px 10px;
            border-radius: 4px;
            background: transparent;
        }}
        QMenuBar::item:selected {{
            background: {HOVER_COLOR};
        }}
        QMenuBar::item:pressed {{
            background: {SELECTED_COLOR};
        }}

        /* Sliders */
        QSlider::groove:horizontal {{
            height: 4px;
            background: {BORDER_COLOR};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT_COLOR};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
            background: {TEXT_COLOR};
        }}
        QSlider::handle:horizontal:hover {{
            background: {ACCENT_COLOR};
        }}

        /* Menus */
        QMenu {{
            background-color: {SURFACE_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 12px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {SELECTED_COLOR};
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDER_COLOR};
            margin: 4px 8px;
        }}

        /* Dialogs */
        QDialog {{
            background-color: {BACKGROUND_COLOR};
        }}

        /* Checkboxes */
        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {BORDER_COLOR};
            border-radius: 4px;
            background-color: {SURFACE_COLOR};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {ACCENT_COLOR};
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT_COLOR};
            border: 1px solid {ACCENT_COLOR};
        }}

        /* Combo boxes */
        QComboBox {{
            padding: 6px 10px;
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            background-color: {SURFACE_COLOR};
            color: {TEXT_COLOR};
        }}
        QComboBox:hover {{
            border: 1px solid {ACCENT_COLOR};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            selection-background-color: {SELECTED_COLOR};
        }}

        /* Tooltips */
        QToolTip {{
            background-color: {SURFACE_ALT_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            padding: 4px 8px;
        }}

        /* Status bar styling */
        QStatusBar {{
            background: {SURFACE_COLOR};
            color: {TEXT_MUTED_COLOR};
            border-top: 1px solid {BORDER_COLOR};
            padding: 4px;
        }}
        QStatusBar QLabel {{
            background: transparent;
            color: {TEXT_MUTED_COLOR};
            padding: 0px 8px;
        }}

        /* Scrollbars */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER_COLOR};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {TEXT_MUTED_COLOR};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            background: none;
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {BORDER_COLOR};
            min-width: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {TEXT_MUTED_COLOR};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            background: none;
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """
