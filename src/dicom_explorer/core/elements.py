"""Addressing, walking, formatting, and parsing of DICOM data elements."""

import copy
import re
from collections.abc import Iterator
from dataclasses import dataclass

import pydicom.config
from pydicom.datadict import keyword_for_tag, tag_for_keyword
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.tag import BaseTag, Tag
from pydicom.valuerep import validate_value

BINARY_VRS = frozenset({"OB", "OD", "OF", "OL", "OV", "OW", "UN", "OB or OW", "US or OW"})
# Backslash is part of the text for these VRs, not a value delimiter
SINGLE_VALUE_TEXT_VRS = frozenset({"LT", "ST", "UT", "UR"})
INT_VRS = frozenset({"SL", "SS", "SV", "UL", "US", "UV"})
FLOAT_VRS = frozenset({"FL", "FD"})
PIXEL_DATA_TAGS = frozenset({0x7FE00008, 0x7FE00009, 0x7FE00010})
MAX_DISPLAY_LENGTH = 256


@dataclass(frozen=True, order=True)
class ElementPath:
    """Location in a dataset as alternating tags and sequence item indices.

    A path ending with a tag points to an element, an empty path or a path
    ending with an item index points to a dataset.
    """

    parts: tuple[int, ...] = ()
    meta: bool = False

    @classmethod
    def top(cls, tag, meta: bool = False) -> "ElementPath":
        return cls((int(Tag(tag)),), meta)

    @property
    def is_element(self) -> bool:
        return len(self.parts) % 2 == 1

    @property
    def tag(self) -> BaseTag:
        return Tag(self.parts[-1])

    @property
    def parent(self) -> "ElementPath":
        return ElementPath(self.parts[:-1], self.meta)

    def child(self, part: int) -> "ElementPath":
        return ElementPath((*self.parts, int(part)), self.meta)

    def dataset(self, root: Dataset) -> Dataset:
        """Dataset addressed by this path. Raises KeyError or IndexError when missing."""
        dataset = root.file_meta if self.meta else root
        parts = self.parts[:-1] if self.is_element else self.parts
        for tag, index in zip(parts[::2], parts[1::2], strict=True):
            dataset = dataset[tag].value[index]
        return dataset

    def element(self, root: Dataset) -> DataElement | None:
        try:
            return self.dataset(root).get(self.tag)
        except (KeyError, IndexError, TypeError, AttributeError):
            return None

    def keywords(self) -> str:
        """Path like ViewCodeSequence[0].CodeValue."""
        return ".".join(self._names(lambda tag: keyword_for_tag(tag) or format_tag(tag)))

    def tags(self) -> str:
        """Path like (0054,0220)[0] > (0008,0100)."""
        return " > ".join(self._names(format_tag))

    def _names(self, name) -> list[str]:
        names = ["FileMeta"] if self.meta else []
        for position, part in enumerate(self.parts):
            if position % 2 == 0:
                names.append(name(part))
            else:
                names[-1] += f"[{part}]"
        return names


@dataclass(frozen=True)
class WalkEntry:
    path: ElementPath
    container: Dataset
    element: DataElement
    depth: int


@dataclass(frozen=True)
class DatasetSnapshot:
    """Deep copy of a dataset's content with the pixel data shared."""

    elements: tuple
    file_meta: Dataset | None

    @classmethod
    def of(cls, dataset: Dataset) -> "DatasetSnapshot":
        elements = tuple(e if is_pixel_data(e) else copy.deepcopy(e) for e in dataset)
        file_meta = getattr(dataset, "file_meta", None)
        return cls(elements, copy.deepcopy(file_meta) if file_meta is not None else None)

    def restore(self, dataset: Dataset) -> None:
        """Replace the content of the dataset in place."""
        dataset.clear()
        for element in self.elements:
            dataset.add(element if is_pixel_data(element) else copy.deepcopy(element))
        if self.file_meta is not None:
            dataset.file_meta = copy.deepcopy(self.file_meta)


def walk(dataset: Dataset, include_meta: bool = False) -> Iterator[WalkEntry]:
    """Yield every element depth first, including elements nested in sequences."""
    file_meta = getattr(dataset, "file_meta", None)
    if include_meta and file_meta is not None:
        yield from _walk(file_meta, ElementPath(meta=True), 0)
    yield from _walk(dataset, ElementPath(), 0)


def common_elements(datasets: list[Dataset]) -> list[DataElement]:
    """Editable top level elements with the same VR and value in every dataset."""
    first, *others = datasets
    return [
        element
        for element in first
        if is_editable(element) and all(_same(element, other.get(element.tag)) for other in others)
    ]


def format_tag(tag) -> str:
    tag = Tag(tag)
    return f"({tag.group:04X},{tag.element:04X})"


def element_vr(element: DataElement) -> str:
    return str(getattr(element, "VR", "") or "")


def element_name(element: DataElement) -> str:
    try:
        return element.name or ""
    except Exception:
        return ""


def is_pixel_data(element: DataElement) -> bool:
    return int(element.tag) in PIXEL_DATA_TAGS


def is_binary(element: DataElement) -> bool:
    return element_vr(element) in BINARY_VRS or isinstance(element.value, (bytes, bytearray))


def is_editable(element: DataElement) -> bool:
    return (
        element_vr(element) != "SQ"
        and not isinstance(element.value, Sequence)
        and not is_binary(element)
        and not is_pixel_data(element)
    )


def value_text(element: DataElement) -> str:
    """Value in DICOM notation, multiple values joined by a backslash."""
    vr = element_vr(element)
    value = element.value
    if isinstance(value, Sequence) or vr == "SQ":
        count = len(value or [])
        return f"<sequence of {count} item{'s' if count != 1 else ''}>"
    if is_binary(element):
        length = len(value) if isinstance(value, (bytes, bytearray)) else 0
        return f"<binary data, {length} bytes>"
    if value is None:
        return ""
    if isinstance(value, (MultiValue, list, tuple)):
        return "\\".join(_format_single(v, vr) for v in value)
    return _format_single(value, vr)


def display_text(element: DataElement, limit: int = MAX_DISPLAY_LENGTH) -> str:
    text = value_text(element).replace("\r\n", " ").replace("\n", " ")
    return text[: limit - 1] + "…" if len(text) > limit else text


def value_multiplicity(element: DataElement) -> int:
    value = element.value
    if value is None or value == "":
        return 0
    if isinstance(value, (MultiValue, list, tuple)):
        return len(value)
    return 1


def format_date(value) -> str:
    """DICOM date YYYYMMDD as DD.MM.YYYY, other text unchanged."""
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[6:8]}.{text[4:6]}.{text[0:4]}"
    return text


def float_values(value) -> list[float]:
    """All values as floats, empty when missing or not numeric."""
    if value is None or value == "":
        return []
    try:
        if isinstance(value, (MultiValue, list, tuple)):
            return [float(v) for v in value]
        return [float(value)]
    except (TypeError, ValueError):
        return []


def first_float(value) -> float | None:
    values = float_values(value)
    return values[0] if values else None


def parse_value(text: str, vr: str):
    """Parse user input for the VR. Raises ValueError with a readable message."""
    vr = vr.strip().upper()
    if vr in BINARY_VRS or vr == "SQ":
        raise ValueError(f"Values with VR {vr} cannot be entered as text")
    if text == "":
        return None if vr in INT_VRS | FLOAT_VRS | {"AT"} else ""
    parts = [text] if vr in SINGLE_VALUE_TEXT_VRS else text.split("\\")
    values = [_parse_single(part, vr) for part in parts]
    return values[0] if len(values) == 1 else values


def parse_tag(text: str) -> BaseTag:
    """Tag from a keyword or a group,element pair. Raises ValueError."""
    text = text.strip()
    keyword_tag = tag_for_keyword(text)
    if keyword_tag is not None:
        return Tag(keyword_tag)
    match = re.fullmatch(r"([0-9A-Fa-f]{4}),?([0-9A-Fa-f]{4})", text.strip("()").replace(" ", ""))
    if not match:
        raise ValueError(f"'{text}' is not a keyword or (GGGG,EEEE) tag")
    return Tag(int(match.group(1), 16), int(match.group(2), 16))


def _walk(dataset: Dataset, prefix: ElementPath, depth: int) -> Iterator[WalkEntry]:
    for element in dataset:
        path = prefix.child(element.tag)
        yield WalkEntry(path, dataset, element, depth)
        if isinstance(element.value, Sequence):
            for index, item in enumerate(element.value):
                yield from _walk(item, path.child(index), depth + 1)


def _same(element: DataElement, other: DataElement | None) -> bool:
    return (
        other is not None
        and element_vr(other) == element_vr(element)
        and value_text(other) == value_text(element)
    )


def _format_single(value, vr: str) -> str:
    if vr == "AT":
        try:
            return format_tag(value)
        except Exception:
            return str(value)
    return str(value)


def _parse_single(text: str, vr: str):
    if vr in INT_VRS:
        value = _convert(int, text, f"'{text}' is not an integer (VR {vr})")
    elif vr in FLOAT_VRS:
        value = _convert(float, text, f"'{text}' is not a number (VR {vr})")
    elif vr == "AT":
        value = parse_tag(text)
    elif vr in ("DS", "IS"):
        value = text.strip()
    else:
        value = text
    try:
        validate_value(vr, value, pydicom.config.RAISE)
    except ValueError as e:
        raise ValueError(str(e).split(" Please see")[0]) from None
    return value


def _convert(kind, text: str, message: str):
    try:
        return kind(text.strip())
    except ValueError:
        raise ValueError(message) from None
