"""File dialogs remembering the last used directory."""

import logging
from pathlib import Path

from pydicom.errors import InvalidDicomError
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QWidget

from dicom_explorer.app.imaging import thumbnail_image
from dicom_explorer.core.export import ExportFormat
from dicom_explorer.core.io import read_dataset
from dicom_explorer.core.pixels import PixelDecodeError, decode_frame, has_pixel_data
from dicom_explorer.core.rendering import FrameImage

log = logging.getLogger(__name__)

DICOM_FILTER = "DICOM files (*.dcm *.dicom *.DCM)"
ALL_FILTER = "All files (*)"
PREVIEW_SIZE = 200


class FileDialogs:
    def __init__(self, parent: QWidget, settings: QSettings):
        self.parent = parent
        self.settings = settings

    @property
    def last_directory(self) -> str:
        directory = Path(str(self.settings.value("last_directory", Path.home())))
        return str(directory if directory.is_dir() else Path.home())

    def open_files(self) -> list[str]:
        """File selection with a preview, the Qt dialog keeps the preview on every platform."""
        dialog = QFileDialog(self.parent, "Open DICOM Files", self.last_directory)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilters([ALL_FILTER, DICOM_FILTER])
        dialog.setViewMode(QFileDialog.Detail)
        dialog.resize(int(self.parent.width() * 0.75), int(self.parent.height() * 0.7))

        preview = QLabel("Preview")
        preview.setObjectName("muted_label")
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumWidth(PREVIEW_SIZE + 20)
        preview.setWordWrap(True)
        grid = dialog.layout()
        grid.addWidget(preview, 0, grid.columnCount(), grid.rowCount(), 1)
        dialog.currentChanged.connect(lambda path: _show_preview(preview, path))

        files = dialog.selectedFiles() if dialog.exec() == QFileDialog.Accepted else []
        if files:
            self._remember(Path(files[0]).parent)
        return files

    def open_folder(self) -> str | None:
        folder = QFileDialog.getExistingDirectory(self.parent, "Open Folder", self.last_directory)
        if folder:
            self._remember(Path(folder))
        return folder or None

    def choose_folder(self, title: str) -> Path | None:
        folder = QFileDialog.getExistingDirectory(self.parent, title, self.last_directory)
        if folder:
            self._remember(Path(folder))
        return Path(folder) if folder else None

    def save_as(self, document) -> Path | None:
        file_name, selected = QFileDialog.getSaveFileName(
            self.parent, "Save As", str(document.path), f"{DICOM_FILTER};;{ALL_FILTER}"
        )
        if not file_name:
            return None
        path = Path(file_name)
        if not path.suffix and selected == DICOM_FILTER:
            path = path.with_suffix(".dcm")
        self._remember(path.parent)
        return path

    def export(self, document) -> tuple[Path, ExportFormat] | None:
        default = Path(self.last_directory) / f"{document.path.stem}_metadata.json"
        file_name, selected = QFileDialog.getSaveFileName(
            self.parent,
            "Export Metadata",
            str(default),
            ";;".join(fmt.file_filter for fmt in ExportFormat),
        )
        if not file_name:
            return None
        chosen = next(fmt for fmt in ExportFormat if fmt.file_filter == selected)
        path = Path(file_name)
        fmt = ExportFormat.for_path(path, chosen)
        if not path.name.lower().endswith(fmt.suffix):
            path = path.with_name(path.name + fmt.suffix)
        self._remember(path.parent)
        return path, fmt

    def _remember(self, directory: Path) -> None:
        self.settings.setValue("last_directory", str(directory))


def _show_preview(label: QLabel, path: str) -> None:
    label.setPixmap(QPixmap())
    if not path or not Path(path).is_file():
        label.setText("Preview")
        return
    try:
        dataset = read_dataset(path)
        if not has_pixel_data(dataset):
            label.setText(f"{dataset.get('Modality', 'DICOM')} file without pixel data")
            return
        image = FrameImage(dataset, *decode_frame(dataset)).render()
        label.setPixmap(QPixmap.fromImage(thumbnail_image(image, PREVIEW_SIZE)))
    except InvalidDicomError:
        label.setText("Not a DICOM file")
    except PixelDecodeError as e:
        label.setText(f"Pixel data cannot be decoded:\n{e}")
    except Exception as e:
        log.debug("Preview failed for %s", path, exc_info=True)
        label.setText(f"Preview unavailable:\n{e}")
