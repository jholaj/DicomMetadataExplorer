from pathlib import Path

import pydicom
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from ui.viewers.image_viewer import ImageViewer
from utils.dicom_utils import normalize_pixel_array


class FileBrowserManager:
    def __init__(self, parent):
        self.parent = parent  # Ref to main window
        self.last_used_directory = str(Path.home())

    def browse_file(self):
        """Open one or more DICOM files with a custom preview widget."""
        file_dialog = QFileDialog(self.parent)
        file_dialog.setWindowTitle("Select DICOM Files")
        file_dialog.setDirectory(self.last_used_directory)
        file_dialog.setNameFilter("DICOM files (*.dcm);;All files (*.*)")
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setViewMode(QFileDialog.Detail)

        app_width = self.parent.width()
        app_height = self.parent.height()
        dialog_width = int(app_width * 0.8)  # 80% width
        dialog_height = int(app_height * 0.7)  # 70% height
        file_dialog.setMinimumWidth(dialog_width)
        file_dialog.setMinimumHeight(dialog_height)

        # Skrýt panel vlevo (sidebar)
        for child in file_dialog.findChildren(QWidget):
            if "sidebar" in child.objectName().lower():
                child.setParent(None)
                break

        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_label = QLabel("Preview will appear here", preview_widget)
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)

        # Adding to file dialog
        layout = file_dialog.layout()
        layout.addWidget(preview_widget, 0, 3, 4, 1)

        # if selected file changed => rerender thumbnail
        file_dialog.currentChanged.connect(lambda path: self.update_preview(preview_label, path))

        if file_dialog.exec() == QFileDialog.Accepted:
            file_names = file_dialog.selectedFiles()
            self.last_used_directory = file_dialog.directory().absolutePath()  # save last dir

            if file_names:
                for file_name in file_names:
                    self.parent.load_dicom(file_name)
        else:
            QMessageBox.information(self.parent, "Information", "No files selected.")

    def update_preview(self, preview_label, path):
        """Update the preview widget with the selected file."""
        if path.lower().endswith(".dcm"):
            try:
                dataset = pydicom.dcmread(path)
                if hasattr(dataset, "pixel_array"):
                    pixel_array = normalize_pixel_array(dataset.pixel_array)
                    image_viewer = ImageViewer()
                    image = image_viewer.create_qimage(pixel_array)
                    pixmap = QPixmap.fromImage(image)
                    preview_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio))
                else:
                    preview_label.setText("No image preview available.")
            except Exception as e:
                preview_label.setText(f"Error loading preview: {str(e)}")
        else:
            preview_label.setText("Preview not available for non-DICOM files.")
