from pathlib import Path
from typing import List, Optional

import pydicom
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from ui.viewers.image_viewer import ImageViewer
from utils.dicom_utils import normalize_pixel_array


class FileBrowserManager:
    PREVIEW_SIZE = 200
    DIALOG_WIDTH_RATIO = 0.8
    DIALOG_HEIGHT_RATIO = 0.7

    def __init__(self, parent):
        self.parent = parent
        self.last_used_directory = str(Path.home())
        self.image_viewer = ImageViewer()

    def _setup_dialog(self, dialog: QFileDialog, title: str, file_mode: QFileDialog.FileMode,
        accept_mode: QFileDialog.AcceptMode) -> None:
        """Set basic dialog properties."""
        dialog.setWindowTitle(title)
        dialog.setDirectory(self.last_used_directory)
        dialog.setNameFilter("DICOM files (*.dcm);;All files (*.*)")
        dialog.setFileMode(file_mode)
        dialog.setAcceptMode(accept_mode)

        if file_mode == QFileDialog.ExistingFiles:
            dialog.setViewMode(QFileDialog.Detail)

        app_width = self.parent.width()
        app_height = self.parent.height()
        dialog.setMinimumWidth(int(app_width * self.DIALOG_WIDTH_RATIO))
        dialog.setMinimumHeight(int(app_height * self.DIALOG_HEIGHT_RATIO))

        # Removing sidebar
        sidebar = dialog.findChild(QWidget, "sidebar")
        if sidebar:
            sidebar.setParent(None)
            sidebar.deleteLater()

    def _create_preview_widget(self) -> tuple[QWidget, QLabel]:
        """Create preview widget."""
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_label = QLabel("Preview will appear here")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)
        return preview_widget, preview_label

    def _update_preview(self, preview_label: QLabel, path: str) -> None:
        """Update dicom file preview."""
        if not path or not path.lower().endswith(".dcm"):
            preview_label.setText("Preview not available for non-DICOM files.")
            return

        try:
            dataset = pydicom.dcmread(path)
            if not hasattr(dataset, "pixel_array"):
                preview_label.setText("No image preview available.")
                return

            pixel_array = normalize_pixel_array(dataset.pixel_array)
            image = self.image_viewer.create_qimage(pixel_array)
            pixmap = QPixmap.fromImage(image)
            preview_label.setPixmap(pixmap.scaled(
                self.PREVIEW_SIZE,
                self.PREVIEW_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            preview_label.setText(f"Error loading preview: {str(e)}")

    def browse_file(self) -> Optional[List[str]]:
        """Open file dialog for selecting DICOM files."""
        try:
            dialog = QFileDialog(self.parent)
            self._setup_dialog(dialog, "Select DICOM Files", QFileDialog.ExistingFiles, QFileDialog.AcceptOpen)

            # add preview
            preview_widget, preview_label = self._create_preview_widget()
            dialog.layout().addWidget(preview_widget, 0, 3, 4, 1)
            dialog.currentChanged.connect(lambda path: self._update_preview(preview_label, path))

            if dialog.exec() == QFileDialog.Accepted:
                file_names = dialog.selectedFiles()
                self.last_used_directory = dialog.directory().absolutePath()

                if file_names:
                    for file_name in file_names:
                        self.parent.load_dicom(file_name)
                    return file_names
            return None
        except Exception as e:
            print(f"Error in browse_file: {e}")
            return None

    def save_file(self, dataset: pydicom.Dataset, current_file: str) -> Optional[str]:
        """Save DICOM file."""
        if not dataset or not current_file:
            self.parent.status_bar.showMessage("No DICOM file loaded")
            return None

        try:
            dialog = QFileDialog(self.parent)
            self._setup_dialog(dialog, "Save DICOM File", QFileDialog.AnyFile, QFileDialog.AcceptSave)

            if dialog.exec() == QFileDialog.Accepted:
                file_name = dialog.selectedFiles()[0]
                if not file_name.lower().endswith(".dcm"):
                    file_name += ".dcm"

                self.last_used_directory = dialog.directory().absolutePath()

                try:
                    dataset.save_as(file_name)
                    self.parent.status_bar.showMessage(
                        f"File saved successfully to {file_name}",
                        3000
                    )
                    return file_name
                except Exception as e:
                    self.parent.show_error_message(f"Failed to save file: {str(e)}")
                    return None
            return None
        except Exception as e:
            print(f"Error in save_file: {e}")
            return None
