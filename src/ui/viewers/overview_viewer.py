from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from styles.theme import SURFACE_COLOR, TEXT_COLOR, TEXT_MUTED_COLOR
from utils.dicom_validation import validate_dataset

# Status colors on the dark surface (used with an icon + label, never alone)
COLOR_OK = "#0ca30c"
COLOR_WARNING = "#fab219"
COLOR_ERROR = "#d03b3b"

MISSING = "-"


class OverviewViewer(QWidget):
    """Tab with a readable summary of the file and validation results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.content_layout.setSpacing(4)
        scroll.setWidget(self.content)
        layout.addWidget(scroll)

        self.issue_count = 0
        self.clear()

    def clear(self):
        """Clear the overview."""
        self._clear_layout()
        self.issue_count = 0
        placeholder = QLabel("No DICOM file loaded")
        placeholder.setStyleSheet(f"color: {TEXT_MUTED_COLOR};")
        placeholder.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(placeholder)

    def _clear_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def load_data(self, dataset, file_path):
        """Populate the overview for the given dataset."""
        self._clear_layout()

        issues, checks = validate_dataset(dataset)
        self.issue_count = len(issues)
        self._add_validation_section(issues, checks)

        def get(keyword, formatter=str):
            value = getattr(dataset, keyword, None)
            if value is None or str(value) == "":
                return MISSING
            try:
                return formatter(value)
            except Exception:
                return str(value)

        self._add_section(
            "Patient",
            [
                ("Name", get("PatientName")),
                ("ID", get("PatientID")),
                ("Birth date", get("PatientBirthDate", _format_date)),
                ("Sex", get("PatientSex")),
            ],
        )

        self._add_section(
            "Study",
            [
                ("Description", get("StudyDescription")),
                ("Date", get("StudyDate", _format_date)),
                ("Modality", get("Modality")),
                ("Accession number", get("AccessionNumber")),
                ("Study UID", get("StudyInstanceUID")),
                ("Series description", get("SeriesDescription")),
                ("Instance number", get("InstanceNumber")),
            ],
        )

        self._add_section("Image", self._image_rows(dataset))

        self._add_section(
            "Equipment",
            [
                ("Manufacturer", get("Manufacturer")),
                ("Model", get("ManufacturerModelName")),
                ("Station name", get("StationName")),
                ("KVP", get("KVP")),
                ("Exposure time (ms)", get("ExposureTime")),
                ("Tube current (mA)", get("XRayTubeCurrent")),
                ("Exposure (mAs)", get("Exposure")),
            ],
        )

        self._add_section("File", self._file_rows(dataset, file_path))
        self.content_layout.addStretch()

    def _image_rows(self, dataset):
        rows = []
        columns_value = getattr(dataset, "Columns", None)
        rows_value = getattr(dataset, "Rows", None)
        if columns_value and rows_value:
            rows.append(("Dimensions", f"{columns_value} x {rows_value} px"))

        bits_stored = getattr(dataset, "BitsStored", None)
        bits_allocated = getattr(dataset, "BitsAllocated", None)
        if bits_allocated:
            rows.append(("Bits", f"{bits_stored or '?'} stored / {bits_allocated} allocated"))

        rows.append(("Photometric", str(getattr(dataset, "PhotometricInterpretation", MISSING))))

        spacing = getattr(dataset, "PixelSpacing", None) or getattr(
            dataset, "ImagerPixelSpacing", None
        )
        if spacing is not None:
            try:
                rows.append(("Pixel spacing", f"{float(spacing[0]):g} x {float(spacing[1]):g} mm"))
            except (TypeError, ValueError, IndexError):
                rows.append(("Pixel spacing", str(spacing)))
        else:
            rows.append(("Pixel spacing", MISSING))

        center = getattr(dataset, "WindowCenter", None)
        width = getattr(dataset, "WindowWidth", None)
        rows.append(("Window C / W", f"{center} / {width}" if center is not None else MISSING))

        slope = getattr(dataset, "RescaleSlope", None)
        intercept = getattr(dataset, "RescaleIntercept", None)
        if slope is not None or intercept is not None:
            rows.append(("Rescale slope / intercept", f"{slope} / {intercept}"))

        try:
            pixels = dataset.pixel_array.astype(np.float64)
            slope_value = float(getattr(dataset, "RescaleSlope", 1.0))
            intercept_value = float(getattr(dataset, "RescaleIntercept", 0.0))
            if slope_value != 1.0 or intercept_value != 0.0:
                pixels = pixels * slope_value + intercept_value
            rows.append(("Value range", f"{pixels.min():g} to {pixels.max():g}"))
            rows.append(("Mean / std dev", f"{pixels.mean():.1f} / {pixels.std():.1f}"))
        except Exception:
            rows.append(("Pixel statistics", "unavailable (pixel data not decodable)"))

        return rows

    def _file_rows(self, dataset, file_path):
        rows = [("Path", str(file_path))]
        try:
            size = Path(file_path).stat().st_size
            rows.append(("Size", _format_size(size)))
        except OSError:
            pass

        file_meta = getattr(dataset, "file_meta", None)
        transfer_syntax = getattr(file_meta, "TransferSyntaxUID", None)
        rows.append(("Transfer syntax", transfer_syntax.name if transfer_syntax else MISSING))

        sop_class = getattr(dataset, "SOPClassUID", None)
        rows.append(("SOP class", sop_class.name if sop_class else MISSING))
        return rows

    def _add_validation_section(self, issues, checks):
        self._add_section_title("Validation")

        if not issues:
            self._add_status_label(COLOR_OK, f"OK - all {checks} checks passed")
            return

        errors = sum(1 for severity, _ in issues if severity == "error")
        warnings = len(issues) - errors
        summary = []
        if errors:
            summary.append(f"{errors} error(s)")
        if warnings:
            summary.append(f"{warnings} warning(s)")
        self._add_status_label(
            COLOR_ERROR if errors else COLOR_WARNING,
            f"{' and '.join(summary)} found ({checks} checks)",
        )

        for severity, message in issues:
            if severity == "error":
                self._add_status_label(COLOR_ERROR, f"Error: {message}", indent=True)
            else:
                self._add_status_label(COLOR_WARNING, f"Warning: {message}", indent=True)

    def _add_status_label(self, color, text, indent=False):
        symbol = {COLOR_ERROR: "✕", COLOR_WARNING: "⚠", COLOR_OK: "✓"}[color]
        label = QLabel(f"{symbol}  {text}")
        label.setStyleSheet(f"color: {color}; padding-left: {24 if indent else 8}px;")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.content_layout.addWidget(label)

    def _add_section(self, title, rows):
        self._add_section_title(title)

        card = QWidget()
        card.setStyleSheet(f"background-color: {SURFACE_COLOR}; border-radius: 6px;")
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)

        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {TEXT_MUTED_COLOR};")
            value_label = QLabel(str(value))
            value_label.setStyleSheet(f"color: {TEXT_COLOR};")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            grid.addWidget(name_label, row, 0, Qt.AlignTop)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)

        self.content_layout.addWidget(card)

    def _add_section_title(self, title):
        label = QLabel(title)
        label.setStyleSheet(
            f"color: {TEXT_MUTED_COLOR}; font-weight: bold; font-size: 12px;"
            "letter-spacing: 1px; margin-top: 10px;"
        )
        self.content_layout.addWidget(label)


def _format_date(value):
    """Format a DICOM date (YYYYMMDD) as DD.MM.YYYY."""
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[6:8]}.{text[4:6]}.{text[0:4]}"
    return text


def _format_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
