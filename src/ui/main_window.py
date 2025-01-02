from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar,
    QLineEdit, QTabWidget, QStatusBar, QFileDialog,
    QMessageBox, QLabel, QHBoxLayout, QListWidget,
    QListWidgetItem
)
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtCore import Qt
from pathlib import Path
import pydicom
from ui.image_viewer import ImageViewer
from ui.metadata_viewer import MetadataViewer
from styles.theme import get_application_style
from utils.dicom_utils import normalize_pixel_array


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.datasets = {}  # Dictionary to store opened DICOM datasets
        self.current_file = None

        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        """Initialize the user interface."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Left panel for DICOM thumbnails
        self.thumbnail_panel = QListWidget()
        self.thumbnail_panel.setMaximumWidth(200)
        layout.addWidget(self.thumbnail_panel)

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

    def _setup_connections(self):
        """Set up signal-slot connections."""
        self.thumbnail_panel.itemClicked.connect(self.load_selected_dicom)
        self.tab_widget.currentChanged.connect(self.update_status_bar)
        self.image_viewer.zoom_changed.connect(self.update_zoom_status)

        # Connect toolbar actions
        self.open_action.triggered.connect(self.browse_file)
        self.save_action.triggered.connect(self.save_file)

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
                self.status_bar.showMessage(f"Error saving file: {str(e)}")
                QMessageBox.warning(
                    self, "Error", f"Failed to save file: {str(e)}"
                )

    def browse_file(self):
        """Open one or more DICOM files."""
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            "Select DICOM files",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )
        if file_names:
            for file_name in file_names:
                self.load_dicom(file_name)

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
            self.status_bar.showMessage(f"Error loading file: {str(e)}")

    def add_thumbnail(self, file_path, dataset):
        """Add a thumbnail of the DICOM file to the left panel."""
        item = QListWidgetItem()
        item.setData(Qt.UserRole, file_path)

        if hasattr(dataset, "pixel_array"):
            try:
                pixel_array = normalize_pixel_array(dataset.pixel_array)
                image = self.image_viewer._create_qimage(pixel_array)
                pixmap = QPixmap.fromImage(image)
                pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio)
                item.setIcon(QPixmap(pixmap))
            except ValueError as e:
                print(f"Error creating thumbnail: {e}")
                item.setText(Path(file_path).name)
        else:
            item.setText(Path(file_path).name)

        self.thumbnail_panel.addItem(item)

    def load_selected_dicom(self, item):
        """Load the selected DICOM file from the left panel."""
        file_path = item.data(Qt.UserRole)
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
