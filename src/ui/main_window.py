from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar,
    QLineEdit, QTabWidget, QStatusBar, QFileDialog,
    QMessageBox, QLabel, QHBoxLayout, QGridLayout,
    QPushButton
)
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtCore import Qt, QSize
from pathlib import Path
import pydicom
from ui.image_viewer import ImageViewer
from ui.metadata_viewer import MetadataViewer
from styles.theme import get_application_style
from utils.dicom_utils import normalize_pixel_array


# Constants
THUMBNAIL_SIZE = QSize(70, 70)
THUMBNAIL_PANEL_WIDTH = 200
ERROR_MESSAGE_TEMPLATE = "Error: {}"


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.datasets = {}  # Dictionary to store opened DICOM datasets
        self.current_file = None
        self.study_groups = {}  # Dictionary to group datasets by StudyInstanceUID

        self.initialize_ui()
        self.setup_signal_slots()

    def initialize_ui(self):
        """Initialize the user interface."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Left panel for DICOM thumbnails
        self.thumbnail_panel = QWidget()
        self.thumbnail_panel.setObjectName("thumbnail_panel")
        self.thumbnail_layout = QGridLayout(self.thumbnail_panel)
        self.thumbnail_panel.setMinimumWidth(THUMBNAIL_PANEL_WIDTH)
        self.thumbnail_panel.setMaximumWidth(THUMBNAIL_PANEL_WIDTH)
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

    def setup_signal_slots(self):
        """Set up signal-slot connections."""
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
                self.show_error_message(f"Failed to save file: {str(e)}")

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
            self.show_error_message(f"Error loading file: {str(e)}")

    def add_thumbnail(self, file_path, dataset):
        """Add a thumbnail of the DICOM file to the left panel."""
        study_uid = dataset.StudyInstanceUID if hasattr(dataset, "StudyInstanceUID") else "Unknown"

        # Group datasets by StudyInstanceUID
        if study_uid not in self.study_groups:
            self.study_groups[study_uid] = []

        self.study_groups[study_uid].append((file_path, dataset))

        # Rebuild the thumbnail layout
        self.rebuild_thumbnail_layout()

    def rebuild_thumbnail_layout(self):
        """Rebuild the thumbnail layout based on grouped datasets."""
        self.clear_thumbnail_layout()
        self.add_study_groups_to_layout()

    def clear_thumbnail_layout(self):
        """Clear the existing thumbnail layout."""
        for i in reversed(range(self.thumbnail_layout.count())):
            self.thumbnail_layout.itemAt(i).widget().setParent(None)
        self.thumbnail_layout.setAlignment(Qt.AlignTop)

    def add_study_groups_to_layout(self):
        """Add study groups to the thumbnail layout."""
        row = 0
        for study_uid, datasets in self.study_groups.items():
            self.add_study_label(study_uid, datasets[0][1], row)
            row += 1
            row = self.add_thumbnails_for_study(datasets, row)
            row += 1

    def add_study_label(self, study_uid, dataset, row):
        """Add a study label to the thumbnail layout."""
        study_date = self.format_study_date(dataset)
        study_label = QLabel(study_date)
        study_label.setObjectName("study_date_label")
        study_label.setToolTip(f"Study UID: {study_uid}")
        study_label.setMaximumHeight(20)
        study_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_layout.addWidget(study_label, row, 0, 1, 2)

    def format_study_date(self, dataset):
        """Format the study date from DICOM format (YYYYMMDD) to a readable format."""
        study_date = dataset.StudyDate if hasattr(dataset, "StudyDate") else "Unknown Date"
        if study_date != "Unknown Date":
            try:
                return f"{study_date[6:8]}.{study_date[4:6]}.{study_date[0:4]}"
            except IndexError:
                return study_date
        return study_date

    def add_thumbnails_for_study(self, datasets, row):
        """Add thumbnails for each dataset in the study group."""
        for idx, (file_path, dataset) in enumerate(datasets):
            thumbnail = self.create_thumbnail(file_path, dataset)
            self.thumbnail_layout.addWidget(thumbnail, row, idx % 2)
            if idx % 2 == 1:
                row += 1
        if len(datasets) % 2 == 1:
            row += 1
        return row

    def create_thumbnail(self, file_path, dataset):
        """Create a thumbnail widget for a DICOM file."""
        thumbnail = QPushButton()
        thumbnail.setCheckable(True)  # Enable checkable state

        # Store the file path as a property of the thumbnail
        thumbnail.setProperty("file_path", file_path)

        if hasattr(dataset, "pixel_array"):
            try:
                pixel_array = normalize_pixel_array(dataset.pixel_array)
                image = self.image_viewer._create_qimage(pixel_array)
                pixmap = QPixmap.fromImage(image)
                pixmap = pixmap.scaled(THUMBNAIL_SIZE, Qt.KeepAspectRatio)
                thumbnail.setIcon(QPixmap(pixmap))
                thumbnail.setIconSize(THUMBNAIL_SIZE)
            except ValueError as e:
                print(f"Error creating thumbnail: {e}")
                thumbnail.setText(Path(file_path).name)
        else:
            thumbnail.setText(Path(file_path).name)

        thumbnail.clicked.connect(self.on_thumbnail_clicked)

        return thumbnail

    def on_thumbnail_clicked(self):
        """Handle thumbnail click events."""
        thumbnail = self.sender()  # Get the clicked thumbnail button
        file_path = thumbnail.property("file_path")

        # Deselect all thumbnails first
        for i in range(self.thumbnail_layout.count()):
            item = self.thumbnail_layout.itemAt(i)
            if item and isinstance(item.widget(), QPushButton):
                if item.widget() != thumbnail:
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

    def show_error_message(self, message):
        """Show an error message in the status bar and a message box."""
        self.status_bar.showMessage(ERROR_MESSAGE_TEMPLATE.format(message))
        QMessageBox.warning(self, "Error", message)
