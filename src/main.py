import sys
import pydicom
import numpy as np
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QLineEdit,
    QHeaderView,
    QSplitter,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from pathlib import Path
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Constants for UI
BACKGROUND_COLOR = "#232323"
TEXT_COLOR = "#ffffff"
BUTTON_COLOR = "#0078d4"
BUTTON_HOVER_COLOR = "#106ebe"
MIN_SIZE = 200
MAX_SIZE = 1400


class ImageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create matplotlib figure
        self.figure = Figure(facecolor=BACKGROUND_COLOR)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        # Add subplot
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(BACKGROUND_COLOR)
        self.ax.set_xticks([])
        self.ax.set_yticks([])

        # Size policy and dimensions
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_height = 0
        self.image_width = 0
        self.setMinimumSize(MIN_SIZE, MIN_SIZE)
        self.setMaximumSize(MAX_SIZE, MAX_SIZE)

    def display_image(self, dataset):
        self.ax.clear()
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.margins(0)

        try:
            if hasattr(dataset, "pixel_array"):
                pixel_array = dataset.pixel_array
                # Store image dimensions
                self.image_height, self.image_width = pixel_array.shape[:2]
                # Normalize pixel values for display
                if pixel_array.dtype != np.uint8:
                    pixel_array = (
                        (pixel_array - pixel_array.min())
                        / (pixel_array.max() - pixel_array.min())
                        * 255
                    ).astype(np.uint8)
                # Display image
                self.ax.imshow(
                    pixel_array,
                    cmap="gray",
                    aspect="auto",
                    extent=(0, self.image_width, 0, self.image_height),
                )
                self.figure.tight_layout(pad=0)
                self.update_size()
                self.canvas.draw()
        except Exception as e:
            print(f"Error displaying image: {e}")

    def update_size(self):
        if not (self.image_width and self.image_height):
            return

        aspect_ratio = self.image_width / self.image_height
        available_width = self.parent().width() * 0.8
        available_height = self.parent().height()

        # (landscape)
        if aspect_ratio > 1:
            new_width = min(available_width, MAX_SIZE)
            new_height = new_width / aspect_ratio
        else:  # (portrait)
            new_height = min(available_height, MAX_SIZE)
            new_width = new_height * aspect_ratio

        new_width = max(new_width, MIN_SIZE)
        new_height = max(new_height, MIN_SIZE)

        self.setFixedSize(int(new_width), int(new_height))
        self.figure.set_size_inches(new_width / 100, new_height / 100)
        self.canvas.draw()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update figure size when widget is resized
        self.figure.set_size_inches(self.width() / 100, self.height() / 100)
        self.canvas.draw()


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Metadata Explorer")

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create splitter for metadata and image
        self.splitter = QSplitter(Qt.Horizontal)

        # Left side - metadata
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        # Top bar with file selection
        top_bar = QHBoxLayout()

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")

        top_bar.addWidget(self.file_path)
        top_bar.addWidget(browse_btn)
        left_layout.addLayout(top_bar)
        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        self.search_input.textChanged.connect(self.filter_items)
        left_layout.addWidget(self.search_input)

        # Tree widget for DICOM tags
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])

        # Set resize mode for all columns
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        left_layout.addWidget(self.tree)

        # Right side - image container
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 5, 10, 10)

        # Image viewer
        self.image_viewer = ImageViewer(right_widget)
        right_layout.addWidget(self.image_viewer, alignment=Qt.AlignCenter)
        right_layout.addStretch()

        # Add widgets to splitter and layout
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)

        layout.addWidget(self.splitter)

        # Set application styles
        style_sheet = f"""
             QMainWindow, QWidget {{ background-color: {BACKGROUND_COLOR}; color: {TEXT_COLOR}; }}
             QTreeWidget {{ border: 1px solid #444444; border-radius: 4px; background-color: #2d2d2d; }}
             QTreeWidget::item {{ padding: 4px; color: {TEXT_COLOR}; }}
             QTreeWidget::item:alternate {{ background-color: #333333; }}
             QLineEdit {{ padding: 6px; border: 1px solid #444444; border-radius: 4px; background-color: #2d2d2d; color: {TEXT_COLOR}; }}
             QPushButton {{ padding: 6px 12px; background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border: none; border-radius: 4px; }}
             QPushButton:hover {{ background-color: {BUTTON_HOVER_COLOR}; }}
             QSplitter::handle {{ background-color: #444444; }}
         """
        self.setStyleSheet(style_sheet)

    def browse_file(self):
        """Open file dialog and load DICOM file"""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )
        if file_name:
            self.file_path.setText(file_name)
            self.load_dicom(file_name)

    def filter_items(self, text):
        """Filter tree items based on search text"""
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower() for j in range(item.columnCount())
            )
            item.setHidden(not matches)

    def load_dicom(self, file_path):
        try:
            dataset = pydicom.dcmread(file_path)
            if not dataset:
                raise ValueError("No data found in DICOM file.")

            # Clear previous data in the tree widget
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

            # Display image if available
            if hasattr(dataset, "pixel_array"):
                self.image_viewer.display_image(dataset)

            # Adjust splitter to prioritize metadata
            total_width = self.splitter.width()
            metadata_width = int(total_width * 0.8)
            image_width = total_width - metadata_width
            self.splitter.setSizes([metadata_width, image_width])

            print(f"Loaded {self.tree.topLevelItemCount()} DICOM tags")
        except Exception as e:
            print(f"Error loading file: {str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DicomExplorer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
