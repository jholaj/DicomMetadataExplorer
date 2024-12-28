import sys
import pydicom
import numpy as np
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QLineEdit,
    QHeaderView,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QStatusBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from pathlib import Path
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Constants for UI
BACKGROUND_COLOR = "#232323"
TEXT_COLOR = "#ffffff"
BUTTON_COLOR = "#0078d4"
BUTTON_HOVER_COLOR = "#106ebe"


class ImageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create matplotlib figure
        self.figure = Figure(facecolor=BACKGROUND_COLOR)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(BACKGROUND_COLOR)
        self.ax.axis("off")

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_height = 0
        self.image_width = 0

    def display_image(self, dataset):
        self.ax.clear()
        self.ax.axis("off")

        try:
            if hasattr(dataset, "pixel_array"):
                pixel_array = dataset.pixel_array
                self.image_height, self.image_width = pixel_array.shape[:2]

                # Normalize pixel values for display
                if pixel_array.dtype != np.uint8:
                    pixel_array = (
                        (pixel_array - pixel_array.min())
                        / (pixel_array.max() - pixel_array.min())
                        * 255
                    ).astype(np.uint8)

                # Display image
                self.ax.imshow(pixel_array, cmap="gray")
                self.figure.tight_layout(pad=0)
                self.canvas.draw()
        except Exception as e:
            print(f"Error displaying image: {e}")


class MetadataViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        layout.addWidget(self.search_input)

        # Tree widget for DICOM tags
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])

        # Set resize mode for columns
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)

        self.search_input.textChanged.connect(self.filter_items)

    def filter_items(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower() for j in range(item.columnCount())
            )
            item.setHidden(not matches)

    def load_metadata(self, dataset):
        self.tree.clear()
        for elem in dataset:
            if elem.tag.group != 0x7FE0:  # Skip pixel data
                item = QTreeWidgetItem()
                tag_str = f"({elem.tag.group:04x},{elem.tag.element:04x})"
                value_str = (
                    "<binary data>"
                    if isinstance(elem.value, bytes)
                    else f"<sequence of {len(elem.value)} items>"
                    if isinstance(elem.value, pydicom.sequence.Sequence)
                    else str(elem.value)
                )

                item.setText(0, tag_str)
                item.setText(1, elem.name or "")
                item.setText(2, getattr(elem, "VR", ""))
                item.setText(3, value_str)
                self.tree.addTopLevelItem(item)


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Add actions
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.browse_file)
        toolbar.addAction(open_action)

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        layout.addWidget(self.file_path)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create metadata tab
        self.metadata_viewer = MetadataViewer()
        self.tab_widget.addTab(self.metadata_viewer, "Metadata")

        # Create image tab
        self.image_viewer = ImageViewer()
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.addWidget(self.image_viewer, alignment=Qt.AlignCenter)
        self.tab_widget.addTab(image_container, "Content")

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Set application styles
        self.apply_styles()

    def apply_styles(self):
        style_sheet = f"""
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
            QPushButton {{
                padding: 6px 12px;
                background-color: {BUTTON_COLOR};
                color: {TEXT_COLOR};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER_COLOR};
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
        """
        self.setStyleSheet(style_sheet)

    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )
        if file_name:
            self.load_dicom(file_name)

    def load_dicom(self, file_path):
        try:
            dataset = pydicom.dcmread(file_path)
            if not dataset:
                raise ValueError("No data found in DICOM file.")

            self.file_path.setText(file_path)

            # Load metadata
            self.metadata_viewer.load_metadata(dataset)

            # Display image
            if hasattr(dataset, "pixel_array"):
                self.image_viewer.display_image(dataset)

            # Update status bar
            self.status_bar.showMessage(
                f"Loaded {self.metadata_viewer.tree.topLevelItemCount()} DICOM tags"
            )

        except Exception as e:
            self.status_bar.showMessage(f"Error loading file: {str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DicomExplorer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
