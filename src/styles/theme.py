# COLORS
BACKGROUND_COLOR = "#1e1e1e"
TEXT_COLOR = "#ffffff"
BUTTON_COLOR = "#0078d4"
BUTTON_HOVER_COLOR = "#106ebe"
BUTTON_CHECKED_COLOR = "#141414"
VERTICAL_LINE_COLOR = "#444444"
ACCENT_COLOR = "#0078d4"
DISABLED_COLOR = "#666666"

def get_application_style():
    return f"""
        /* General application styling */
        QMainWindow, QWidget {{
            background-color: {BACKGROUND_COLOR};
            color: {TEXT_COLOR};
            font-family: "Segoe UI", sans-serif;
            font-size: 14px;
        }}

        /* Tree widget styling */
        QTreeWidget {{
            border: 1px solid {VERTICAL_LINE_COLOR};
            border-radius: 4px;
            background-color: #2d2d2d;
        }}
        QTreeWidget::item {{
            padding: 6px;
            color: {TEXT_COLOR};
        }}
        QTreeWidget::item:hover {{
            background-color: #3a3a3a;
        }}
        QTreeWidget::item:selected {{
            background-color: {ACCENT_COLOR};
            color: {TEXT_COLOR};
        }}
        QTreeWidget::item:alternate {{
            background-color: #333333;
        }}

        /* Line edit styling */
        QLineEdit {{
            padding: 6px;
            border: 1px solid {VERTICAL_LINE_COLOR};
            border-radius: 4px;
            background-color: #2d2d2d;
            color: {TEXT_COLOR};
        }}
        QLineEdit:focus {{
            border: 1px solid {ACCENT_COLOR};
        }}

        /* Standard buttons */
        QPushButton {{
            padding: 8px 16px;
            background-color: {BUTTON_COLOR};
            color: {TEXT_COLOR};
            border: none;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {BUTTON_HOVER_COLOR};
        }}
        QPushButton:pressed {{
            background-color: {BUTTON_CHECKED_COLOR};
        }}
        QPushButton:disabled {{
            background-color: {DISABLED_COLOR};
            color: #999999;
        }}

        /* Thumbnail items */
        QWidget#thumbnail_panel QPushButton {{
            padding: 0px;
            margin: 0px;
            border: none;
            background-color: transparent;
        }}
        QWidget#thumbnail_panel QPushButton:hover {{
            background-color: {BUTTON_HOVER_COLOR};
        }}
        QWidget#thumbnail_panel QPushButton:checked {{
            background-color: {BUTTON_CHECKED_COLOR};
        }}

        /* Tab widget styling */
        QTabWidget::pane {{
            border: 1px solid {VERTICAL_LINE_COLOR};
            background: {BACKGROUND_COLOR};
        }}
        QTabBar::tab {{
            background: #2d2d2d;
            color: {TEXT_COLOR};
            padding: 8px 16px;
            border: 1px solid {VERTICAL_LINE_COLOR};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:hover {{
            background: #3a3a3a;
        }}
        QTabBar::tab:selected {{
            background: {BACKGROUND_COLOR};
            border-bottom: 2px solid {ACCENT_COLOR};
        }}

        /* Toolbar styling */
        QToolBar {{
            background: #2d2d2d;
            border: none;
            spacing: 4px;
            padding: 4px;
        }}
        QToolBar::separator {{
            background: {VERTICAL_LINE_COLOR};
            width: 1px;
            margin: 4px;
        }}

        /* Status bar styling */
        QStatusBar {{
            background: #2d2d2d;
            color: {TEXT_COLOR};
            padding: 4px;
        }}

        /* Study separators */
        QFrame#study_separator {{
            background-color: {VERTICAL_LINE_COLOR};
            border: none;
        }}

        /* Scrollbars */
        QScrollBar:vertical {{
            background: {BACKGROUND_COLOR};
            width: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: #444444;
            min-height: 20px;
            border-radius: 6px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            background: {BACKGROUND_COLOR};
            height: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: #444444;
            min-width: 20px;
            border-radius: 6px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """
