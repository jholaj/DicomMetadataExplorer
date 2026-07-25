import contextlib
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QPushButton, QSizePolicy

from constants import THUMBNAIL_SIZE
from ui.viewers.image_viewer import ImageViewer
from utils.dicom_properties import DicomImageProperties


class ElidedLabel(QLabel):
    """Label that elides its text with '…' instead of widening its parent."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        # Ignored horizontal policy: the label takes whatever width the
        # layout gives it and never forces the panel wider
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._update_elide()

    def setText(self, text):
        self._full_text = text
        self._update_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self):
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.ElideRight, max(0, self.width() - 4))
        super().setText(elided)


class _ThumbnailSignals(QObject):
    ready = Signal(str, QImage)
    failed = Signal(str)


class ThumbnailWorker(QRunnable):
    """Decodes pixel data and builds the thumbnail image off the UI thread."""

    def __init__(self, file_path, dataset, signals):
        super().__init__()
        self.file_path = file_path
        self.dataset = dataset
        self.signals = signals

    def run(self):
        try:
            props = DicomImageProperties.from_dataset(self.dataset)
            pixels = props.get_processed_pixels()
            image = ImageViewer.create_qimage(pixels)
            # Detach from the numpy buffer before crossing thread boundaries
            self.signals.ready.emit(self.file_path, image.copy())
        except RuntimeError:
            pass  # UI was torn down while the worker was still running
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            with contextlib.suppress(RuntimeError):
                self.signals.failed.emit(self.file_path)


class ThumbnailManager:
    def __init__(self, thumbnail_panel, thumbnail_layout, study_groups):
        self.thumbnail_panel = thumbnail_panel
        self.thumbnail_layout = thumbnail_layout
        self.main_window = thumbnail_panel.window()
        self.study_groups = study_groups

        # Thumbnails are decoded once, in background threads, and cached
        self.icon_cache = {}
        self.pending = set()
        self.thread_pool = QThreadPool.globalInstance()
        self.signals = _ThumbnailSignals()
        self.signals.ready.connect(self.on_thumbnail_ready)
        self.signals.failed.connect(self.on_thumbnail_failed)

    def rebuild_thumbnail_layout(self):
        """Rebuild the thumbnail layout based on grouped datasets."""
        self.clear_thumbnail_layout()
        self.add_study_groups_to_layout()
        self.select_thumbnail(self.main_window.current_file)

    def select_thumbnail(self, file_path):
        """Check the thumbnail matching file_path and uncheck all others."""
        for i in range(self.thumbnail_layout.count()):
            widget = self.thumbnail_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setChecked(widget.property("file_path") == file_path)

    def clear_thumbnail_layout(self):
        """Clear the existing thumbnail layout."""
        while self.thumbnail_layout.count():
            item = self.thumbnail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Detach immediately so the stale widget is not painted
                # over the panel before deleteLater() runs
                widget.setParent(None)
                widget.deleteLater()

    def add_study_groups_to_layout(self):
        """Add study groups to the thumbnail layout, sorted by study."""
        row = 0

        for study_uid, datasets in self.sorted_study_groups():
            if row > 0:
                separator = self.create_horizontal_separator()
                self.thumbnail_layout.addWidget(separator, row, 0, 1, 2)
                row += 1

            self.add_study_label(study_uid, datasets[0][1], row)
            row += 1
            row = self.add_thumbnails_for_study(datasets, row)

    def sorted_study_groups(self):
        """Sort study groups by StudyInstanceUID."""
        return sorted(self.study_groups.items(), key=lambda entry: str(entry[0]))

    def add_study_label(self, study_uid, dataset, row):
        """Add a study label (description, falling back to date) to the layout."""
        study_date = self.format_study_date(dataset)
        description = str(getattr(dataset, "StudyDescription", "") or "")
        study_label = ElidedLabel(description or study_date)
        study_label.setObjectName("study_date_label")

        tooltip = f"Study UID: {study_uid}\nDate: {study_date}"
        if description:
            tooltip = f"{description}\n{tooltip}"
        study_label.setToolTip(tooltip)

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

        def instance_key(entry):
            file_path, dataset = entry
            instance = getattr(dataset, "InstanceNumber", None)
            try:
                return (0, int(instance), file_path)
            except (TypeError, ValueError):
                return (1, 0, file_path)

        for idx, (file_path, dataset) in enumerate(sorted(datasets, key=instance_key)):
            thumbnail = self.create_thumbnail(file_path, dataset)
            self.thumbnail_layout.addWidget(thumbnail, row, idx % 2)
            if idx % 2 == 1:
                row += 1
        if len(datasets) % 2 == 1:
            row += 1
        return row

    def create_horizontal_separator(self):
        """Create a horizontal separator line."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("study_separator")
        separator.setFixedHeight(1)
        return separator

    def create_thumbnail(self, file_path, dataset):
        """Create a thumbnail widget for a DICOM file."""
        thumbnail = QPushButton()
        thumbnail.setCheckable(True)  # Enable checkable state

        # Store the file path as a property of the thumbnail
        thumbnail.setProperty("file_path", file_path)
        thumbnail.setToolTip(self.build_tooltip(file_path, dataset))

        if file_path in self.icon_cache:
            thumbnail.setIcon(self.icon_cache[file_path])
            thumbnail.setIconSize(THUMBNAIL_SIZE)
        elif hasattr(dataset, "pixel_array"):
            # Placeholder until the background decode finishes
            thumbnail.setText("...")
            if file_path not in self.pending:
                self.pending.add(file_path)
                self.thread_pool.start(ThumbnailWorker(file_path, dataset, self.signals))
        else:
            thumbnail.setText(Path(file_path).name)

        thumbnail.clicked.connect(self.main_window.on_thumbnail_clicked)
        thumbnail.setContextMenuPolicy(Qt.CustomContextMenu)
        thumbnail.customContextMenuRequested.connect(
            lambda pos, btn=thumbnail: self.show_thumbnail_menu(btn, pos)
        )

        return thumbnail

    def on_thumbnail_ready(self, file_path, image):
        """Cache the decoded thumbnail and update the matching button."""
        self.pending.discard(file_path)
        pixmap = QPixmap.fromImage(image).scaled(
            THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        icon = QIcon(pixmap)
        self.icon_cache[file_path] = icon

        for i in range(self.thumbnail_layout.count()):
            widget = self.thumbnail_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.property("file_path") == file_path:
                widget.setText("")
                widget.setIcon(icon)
                widget.setIconSize(THUMBNAIL_SIZE)
                break

    def on_thumbnail_failed(self, file_path):
        """Fall back to the file name when the thumbnail cannot be decoded."""
        self.pending.discard(file_path)
        for i in range(self.thumbnail_layout.count()):
            widget = self.thumbnail_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.property("file_path") == file_path:
                widget.setText(Path(file_path).name)
                break

    def forget_file(self, file_path):
        """Drop cached data for a closed file."""
        self.icon_cache.pop(file_path, None)
        self.pending.discard(file_path)

    def show_thumbnail_menu(self, thumbnail, position):
        """Show a context menu for closing a file or a whole study."""
        file_path = thumbnail.property("file_path")

        menu = QMenu()
        close_file_action = menu.addAction("Close File")
        close_study_action = menu.addAction("Close Study")
        action = menu.exec(thumbnail.mapToGlobal(position))

        if action == close_file_action:
            self.main_window.close_file(file_path)
        elif action == close_study_action:
            self.main_window.close_study(file_path)

    def build_tooltip(self, file_path, dataset):
        """Build a tooltip with basic information about the DICOM file."""
        lines = [Path(file_path).name]
        for attr in ("PatientName", "Modality", "SeriesDescription"):
            value = getattr(dataset, attr, None)
            if value:
                lines.append(f"{attr}: {value}")
        return "\n".join(lines)
