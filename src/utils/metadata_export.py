import csv
import json

from pydicom.sequence import Sequence


def dataset_to_list(dataset):
    """Convert a DICOM dataset to a list of tag dictionaries (recursively)."""
    items = []
    for elem in dataset:
        if elem.tag.group == 0x7FE0:  # Skip pixel data
            continue

        entry = {
            "tag": f"({elem.tag.group:04x},{elem.tag.element:04x})",
            "name": elem.name or "",
            "vr": str(getattr(elem, "VR", "") or ""),
        }

        if isinstance(elem.value, Sequence):
            entry["value"] = [dataset_to_list(item) for item in elem.value]
        elif isinstance(elem.value, bytes):
            entry["value"] = "<binary data>"
        else:
            entry["value"] = str(elem.value)

        items.append(entry)
    return items


def export_to_json(dataset, file_path):
    """Export dataset metadata to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(dataset_to_list(dataset), f, indent=2, ensure_ascii=False)


def export_to_csv(dataset, file_path):
    """Export dataset metadata to a CSV file (sequences flattened with depth)."""
    rows = []

    def flatten(items, depth):
        for entry in items:
            if isinstance(entry["value"], list):
                rows.append(
                    (
                        depth,
                        entry["tag"],
                        entry["name"],
                        entry["vr"],
                        f"<sequence of {len(entry['value'])} items>",
                    )
                )
                for sub_items in entry["value"]:
                    flatten(sub_items, depth + 1)
            else:
                rows.append((depth, entry["tag"], entry["name"], entry["vr"], entry["value"]))

    flatten(dataset_to_list(dataset), 0)

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Depth", "Tag", "Name", "VR", "Value"])
        writer.writerows(rows)
