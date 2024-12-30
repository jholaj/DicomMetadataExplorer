from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar,
    QLineEdit, QTabWidget, QStatusBar, QFileDialog,
    QMessageBox, QLabel
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from pathlib import Path
import pydicom
from ui.image_viewer import ImageViewer
from ui.metadata_viewer import MetadataViewer
from styles.theme import get_application_style

class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.dataset = None

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        toolbar = QToolBar()
        self.addToolBar(toolbar)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.browse_file)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)

        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        layout.addWidget(self.file_path)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.metadata_viewer = MetadataViewer()
        self.tab_widget.addTab(self.metadata_viewer, "Metadata")

        self.image_viewer = ImageViewer()
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.addWidget(self.image_viewer, alignment=Qt.AlignCenter)
        self.tab_widget.addTab(image_container, "Content")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_bar.addPermanentWidget(self.zoom_label)
        self.zoom_label.hide()

        self.tab_widget.currentChanged.connect(self.update_status_bar)
        self.image_viewer.zoom_changed.connect(self.update_zoom_status)

        self.setStyleSheet(get_application_style())

    def update_status_bar(self, index: int) -> None:
        """Updates the status bar based on the active tab and application state."""
        if not self.dataset:
            self.status_bar.showMessage("No DICOM file loaded")
            self.zoom_label.hide()
            return

        if index == 0:  # Metadata tab
            tag_count = self.metadata_viewer.tree.topLevelItemCount()
            self.status_bar.showMessage(f"Loaded {tag_count} DICOM tags")
            self.zoom_label.hide()

        elif index == 1:  # Content tab
            if hasattr(self.dataset, "pixel_array"):
                dimensions = self.dataset.pixel_array.shape
                bits = getattr(self.dataset, "BitsStored", "unknown")
                self.status_bar.showMessage(
                    f"Dimensions: {dimensions[1]}x{dimensions[0]}, {bits} bits/pixel"
                )
                self.zoom_label.show()
            else:
                self.zoom_label.hide()

    def update_zoom_status(self, relative_zoom):
        """Update the zoom level display"""
        zoom_percentage = int(relative_zoom * 100)
        self.zoom_label.setText(f"Zoom: {zoom_percentage}%")
        self.zoom_label.show()

    def save_file(self):
        if not self.dataset:
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
                self.dataset.save_as(file_name)
                self.status_bar.showMessage(
                    f"File saved successfully to {file_name}", 3000
                )
            except Exception as e:
                self.status_bar.showMessage(f"Error saving file: {str(e)}")
                QMessageBox.warning(
                    self, "Error", f"Failed to save file: {str(e)}"
                )

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
            self.dataset = pydicom.dcmread(file_path)
            if not self.dataset:
                raise ValueError("No data found in DICOM file.")

            self.file_path.setText(file_path)
            self.metadata_viewer.load_metadata(self.dataset)

            if hasattr(self.dataset, "pixel_array"):
                self.image_viewer.display_image(self.dataset)

            self.status_bar.showMessage(
                f"Loaded {self.metadata_viewer.tree.topLevelItemCount()} DICOM tags"
            )

        except Exception as e:
            self.status_bar.showMessage(f"Error loading file: {str(e)}")
