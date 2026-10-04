"""Structured report content tree rendered as a readable document."""

import html

from PySide6.QtWidgets import QTextBrowser

from dicom_explorer.core.elements import format_date
from dicom_explorer.styles.theme import ACCENT_COLOR, TEXT_COLOR, TEXT_MUTED_COLOR

STYLE = f"""
body {{ color: {TEXT_COLOR}; font-size: 14px; }}
h2 {{ margin-bottom: 2px; }}
.meta {{ color: {TEXT_MUTED_COLOR}; margin-top: 0px; }}
.section {{ color: {ACCENT_COLOR}; margin-top: 10px; margin-bottom: 2px; }}
.label {{ color: {TEXT_MUTED_COLOR}; }}
p {{ margin-top: 2px; margin-bottom: 2px; }}
"""


class ReportView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.document().setDefaultStyleSheet(STYLE)

    def load_report(self, dataset):
        parts = [self._render_header(dataset)]
        parts.extend(self._render_items(getattr(dataset, "ContentSequence", []), level=0))
        self.setHtml("<body>" + "".join(parts) + "</body>")

    def _render_header(self, dataset):
        title = _concept_name(dataset) or "Structured Report"
        flags = (dataset.get("CompletionFlag", ""), dataset.get("VerificationFlag", ""))
        meta = [format_date(dataset.get("ContentDate", ""))]
        meta += [str(flag).capitalize() for flag in flags]
        meta = " · ".join(part for part in meta if part)
        return f'<h2>{html.escape(title)}</h2><p class="meta">{html.escape(meta)}</p>'

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
                        f'<p class="section" style="margin-left: {indent}px; '
                        f'font-size: {size}px;"><b>{html.escape(label)}</b></p>'
                    )
                parts.extend(self._render_items(getattr(item, "ContentSequence", []), level + 1))
                continue

            value = item_value(item, value_type)
            if value or label:
                label_html = f'<span class="label">{html.escape(label)}: </span>' if label else ""
                value_html = html.escape(value).replace("\n", "<br>")
                parts.append(f'<p style="margin-left: {indent}px;">{label_html}{value_html}</p>')
            parts.extend(self._render_items(getattr(item, "ContentSequence", []), level + 1))
        return parts


def _concept_name(item) -> str:
    sequence = getattr(item, "ConceptNameCodeSequence", None)
    if sequence:
        return str(getattr(sequence[0], "CodeMeaning", "") or "")
    return ""


def item_value(item, value_type) -> str:
    if value_type == "TEXT":
        return str(getattr(item, "TextValue", "") or "")
    if value_type == "NUM":
        measured = getattr(item, "MeasuredValueSequence", None)
        if measured:
            value = str(getattr(measured[0], "NumericValue", "") or "")
            units = getattr(measured[0], "MeasurementUnitsCodeSequence", None)
            unit = str(getattr(units[0], "CodeMeaning", "") or "") if units else ""
            return f"{value} {unit}".strip()
        return ""
    if value_type == "CODE":
        sequence = getattr(item, "ConceptCodeSequence", None)
        return str(getattr(sequence[0], "CodeMeaning", "") or "") if sequence else ""
    if value_type == "PNAME":
        return str(getattr(item, "PersonName", "") or "")
    if value_type in ("DATETIME", "DATE", "TIME"):
        for keyword in ("DateTime", "Date", "Time"):
            value = getattr(item, keyword, None)
            if value:
                return str(value)
        return ""
    if value_type == "UIDREF":
        return str(getattr(item, "UID", "") or "")
    if value_type in ("IMAGE", "COMPOSITE", "WAVEFORM"):
        referenced = getattr(item, "ReferencedSOPSequence", None)
        if referenced:
            uid = str(getattr(referenced[0], "ReferencedSOPInstanceUID", "") or "")
            return f"Reference: {uid}"
        return ""
    if value_type in ("SCOORD", "SCOORD3D"):
        graphic = str(getattr(item, "GraphicType", "") or "")
        points = list(getattr(item, "GraphicData", []) or [])
        shown = ", ".join(f"{float(v):g}" for v in points[:8])
        more = " …" if len(points) > 8 else ""
        return f"{graphic} ({shown}{more})".strip()
    return str(getattr(item, "TextValue", "") or "")
