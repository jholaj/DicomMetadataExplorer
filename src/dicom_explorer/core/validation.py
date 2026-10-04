"""Validation of DICOM datasets and of consistency between loaded files."""

import datetime
import math
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import pydicom.config
from pydicom.datadict import dictionary_VM
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.tag import Tag
from pydicom.uid import UID
from pydicom.valuerep import validate_value

from dicom_explorer.core.elements import (
    ElementPath,
    element_name,
    element_vr,
    float_values,
    format_tag,
    is_binary,
    is_pixel_data,
    value_multiplicity,
    walk,
)
from dicom_explorer.core.iod import IOD, MONOCHROME, Attr
from dicom_explorer.core.pixels import PixelDecodeError, decode_frame, frame_count, has_pixel_data


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


class Category(Enum):
    FILE_META = "File meta"
    IOD = "IOD"
    PIXEL_DATA = "Pixel data"
    VALUES = "Values"
    CONSISTENCY = "Consistency"
    WORKSPACE = "Workspace"


ERROR, WARNING = Severity.ERROR, Severity.WARNING

SAMPLES_PER_PHOTOMETRIC = {
    "MONOCHROME1": 1,
    "MONOCHROME2": 1,
    "PALETTE COLOR": 1,
    "RGB": 3,
    "YBR_FULL": 3,
    "YBR_FULL_422": 3,
    "YBR_PARTIAL_420": 3,
    "YBR_ICT": 3,
    "YBR_RCT": 3,
}
LOSSY_TRANSFER_SYNTAXES = frozenset(
    {
        "1.2.840.10008.1.2.4.50",  # JPEG Baseline
        "1.2.840.10008.1.2.4.51",  # JPEG Extended
        "1.2.840.10008.1.2.4.81",  # JPEG-LS Near-Lossless
        "1.2.840.10008.1.2.4.91",  # JPEG 2000
        "1.2.840.10008.1.2.4.93",  # JPEG 2000 Part 2
        "1.2.840.10008.1.2.4.203",  # HTJ2K
        *(f"1.2.840.10008.1.2.4.{n}" for n in range(100, 109)),  # MPEG and HEVC
    }
)
ITEM_TAG = b"\xfe\xff\x00\xe0"

# Attribute that must be equal in all files sharing the grouping attribute
UNIFORM_WITHIN = (
    ("StudyInstanceUID", "PatientID", ERROR),
    ("StudyInstanceUID", "PatientName", WARNING),
    ("StudyInstanceUID", "StudyDate", WARNING),
    ("SeriesInstanceUID", "StudyInstanceUID", ERROR),
    ("SeriesInstanceUID", "Modality", ERROR),
)


@dataclass(frozen=True)
class Issue:
    severity: Severity
    category: Category
    message: str
    path: ElementPath | None = None


@dataclass
class ValidationReport:
    iod: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is WARNING)

    def sorted_issues(self) -> list[Issue]:
        categories, severities = list(Category), list(Severity)
        return sorted(
            self.issues,
            key=lambda i: (categories.index(i.category), severities.index(i.severity)),
        )


def validate_dataset(dataset: Dataset, pixels: np.ndarray | None = None) -> ValidationReport:
    """Validate one dataset, the first frame is decoded unless pixels are given."""
    context = _Context(dataset, IOD.of(dataset), pixels)
    report = ValidationReport(context.iod.name)
    for category, check in _CHECKS:
        for severity, message, where in check(context):
            path = ElementPath.top(where) if isinstance(where, str) else where
            report.issues.append(Issue(severity, category, message, path))
    return report


def validate_workspace(datasets: dict[Path, Dataset]) -> dict[Path, list[Issue]]:
    """Issues found by comparing the loaded files, keyed by file."""
    issues = defaultdict(list)
    for paths, issue in _workspace_findings(datasets):
        for path in paths:
            issues[path].append(issue)
    return dict(issues)


def vm_allows(spec: str, count: int) -> bool:
    """True when count values satisfy a dictionary VM like 1, 1-3, 1-n or 2-2n."""
    if " or " in spec:
        return any(vm_allows(part, count) for part in spec.split(" or "))
    if "-" not in spec:
        return not spec.isdigit() or count == int(spec)
    low, high = spec.split("-", 1)
    if count < (int(low) if low.isdigit() else 1):
        return False
    if high.endswith("n"):
        return count % int(high[:-1] or 1) == 0
    return count <= int(high)


@dataclass(frozen=True)
class _Context:
    dataset: Dataset
    iod: IOD
    pixels: np.ndarray | None


def _check_file_meta(context: _Context) -> Iterator:
    ds = context.dataset
    meta = getattr(ds, "file_meta", None)
    if not meta:
        yield WARNING, "No file meta information (file without a PS3.10 header)", None
        return

    syntax = meta.get("TransferSyntaxUID")
    if syntax is None:
        yield ERROR, "Missing TransferSyntaxUID in the file meta", None
    elif not UID(syntax).is_transfer_syntax:
        yield ERROR, f"Unknown transfer syntax {syntax}", _meta("TransferSyntaxUID")

    for meta_keyword, keyword in (
        ("MediaStorageSOPClassUID", "SOPClassUID"),
        ("MediaStorageSOPInstanceUID", "SOPInstanceUID"),
    ):
        meta_value, value = meta.get(meta_keyword), ds.get(keyword)
        if meta_value is None:
            yield ERROR, f"Missing {meta_keyword} in the file meta", None
        elif value is not None and str(meta_value) != str(value):
            message = f"{meta_keyword} ({meta_value}) differs from {keyword} ({value})"
            yield ERROR, message, _meta(meta_keyword)

    if not syntax or not UID(syntax).is_transfer_syntax or "PixelData" not in ds:
        return
    syntax = UID(syntax)
    if syntax.is_encapsulated and bytes(ds.PixelData[:4]) != ITEM_TAG:
        yield ERROR, f"{syntax.name} requires encapsulated pixel data", "PixelData"
    lossy = str(ds.get("LossyImageCompression", ""))
    if syntax in LOSSY_TRANSFER_SYNTAXES and lossy != "01":
        message = f"Lossy {syntax.name} but LossyImageCompression is '{lossy or 'not set'}'"
        yield WARNING, message, "LossyImageCompression"


def _check_modules(context: _Context) -> Iterator:
    ds, iod = context.dataset, context.iod
    missing = set()
    for module, attr in iod.requirements():
        if attr.keyword in missing or (attr.condition and not attr.condition.test(ds)):
            continue
        problem = _requirement_problem(ds, module, attr)
        if problem:
            missing.add(attr.keyword)
            yield problem
            continue
        invalid = [str(v) for v in _values(ds[attr.keyword].value) if not _allowed(v, attr)]
        if invalid:
            expected = " / ".join(str(v) for v in attr.enum)
            message = f"{attr.keyword} is '{', '.join(invalid)}', expected {expected}"
            yield WARNING, message, attr.keyword

    modality = str(ds.get("Modality", ""))
    if iod.modalities and modality and modality not in iod.modalities:
        message = f"Modality '{modality}' does not match {iod.name} ({', '.join(iod.modalities)})"
        yield ERROR, message, "Modality"


def _check_pixel_module(context: _Context) -> Iterator:
    ds = context.dataset
    if not has_pixel_data(ds):
        return
    rows, columns = _int(ds, "Rows"), _int(ds, "Columns")
    allocated, stored = _int(ds, "BitsAllocated"), _int(ds, "BitsStored")
    high_bit = _int(ds, "HighBit")
    samples = _int(ds, "SamplesPerPixel") or 1
    photometric = str(ds.get("PhotometricInterpretation", "")).strip().upper()

    if not rows or not columns:
        yield ERROR, "Pixel data present but Rows or Columns missing", None
    if allocated not in (None, 1, 8, 16, 32, 64):
        yield ERROR, f"Unusual BitsAllocated {allocated}", "BitsAllocated"
    if allocated and stored and stored > allocated:
        yield ERROR, f"BitsStored {stored} exceeds BitsAllocated {allocated}", "BitsStored"
    if stored is not None and high_bit is not None and high_bit != stored - 1:
        yield WARNING, f"HighBit {high_bit} is not BitsStored - 1 ({stored - 1})", "HighBit"

    expected_samples = SAMPLES_PER_PHOTOMETRIC.get(photometric)
    if photometric and expected_samples is None:
        message = f"Unknown PhotometricInterpretation {photometric}"
        yield WARNING, message, "PhotometricInterpretation"
    elif expected_samples and samples != expected_samples:
        message = f"{photometric} expects SamplesPerPixel {expected_samples}, got {samples}"
        yield ERROR, message, "SamplesPerPixel"

    syntax = getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None)
    native = syntax is None or not UID(syntax).is_encapsulated
    if native and rows and columns and allocated and "PixelData" in ds:
        expected = math.ceil(rows * columns * samples * frame_count(ds) * allocated / 8)
        actual = len(ds.PixelData)
        if actual < expected:
            yield ERROR, f"PixelData has {actual} bytes, expected {expected}", "PixelData"
        elif actual > expected + 1:
            yield WARNING, f"PixelData has {actual - expected} trailing bytes", "PixelData"
        yield from _unused_high_bits(ds, allocated, stored)

    yield from _window_and_rescale(ds)
    yield from _decoded_range(context, stored)

    for keyword in ("PixelSpacing", "ImagerPixelSpacing"):
        values = float_values(ds.get(keyword))
        if values and (len(values) != 2 or min(values) <= 0):
            yield ERROR, f"{keyword} must be two positive values, got {values}", keyword


def _check_values(context: _Context) -> Iterator:
    ds = context.dataset
    for entry in walk(ds, include_meta=True):
        element, tag = entry.element, entry.element.tag
        label = f"{format_tag(tag)} {element.keyword or element_name(element)}".strip()
        if tag.is_private and tag.element >= 0x1000:
            creator = Tag(tag.group, tag.element >> 8)
            if creator not in entry.container:
                yield WARNING, f"{label} has no Private Creator {format_tag(creator)}", entry.path
        if element_vr(element) == "SQ" or is_binary(element) or is_pixel_data(element):
            continue
        if not _empty(element.value):
            for problem in (_vr_problem(element), _vm_problem(element)):
                if problem:
                    yield WARNING, f"{label}: {problem}", entry.path

    if "SpecificCharacterSet" not in ds:
        for entry in walk(ds):
            value = entry.element.value
            if isinstance(value, str) and not value.isascii():
                yield WARNING, "Non-ASCII text without SpecificCharacterSet", entry.path
                break


def _check_consistency(context: _Context) -> Iterator:
    ds, iod = context.dataset, context.iod
    keywords = ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID")
    uids = [str(ds.get(keyword)) for keyword in keywords if ds.get(keyword)]
    if len(set(uids)) != len(uids):
        yield ERROR, "Study, Series and SOP Instance UIDs must all differ", "SOPInstanceUID"

    intent = str(ds.get("PresentationIntentType", "")).strip().upper()
    if iod.intent and intent and intent != iod.intent:
        message = f"PresentationIntentType {intent} does not match {iod.name}"
        yield ERROR, message, "PresentationIntentType"

    if iod.is_projection:
        photometric = str(ds.get("PhotometricInterpretation", "")).strip().upper()
        shape = str(ds.get("PresentationLUTShape", "")).strip().upper()
        expected = "INVERSE" if photometric == "MONOCHROME1" else "IDENTITY"
        if shape and photometric in MONOCHROME and shape != expected:
            message = f"PresentationLUTShape must be {expected} for {photometric}, got {shape}"
            yield ERROR, message, "PresentationLUTShape"
        has_voi = "VOILUTSequence" in ds or ("WindowCenter" in ds and "WindowWidth" in ds)
        if intent == "FOR PRESENTATION" and not has_voi:
            yield ERROR, "FOR PRESENTATION image without a window or VOI LUT", None

    image_type = [str(v).upper() for v in _values(ds.get("ImageType"))]
    if image_type and image_type[0] not in ("ORIGINAL", "DERIVED"):
        message = f"ImageType value 1 should be ORIGINAL or DERIVED, got {image_type[0]}"
        yield WARNING, message, "ImageType"
    if len(image_type) > 1 and image_type[1] not in ("PRIMARY", "SECONDARY"):
        message = f"ImageType value 2 should be PRIMARY or SECONDARY, got {image_type[1]}"
        yield WARNING, message, "ImageType"

    yield from _dates(ds)


def _workspace_findings(datasets: dict[Path, Dataset]) -> Iterator:
    for paths in _group_by(datasets, "SOPInstanceUID").values():
        if len(paths) > 1:
            message = f"Duplicate SOPInstanceUID in {len(paths)} files"
            yield paths, _workspace_issue(ERROR, message, "SOPInstanceUID")
    for group_keyword, keyword, severity in UNIFORM_WITHIN:
        group = group_keyword.removesuffix("InstanceUID").lower()
        for paths in _group_by(datasets, group_keyword).values():
            values = sorted({str(datasets[path].get(keyword, "")) for path in paths})
            if len(values) > 1:
                shown = ", ".join(f"'{value}'" for value in values)
                message = f"{keyword} differs within the {group}: {shown}"
                yield paths, _workspace_issue(severity, message, keyword)


_CHECKS = (
    (Category.FILE_META, _check_file_meta),
    (Category.IOD, _check_modules),
    (Category.PIXEL_DATA, _check_pixel_module),
    (Category.VALUES, _check_values),
    (Category.CONSISTENCY, _check_consistency),
)


def _requirement_problem(ds: Dataset, module: str, attr: Attr):
    when = f", required when {attr.condition.text}" if attr.condition else ""
    label = f"{attr.keyword} ({module} module{when})"
    if attr.keyword not in ds:
        return (ERROR if attr.type == 1 else WARNING), f"Missing Type {attr.type} {label}", None
    if attr.type == 1 and _empty(ds[attr.keyword].value):
        return ERROR, f"Empty Type 1 {label}", attr.keyword
    return None


def _window_and_rescale(ds: Dataset) -> Iterator:
    centers = float_values(ds.get("WindowCenter"))
    widths = float_values(ds.get("WindowWidth"))
    if widths and min(widths) <= 0:
        yield ERROR, f"WindowWidth must be positive, got {widths}", "WindowWidth"
    if len(centers) != len(widths):
        message = f"{len(centers)} WindowCenter value(s) but {len(widths)} WindowWidth value(s)"
        yield WARNING, message, "WindowCenter"
    slope = float_values(ds.get("RescaleSlope"))
    if slope and slope[0] == 0:
        yield ERROR, "RescaleSlope must not be 0", "RescaleSlope"
    if "ModalityLUTSequence" in ds and "RescaleSlope" in ds:
        message = "ModalityLUTSequence and RescaleSlope are mutually exclusive"
        yield WARNING, message, "ModalityLUTSequence"
    for index, item in enumerate(ds.get("VOILUTSequence") or []):
        if len(item.get("LUTDescriptor") or []) != 3:
            path = ElementPath.top("VOILUTSequence").child(index).child(Tag("LUTDescriptor"))
            yield ERROR, f"VOILUTSequence item {index + 1} has no valid LUTDescriptor", path


def _unused_high_bits(ds: Dataset, allocated: int, stored: int | None) -> Iterator:
    """Stored values above BitsStored, decoders mask them silently."""
    if _int(ds, "PixelRepresentation") != 0 or allocated not in (8, 16, 32):
        return
    if not stored or stored >= allocated:
        return
    dtype = np.dtype({8: "u1", 16: "<u2", 32: "<u4"}[allocated])
    data = bytes(ds.PixelData)
    raw = np.frombuffer(data[: len(data) - len(data) % dtype.itemsize], dtype=dtype)
    if raw.size and int(raw.max()) >= 2**stored:
        message = f"Stored values up to {int(raw.max())} use bits above BitsStored {stored}"
        yield WARNING, message, "BitsStored"


def _decoded_range(context: _Context, stored: int | None) -> Iterator:
    pixels = context.pixels
    if pixels is None:
        try:
            pixels, _ = decode_frame(context.dataset)
        except PixelDecodeError as e:
            yield ERROR, f"Pixel data cannot be decoded: {e}", None
            return
    if not stored or pixels.dtype.kind not in "iu":
        return
    if _int(context.dataset, "PixelRepresentation") == 1:
        minimum, maximum = -(2 ** (stored - 1)), 2 ** (stored - 1) - 1
    else:
        minimum, maximum = 0, 2**stored - 1
    low, high = int(pixels.min()), int(pixels.max())
    if low < minimum or high > maximum:
        yield WARNING, f"Pixel values {low}..{high} exceed BitsStored {stored}", "BitsStored"


def _dates(ds: Dataset) -> Iterator:
    today = datetime.date.today()
    study, birth = _date(ds.get("StudyDate")), _date(ds.get("PatientBirthDate"))
    for keyword, value in (("StudyDate", study), ("PatientBirthDate", birth)):
        if value and value > today:
            yield WARNING, f"{keyword} {value.isoformat()} is in the future", keyword
    if not (study and birth):
        return
    if birth > study:
        yield ERROR, f"PatientBirthDate {birth} is after StudyDate {study}", "PatientBirthDate"
    age = str(ds.get("PatientAge", "")).strip()
    if len(age) == 4 and age[:3].isdigit() and age[3] == "Y":
        years = study.year - birth.year - ((study.month, study.day) < (birth.month, birth.day))
        if abs(years - int(age[:3])) > 1:
            message = f"PatientAge {age} does not match the dates ({years} years)"
            yield WARNING, message, "PatientAge"


def _vr_problem(element: DataElement) -> str | None:
    vr = element_vr(element)
    for value in _values(element.value):
        if vr in ("DS", "IS") and not isinstance(value, str):
            value = getattr(value, "original_string", None) or str(value)
        try:
            validate_value(vr, value, pydicom.config.RAISE)
        except ValueError as e:
            return str(e).split(" Please see")[0]
        except Exception:
            return None
    return None


def _vm_problem(element: DataElement) -> str | None:
    if element.tag.is_private:
        return None
    try:
        spec = dictionary_VM(element.tag)
    except KeyError:
        return None
    count = value_multiplicity(element)
    return None if vm_allows(spec, count) else f"{count} value(s), dictionary VM is {spec}"


def _group_by(datasets: dict[Path, Dataset], keyword: str) -> dict[str, list[Path]]:
    groups = defaultdict(list)
    for path, ds in datasets.items():
        if ds.get(keyword):
            groups[str(ds.get(keyword))].append(path)
    return groups


def _workspace_issue(severity: Severity, message: str, keyword: str) -> Issue:
    return Issue(severity, Category.WORKSPACE, message, ElementPath.top(keyword))


def _meta(keyword: str) -> ElementPath:
    return ElementPath.top(keyword, meta=True)


def _values(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (MultiValue, list, tuple)) else [value]


def _allowed(value, attr: Attr) -> bool:
    return not attr.enum or str(value).strip() in {str(v) for v in attr.enum}


def _empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (bytes, list, tuple, MultiValue)):
        return len(value) == 0
    return not str(value).strip()


def _int(ds: Dataset, keyword: str) -> int | None:
    try:
        value = ds.get(keyword)
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _date(value) -> datetime.date | None:
    text = str(value or "").strip()
    try:
        return datetime.datetime.strptime(text, "%Y%m%d").date() if len(text) == 8 else None
    except ValueError:
        return None
