from pathlib import Path

import pydicom
import pydicom.config
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from constants import THUMBNAIL_PANEL_WIDTH
from styles.theme import get_application_style
from ui.managers.file_browser_manager import FileBrowserManager
from ui.managers.thumbnail_manager import ThumbnailManager
from ui.viewers.image_viewer import ImageViewer
from ui.viewers.metadata_viewer import MetadataViewer

# Constants
ERROR_MESSAGE_TEMPLATE = "Error: {}"
# Ignore invalid data and replace with UN
pydicom.config.convert_wrong_length_to_UN = True


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.datasets = {}  # Dictionary to store opened DICOM datasets
        self.current_file = None
        self.study_groups = {}  # Dictionary to group datasets by StudyInstanceUID
        self.last_used_directory = str(Path.home())

        # Initialize FileBrowserManager
        self.file_browser_manager = FileBrowserManager(self)

        self.initialize_ui()
        self.setup_signal_slots()

        # Initialize ThumbnailManager
        self.thumbnail_manager = ThumbnailManager(
            self.thumbnail_panel, self.thumbnail_layout, self.datasets, self.study_groups
        )

    def initialize_ui(self):
        """Initialize the user interface."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Left panel for DICOM thumbnails
        scroll_area = self.initialize_left_panel()
        layout.addWidget(scroll_area)

        # Right panel for main content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Store actions as instance variables
        self.open_action = QAction("Open", self)
        self.save_action = QAction("Save", self)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        right_layout.addWidget(self.file_path)

        # Tab widget for metadata and image
        self.tab_widget = QTabWidget()
        self.metadata_viewer = MetadataViewer()
        self.image_viewer = ImageViewer()
        self.tab_widget.addTab(self.metadata_viewer, "Metadata")
        self.tab_widget.addTab(self.image_viewer, "Content")
        right_layout.addWidget(self.tab_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_bar.addPermanentWidget(self.zoom_label)
        self.zoom_label.hide()

        layout.addWidget(right_panel)
        self.setStyleSheet(get_application_style())

    def setup_signal_slots(self):
        """Set up signal-slot connections."""
        self.tab_widget.currentChanged.connect(self.update_status_bar)
        self.image_viewer.zoom_changed.connect(self.update_zoom_status)

        # Connect toolbar actions
        self.open_action.triggered.connect(self.browse_file)
        self.save_action.triggered.connect(self.save_file)

    def initialize_left_panel(self):
        """Initialize the left panel with thumbnails and scroll area."""
        self.thumbnail_panel = QWidget()
        self.thumbnail_panel.setObjectName("thumbnail_panel")
        self.thumbnail_layout = QGridLayout(self.thumbnail_panel)
        self.thumbnail_layout.setAlignment(Qt.AlignTop)

        # Create a QScrollArea and set the thumbnail_panel as its widget
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.thumbnail_panel)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_area.setMinimumWidth(THUMBNAIL_PANEL_WIDTH)
        scroll_area.setMaximumWidth(THUMBNAIL_PANEL_WIDTH)

        return scroll_area

    def on_thumbnail_clicked(self):
        """Handle thumbnail click events."""
        thumbnail = self.sender()  # Get the clicked thumbnail button
        file_path = thumbnail.property("file_path")

        # Deselect all thumbnails first
        for i in range(self.thumbnail_layout.count()):
            item = self.thumbnail_layout.itemAt(i)
            if item and isinstance(item.widget(), QPushButton) and item.widget() != thumbnail:
                item.widget().setChecked(False)

        # Set the clicked thumbnail as selected
        thumbnail.setChecked(True)

        # Load the selected DICOM file
        self.load_selected_dicom(file_path)

    def load_selected_dicom(self, file_path):
        """Load the selected DICOM file from the left panel."""
        if file_path in self.datasets:
            self.current_file = file_path
            self.update_display(self.datasets[file_path])

    def update_display(self, dataset):
        """Update the metadata and image display for the selected DICOM file."""
        self.file_path.setText(self.current_file)
        self.metadata_viewer.load_metadata(dataset)

        if hasattr(dataset, "pixel_array"):
            self.image_viewer.display_image(dataset)
        else:
            self.image_viewer.clear()

        self.update_status_bar(self.tab_widget.currentIndex())

    def update_status_bar(self, index: int) -> None:
        """Update the status bar based on the active tab."""
        if not self.current_file or self.current_file not in self.datasets:
            self.status_bar.showMessage("No DICOM file loaded")
            self.zoom_label.hide()
            return

        dataset = self.datasets[self.current_file]

        if index == 0:  # Metadata tab
            tag_count = self.metadata_viewer.tree.topLevelItemCount()
            self.status_bar.showMessage(f"Loaded {tag_count} DICOM tags")
            self.zoom_label.hide()

        elif index == 1:  # Content tab
            if hasattr(dataset, "pixel_array"):
                dimensions = dataset.pixel_array.shape
                bits = getattr(dataset, "BitsStored", "unknown")
                self.status_bar.showMessage(
                    f"Dimensions: {dimensions[1]}x{dimensions[0]}, {bits} bits/pixel"
                )
                self.zoom_label.show()
            else:
                self.zoom_label.hide()

    def update_zoom_status(self, relative_zoom):
        """Update the zoom level display."""
        zoom_percentage = int(relative_zoom * 100)
        self.zoom_label.setText(f"Zoom: {zoom_percentage}%")
        self.zoom_label.show()

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle file drop event."""
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            self.handle_dropped_files(files)
        else:
            event.ignore()

    def handle_dropped_files(self, files):
        """Process dropped files."""
        for file_path in files:
            if Path(file_path).suffix.lower() == ".dcm":  # Check for DICOM files
                self.load_dicom(file_path)
            else:
                QMessageBox.warning(self, "Invalid File", f"File {file_path} is not a valid DICOM file.")

    def browse_file(self):
        """Open one or more DICOM files using FileBrowserManager."""
        self.file_browser_manager.browse_file()

    def load_dicom(self, file_path):
        """Load a DICOM file and add it to the dataset."""
        try:
            dataset = pydicom.dcmread(file_path)
            if not dataset:
                raise ValueError("No data found in DICOM file.")

            self.datasets[file_path] = dataset
            self.add_thumbnail(file_path, dataset)

            if not self.current_file:
                self.current_file = file_path
                self.update_display(dataset)

            self.status_bar.showMessage(
                f"Loaded {self.metadata_viewer.tree.topLevelItemCount()} DICOM tags"
            )
        except Exception as e:
            self.show_error_message(f"Error loading file: {str(e)}")

    def add_thumbnail(self, file_path, dataset):
        """Add a thumbnail of the DICOM file to the left panel."""
        study_uid = dataset.StudyInstanceUID if hasattr(dataset, "StudyInstanceUID") else "Unknown"

        # Group datasets by StudyInstanceUID
        if study_uid not in self.study_groups:
            self.study_groups[study_uid] = []

        self.study_groups[study_uid].append((file_path, dataset))

        # Rebuild the thumbnail layout
        self.thumbnail_manager.rebuild_thumbnail_layout()

    def save_file(self):
        """Save the currently selected DICOM file."""
        if not self.current_file or self.current_file not in self.datasets:
            self.status_bar.showMessage("No DICOM file loaded")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )

        if file_name:
            try:
                self.datasets[self.current_file].save_as(file_name)
                self.status_bar.showMessage(
                    f"File saved successfully to {file_name}", 3000
                )
            except Exception as e:
                self.show_error_message(f"Failed to save file: {str(e)}")

    def show_error_message(self, message):
        """Show an error message in the status bar and a message box."""
        self.status_bar.showMessage(ERROR_MESSAGE_TEMPLATE.format(message))
        QMessageBox.warning(self, "Error", message)
