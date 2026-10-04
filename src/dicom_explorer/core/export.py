"""Metadata export to JSON, CSV, and the DICOM JSON Model."""

import csv
import json
from enum import Enum
from pathlib import Path

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from dicom_explorer.core.elements import (
    element_name,
    element_vr,
    format_tag,
    is_pixel_data,
    value_text,
    walk,
)


class ExportFormat(Enum):
    JSON = ("JSON", ".json")
    CSV = ("CSV", ".csv")
    DICOM_JSON = ("DICOM JSON Model", ".dcm.json")

    def __init__(self, label: str, suffix: str):
        self.label = label
        self.suffix = suffix

    @property
    def file_filter(self) -> str:
        return f"{self.label} (*{self.suffix})"

    @classmethod
    def for_path(cls, path: Path, fallback: "ExportFormat") -> "ExportFormat":
        """Format given by the file suffix, the fallback when the suffix is unknown."""
        name = path.name.lower()
        if name.endswith(cls.DICOM_JSON.suffix):
            return cls.DICOM_JSON
        if name.endswith(cls.JSON.suffix):
            return cls.DICOM_JSON if fallback is cls.DICOM_JSON else cls.JSON
        if name.endswith(cls.CSV.suffix):
            return cls.CSV
        return fallback

    def write(self, dataset: Dataset, path: Path) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            if self is ExportFormat.CSV:
                _write_csv(dataset, f)
            elif self is ExportFormat.DICOM_JSON:
                json.dump(_dicom_json(dataset), f, indent=2, ensure_ascii=False)
            else:
                json.dump(dataset_to_list(dataset), f, indent=2, ensure_ascii=False)


def dataset_to_list(dataset: Dataset) -> list[dict]:
    """Nested element dictionaries without pixel data."""
    items = []
    for element in dataset:
        if is_pixel_data(element):
            continue
        value = element.value
        items.append(
            {
                "tag": format_tag(element.tag),
                "keyword": element.keyword or "",
                "name": element_name(element),
                "vr": element_vr(element),
                "value": (
                    [dataset_to_list(item) for item in value]
                    if isinstance(value, Sequence)
                    else value_text(element)
                ),
            }
        )
    return items


def _write_csv(dataset: Dataset, file) -> None:
    writer = csv.writer(file)
    writer.writerow(["Depth", "Path", "Tag", "Name", "VR", "Value"])
    for entry in walk(dataset):
        element = entry.element
        if not is_pixel_data(element):
            writer.writerow(
                [
                    entry.depth,
                    entry.path.keywords(),
                    format_tag(element.tag),
                    element_name(element),
                    element_vr(element),
                    value_text(element),
                ]
            )


def _dicom_json(dataset: Dataset) -> dict:
    copy = Dataset()
    for element in dataset:
        if not is_pixel_data(element):
            copy.add(element)
    return copy.to_json_dict(bulk_data_threshold=2**31)
