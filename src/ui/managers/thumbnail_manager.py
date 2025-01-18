from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton

from constants import THUMBNAIL_SIZE
from ui.viewers.image_viewer import ImageViewer
from utils.dicom_properties import DicomImageProperties


class ThumbnailManager:
    def __init__(self, thumbnail_panel, thumbnail_layout, datasets, study_groups):
        self.thumbnail_panel = thumbnail_panel
        self.thumbnail_layout = thumbnail_layout
        self.main_window = thumbnail_panel.window()
        self.datasets = datasets
        self.study_groups = study_groups

    def rebuild_thumbnail_layout(self):
        """Rebuild the thumbnail layout based on grouped datasets."""
        self.clear_thumbnail_layout()
        self.add_study_groups_to_layout()

    def clear_thumbnail_layout(self):
        """Clear the existing thumbnail layout."""
        while self.thumbnail_layout.count():
            item = self.thumbnail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_study_groups_to_layout(self):
        """Add study groups to the thumbnail layout."""
        row = 0

        for study_uid, datasets in self.study_groups.items():
            if row > 0:
                separator = self.create_horizontal_separator()
                self.thumbnail_layout.addWidget(separator, row, 0, 1, 2)
                row += 1

            self.add_study_label(study_uid, datasets[0][1], row)
            row += 1
            row = self.add_thumbnails_for_study(datasets, row)

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

        if hasattr(dataset, "pixel_array"):
            try:
                dicom_props = DicomImageProperties.from_dataset(dataset)
                image_viewer = ImageViewer()
                processed_pixels = dicom_props.get_processed_pixels()
                image = image_viewer.create_qimage(processed_pixels)
                pixmap = QPixmap.fromImage(image)
                pixmap = pixmap.scaled(THUMBNAIL_SIZE, Qt.KeepAspectRatio)
                thumbnail.setIcon(QPixmap(pixmap))
                thumbnail.setIconSize(THUMBNAIL_SIZE)
            except ValueError as e:
                print(f"Error creating thumbnail: {e}")
                thumbnail.setText(Path(file_path).name)
        else:
            thumbnail.setText(Path(file_path).name)

        thumbnail.clicked.connect(self.main_window.on_thumbnail_clicked)

        return thumbnail
