"""Readable rendering of DICOM Structured Reports (SR) in the Content tab."""

import html

from PySide6.QtWidgets import QTextBrowser

from styles.theme import ACCENT_COLOR, TEXT_COLOR, TEXT_MUTED_COLOR


class ReportViewer(QTextBrowser):
    """Renders the content tree of a structured report as a document."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)

    @staticmethod
    def is_report(dataset) -> bool:
        """True when the dataset carries an SR content tree."""
        return "ContentSequence" in dataset

    def load_report(self, dataset):
        """Render the dataset's SR content tree."""
        parts = [self._render_header(dataset)]
        parts.extend(self._render_items(dataset.ContentSequence, level=0))
        self.setHtml(
            f'<div style="color: {TEXT_COLOR}; font-size: 14px; line-height: 1.5;">'
            + "".join(parts)
            + "</div>"
        )

    def _render_header(self, dataset):
        title = _concept_name(dataset) or "Structured Report"
        meta = []
        completion = str(getattr(dataset, "CompletionFlag", "") or "")
        verification = str(getattr(dataset, "VerificationFlag", "") or "")
        content_date = str(getattr(dataset, "ContentDate", "") or "")
        if content_date and len(content_date) == 8:
            meta.append(f"{content_date[6:8]}.{content_date[4:6]}.{content_date[0:4]}")
        if completion:
            meta.append(completion.capitalize())
        if verification:
            meta.append(verification.capitalize().replace("_", " "))

        header = f'<h2 style="color: {TEXT_COLOR}; margin-bottom: 2px;">{html.escape(title)}</h2>'
        if meta:
            header += (
                f'<p style="color: {TEXT_MUTED_COLOR}; margin-top: 0px;">'
                f"{html.escape(' · '.join(meta))}</p>"
            )
        return header

    def _render_items(self, items, level):
        parts = []
        indent = level * 18

        for item in items:
            value_type = str(getattr(item, "ValueType", "") or "")
            label = _concept_name(item)

            if value_type == "CONTAINER":
                if label:
                    size = max(13, 17 - level)
                    parts.append(
                        f'<h3 style="color: {ACCENT_COLOR}; font-size: {size}px; '
                        f'margin: 10px 0px 2px {indent}px;">{html.escape(label)}</h3>'
                    )
                if "ContentSequence" in item:
                    parts.extend(self._render_items(item.ContentSequence, level + 1))
                continue

            value = _item_value(item, value_type)
            if not value and not label:
                continue

            label_html = (
                f'<span style="color: {TEXT_MUTED_COLOR};">{html.escape(label)}: </span>'
                if label
                else ""
            )
            value_html = html.escape(value).replace("\n", "<br>")
            parts.append(f'<p style="margin: 2px 0px 2px {indent}px;">{label_html}{value_html}</p>')

            if "ContentSequence" in item:
                parts.extend(self._render_items(item.ContentSequence, level + 1))

        return parts


def _concept_name(item) -> str:
    """CodeMeaning of the item's concept name, if any."""
    sequence = getattr(item, "ConceptNameCodeSequence", None)
    if sequence:
        return str(getattr(sequence[0], "CodeMeaning", "") or "")
    return ""


def _item_value(item, value_type) -> str:
    """Human-readable value of a non-container content item."""
    if value_type == "TEXT":
        return str(getattr(item, "TextValue", "") or "")

    if value_type == "NUM":
        measured = getattr(item, "MeasuredValueSequence", None)
        if measured:
            value = str(getattr(measured[0], "NumericValue", "") or "")
            units_seq = getattr(measured[0], "MeasurementUnitsCodeSequence", None)
            units = str(getattr(units_seq[0], "CodeMeaning", "") or "") if units_seq else ""
            return f"{value} {units}".strip()
        return ""

    if value_type == "CODE":
        sequence = getattr(item, "ConceptCodeSequence", None)
        if sequence:
            return str(getattr(sequence[0], "CodeMeaning", "") or "")
        return ""

    if value_type == "PNAME":
        return str(getattr(item, "PersonName", "") or "")

    if value_type in ("DATETIME", "DATE", "TIME"):
        return str(
            getattr(item, "DateTime", None)
            or getattr(item, "Date", None)
            or getattr(item, "Time", None)
            or ""
        )

    if value_type == "UIDREF":
        return str(getattr(item, "UID", "") or "")

    if value_type in ("IMAGE", "COMPOSITE", "WAVEFORM"):
        referenced = getattr(item, "ReferencedSOPSequence", None)
        if referenced:
            uid = str(getattr(referenced[0], "ReferencedSOPInstanceUID", "") or "")
            return f"Reference: {uid}"
        return ""

    # Fallback for unknown value types
    return str(getattr(item, "TextValue", "") or "")
