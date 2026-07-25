from pathlib import Path

import pydicom
from pydicom.errors import InvalidDicomError
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from ui.viewers.image_viewer import ImageViewer
from utils.dicom_properties import DicomImageProperties
from utils.metadata_export import export_to_csv, export_to_json


class FileBrowserManager:
    PREVIEW_SIZE = 200
    DIALOG_WIDTH_RATIO = 0.8
    DIALOG_HEIGHT_RATIO = 0.7

    def __init__(self, parent):
        self.parent = parent
        self.last_used_directory = str(parent.settings.value("last_directory", str(Path.home())))

    def _set_last_directory(self, dialog: QFileDialog) -> None:
        """Remember the dialog's directory across sessions."""
        self.last_used_directory = dialog.directory().absolutePath()
        self.parent.settings.setValue("last_directory", self.last_used_directory)

    def _setup_dialog(
        self,
        dialog: QFileDialog,
        title: str,
        file_mode: QFileDialog.FileMode,
        accept_mode: QFileDialog.AcceptMode,
    ) -> None:
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
        if not path or not Path(path).is_file():
            preview_label.setText("Preview will appear here")
            return

        try:
            dataset = pydicom.dcmread(path)
            if not hasattr(dataset, "pixel_array"):
                preview_label.setText("No image preview available.")
                return

            dicom_props = DicomImageProperties.from_dataset(dataset)
            processed_pixels = dicom_props.get_processed_pixels()
            image = ImageViewer.create_qimage(processed_pixels)

            pixmap = QPixmap.fromImage(image)
            preview_label.setPixmap(
                pixmap.scaled(
                    self.PREVIEW_SIZE,
                    self.PREVIEW_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        except InvalidDicomError:
            preview_label.setText("Not a DICOM file.")
        except Exception as e:
            preview_label.setText(f"Error loading preview: {e!s}")

    def browse_file(self) -> list[str] | None:
        """Open file dialog for selecting DICOM files."""
        try:
            dialog = QFileDialog(self.parent)
            self._setup_dialog(
                dialog, "Select DICOM Files", QFileDialog.ExistingFiles, QFileDialog.AcceptOpen
            )

            # add preview
            preview_widget, preview_label = self._create_preview_widget()
            dialog.layout().addWidget(preview_widget, 0, 3, 4, 1)
            dialog.currentChanged.connect(lambda path: self._update_preview(preview_label, path))

            if dialog.exec() == QFileDialog.Accepted:
                file_names = dialog.selectedFiles()
                self._set_last_directory(dialog)

                if file_names:
                    self.parent.load_files(file_names)
                    return file_names
            return None
        except Exception as e:
            print(f"Error in browse_file: {e}")
            return None

    def save_file(self, dataset: pydicom.Dataset, current_file: str) -> str | None:
        """Save DICOM file."""
        if not dataset or not current_file:
            self.parent.status_bar.showMessage("No DICOM file loaded")
            return None

        try:
            dialog = QFileDialog(self.parent)
            self._setup_dialog(
                dialog, "Save DICOM File", QFileDialog.AnyFile, QFileDialog.AcceptSave
            )

            if dialog.exec() == QFileDialog.Accepted:
                file_name = dialog.selectedFiles()[0]
                if not file_name.lower().endswith(".dcm"):
                    file_name += ".dcm"

                self._set_last_directory(dialog)

                try:
                    dataset.save_as(file_name)
                    self.parent.status_bar.showMessage(
                        f"File saved successfully to {file_name}", 3000
                    )
                    return file_name
                except Exception as e:
                    self.parent.show_error_message(f"Failed to save file: {e!s}")
                    return None
            return None
        except Exception as e:
            print(f"Error in save_file: {e}")
            return None

    def export_metadata(self, dataset: pydicom.Dataset, current_file: str) -> str | None:
        """Export metadata of the current DICOM file to JSON or CSV."""
        if not dataset or not current_file:
            self.parent.status_bar.showMessage("No DICOM file loaded")
            return None

        try:
            dialog = QFileDialog(self.parent)
            self._setup_dialog(
                dialog, "Export Metadata", QFileDialog.AnyFile, QFileDialog.AcceptSave
            )
            dialog.setNameFilter("JSON (*.json);;CSV (*.csv)")
            dialog.selectFile(f"{Path(current_file).stem}_metadata.json")

            if dialog.exec() != QFileDialog.Accepted:
                return None

            file_name = dialog.selectedFiles()[0]
            self._set_last_directory(dialog)

            suffix = Path(file_name).suffix.lower()
            if suffix not in (".json", ".csv"):
                suffix = ".csv" if "CSV" in dialog.selectedNameFilter() else ".json"
                file_name += suffix

            try:
                if suffix == ".csv":
                    export_to_csv(dataset, file_name)
                else:
                    export_to_json(dataset, file_name)
                self.parent.status_bar.showMessage(f"Metadata exported to {file_name}", 3000)
                return file_name
            except Exception as e:
                self.parent.show_error_message(f"Failed to export metadata: {e!s}")
                return None
        except Exception as e:
            print(f"Error in export_metadata: {e}")
            return None
