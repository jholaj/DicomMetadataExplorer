from constants import (
    BACKGROUND_COLOR,
    TEXT_COLOR,
    BUTTON_COLOR,
    BUTTON_HOVER_COLOR,
    BUTTON_CHECKED_COLOR,
    VERTICAL_LINE_COLOR,
)


def get_application_style():
    return f"""
        QMainWindow, QWidget {{
            background-color: {BACKGROUND_COLOR};
            color: {TEXT_COLOR};
        }}
        QTreeWidget {{
            border: 1px solid #444444;
            border-radius: 4px;
            background-color: #2d2d2d;
        }}
        QTreeWidget::item {{
            padding: 4px;
            color: {TEXT_COLOR};
        }}
        QTreeWidget::item:alternate {{
            background-color: #333333;
        }}
        QLineEdit {{
            padding: 6px;
            border: 1px solid #444444;
            border-radius: 4px;
            background-color: #2d2d2d;
            color: {TEXT_COLOR};
        }}
        /* Standard buttons */
        QToolBar QPushButton, QDialog QPushButton {{
            padding: 6px 12px;
            background-color: {BUTTON_COLOR};
            color: {TEXT_COLOR};
            border: none;
            border-radius: 4px;
        }}
        QToolBar QPushButton:hover, QDialog QPushButton:hover {{
            background-color: {BUTTON_HOVER_COLOR};
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
        QTabWidget::pane {{
            border: 1px solid #444444;
            background: {BACKGROUND_COLOR};
        }}
        QTabBar::tab {{
            background: #2d2d2d;
            color: {TEXT_COLOR};
            padding: 8px 12px;
            border: 1px solid #444444;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background: {BACKGROUND_COLOR};
        }}
        QToolBar {{
            background: #2d2d2d;
            border: none;
            spacing: 3px;
            padding: 3px;
        }}
        QStatusBar {{
            background: #2d2d2d;
            color: {TEXT_COLOR};
        }}
        /* Horizontal line */
        QFrame[frameShape="4"] {{      /* HLine */
            background-color: {VERTICAL_LINE_COLOR};
            border: none;
        }}
    """
