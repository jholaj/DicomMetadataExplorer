"""Overview tab with validation results linked to elements and a file summary."""

import contextlib
import html

import numpy as np
from pydicom.dataset import Dataset
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from dicom_explorer.core.elements import format_date
from dicom_explorer.core.measurement import Spacing
from dicom_explorer.core.pixels import PixelDecodeError
from dicom_explorer.core.validation import ERROR, WARNING, Category, Issue, validate_dataset
from dicom_explorer.ui.text import plural

MISSING = "-"
SYMBOLS = {ERROR: "✕", WARNING: "⚠"}


class OverviewView(QWidget):
    element_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.issues: list[Issue] = []
        self._links = []

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.content_layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(scroll)
        self.clear()

    def clear(self) -> None:
        self.document = None
        self.issues = []
        self._clear_layout()
        placeholder = QLabel("No DICOM file loaded")
        placeholder.setObjectName("muted_label")
        placeholder.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(placeholder)

    def set_document(self, document, workspace_issues=()) -> None:
        if document is None:
            self.clear()
            return
        self.document = document
        pixels = None
        if document.has_pixels:
            with contextlib.suppress(PixelDecodeError):
                pixels = document.frame(0).raw
        report = validate_dataset(document.dataset, pixels)
        self.issues = report.sorted_issues() + list(workspace_issues)
        ds = document.dataset

        self._clear_layout()
        self._add_validation(report.iod)
        self._add_section(
            "Patient",
            [
                ("Name", _text(ds, "PatientName")),
                ("ID", _text(ds, "PatientID")),
                ("Birth date", format_date(_text(ds, "PatientBirthDate"))),
                ("Sex", _text(ds, "PatientSex")),
                ("Age", _text(ds, "PatientAge")),
                ("De-identified", _text(ds, "PatientIdentityRemoved")),
            ],
        )
        self._add_section(
            "Study",
            [
                ("Description", _text(ds, "StudyDescription")),
                ("Date", format_date(_text(ds, "StudyDate"))),
                ("Modality", _text(ds, "Modality")),
                ("Accession number", _text(ds, "AccessionNumber")),
                ("Study UID", _text(ds, "StudyInstanceUID")),
                ("Series description", _text(ds, "SeriesDescription")),
                ("Instance number", _text(ds, "InstanceNumber")),
            ],
        )
        if document.has_pixels:
            self._add_section("Image", self._image_rows(ds))
        self._add_section(
            "Equipment",
            [
                ("Manufacturer", _text(ds, "Manufacturer")),
                ("Model", _text(ds, "ManufacturerModelName")),
                ("Station name", _text(ds, "StationName")),
                ("KVP", _text(ds, "KVP")),
                ("Exposure time (ms)", _text(ds, "ExposureTime")),
                ("Tube current (mA)", _text(ds, "XRayTubeCurrent")),
                ("Exposure (mAs)", _text(ds, "Exposure")),
            ],
        )
        self._add_section("File", self._file_rows(ds))
        self.content_layout.addStretch()

    def _clear_layout(self):
        self._links = []
        while self.content_layout.count():
            widget = self.content_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _add_validation(self, iod: str):
        errors = sum(1 for issue in self.issues if issue.severity is ERROR)
        warnings = len(self.issues) - errors
        self._add_title(f"Validation · {iod}")
        if not self.issues:
            self._add_issue("ok", "No problems found", indent=False)
        else:
            summary = f"{plural(errors, 'error')}, {plural(warnings, 'warning')}"
            self._add_issue(ERROR if errors else WARNING, summary, indent=False)
        for category in Category:
            issues = [issue for issue in self.issues if issue.category is category]
            if issues:
                title = QLabel(category.value)
                title.setObjectName("issue_category")
                self.content_layout.addWidget(title)
            for issue in issues:
                self._add_issue(issue.severity, issue.message, issue.path)

    def _add_issue(self, severity, message: str, path=None, indent: bool = True):
        key = severity if isinstance(severity, str) else severity.value
        text = f"{SYMBOLS.get(severity, '✓')}  {html.escape(message)}"
        if path:
            self._links.append(path)
            text += f'  <a href="{len(self._links) - 1}">{html.escape(path.keywords())}</a>'
        label = QLabel(text)
        label.setObjectName("issue_label")
        label.setProperty("severity", key)
        label.setProperty("indent", indent)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.linkActivated.connect(
            lambda href: self.element_requested.emit(self._links[int(href)])
        )
        self.content_layout.addWidget(label)

    def _image_rows(self, ds: Dataset) -> list:
        frames = self.document.frame_count
        rows = [
            ("Dimensions", f"{_text(ds, 'Columns')} x {_text(ds, 'Rows')} px"),
            ("Frames", str(frames)),
            ("Bits", f"{_text(ds, 'BitsStored')} stored / {_text(ds, 'BitsAllocated')} allocated"),
            ("Photometric", _text(ds, "PhotometricInterpretation")),
            ("Presentation intent", _text(ds, "PresentationIntentType")),
        ]
        spacing = Spacing.of(ds)
        if spacing:
            note = f" ({spacing.note})" if spacing.note else ""
            rows.append(("Pixel spacing", f"{spacing.row:g} x {spacing.column:g} mm{note}"))
        else:
            rows.append(("Pixel spacing", f"{MISSING} (measurements in pixels)"))
        window = f"{_text(ds, 'WindowCenter')} / {_text(ds, 'WindowWidth')}"
        rows.append(("Window center / width", window))
        if "VOILUTSequence" in ds:
            rows.append(("VOI LUT", f"{len(ds.VOILUTSequence)} LUT(s)"))
        rescale = f"{_text(ds, 'RescaleSlope')} / {_text(ds, 'RescaleIntercept')}"
        rows.append(("Rescale slope / intercept", rescale))
        rows.append(("Burned-in annotation", _text(ds, "BurnedInAnnotation")))
        try:
            frame = self.document.frame(0)
        except PixelDecodeError:
            return [*rows, ("Pixel statistics", "pixel data cannot be decoded")]
        if not frame.is_color:
            low, high = frame.value_range
            first = " (frame 1)" if frames > 1 else ""
            rows.append((f"Value range{first}", f"{low:g} to {high:g}"))
            mean, std = float(np.mean(frame.values)), float(np.std(frame.values))
            rows.append((f"Mean / std dev{first}", f"{mean:.1f} / {std:.1f}"))
        return rows

    def _file_rows(self, ds: Dataset) -> list:
        path = self.document.path
        rows = [("Path", str(path))]
        with contextlib.suppress(OSError):
            rows.append(("Size", _size(path.stat().st_size)))
        syntax = getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None)
        sop_class = ds.get("SOPClassUID")
        rows.append(("Transfer syntax", syntax.name if syntax else MISSING))
        rows.append(("SOP class", sop_class.name if sop_class else MISSING))
        return rows

    def _add_section(self, title: str, rows: list):
        self._add_title(title)
        card = QFrame()
        card.setObjectName("overview_card")
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        for row, (name, value) in enumerate(rows):
            key = QLabel(name)
            key.setObjectName("card_key")
            value_label = QLabel(str(value))
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            grid.addWidget(key, row, 0, Qt.AlignTop)
            grid.addWidget(value_label, row, 1)
        self.content_layout.addWidget(card)

    def _add_title(self, title: str):
        label = QLabel(title)
        label.setObjectName("section_title")
        self.content_layout.addWidget(label)


def _text(ds: Dataset, keyword: str) -> str:
    value = ds.get(keyword)
    return MISSING if value is None or str(value) == "" else str(value)


def _size(size: float) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
