"""Consistency checks for DICOM datasets.

validate_dataset() returns a list of (severity, message) issues and the
number of checks performed. Severity is "error" or "warning".
"""

ERROR = "error"
WARNING = "warning"

REQUIRED_TAGS = (
    "SOPClassUID",
    "SOPInstanceUID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "Modality",
)

RECOMMENDED_TAGS = (
    "PatientName",
    "PatientID",
    "StudyDate",
)

KNOWN_PHOTOMETRIC = {
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


def validate_dataset(dataset):
    """Run consistency checks; return (issues, checks_run)."""
    issues = []
    checks = 0

    def check(condition, severity, message):
        nonlocal checks
        checks += 1
        if not condition:
            issues.append((severity, message))

    # Required and recommended tags
    for keyword in REQUIRED_TAGS:
        check(getattr(dataset, keyword, None), ERROR, f"Missing required tag: {keyword}")
    for keyword in RECOMMENDED_TAGS:
        check(str(getattr(dataset, keyword, "") or ""), WARNING, f"Missing or empty tag: {keyword}")

    # File meta / transfer syntax
    file_meta = getattr(dataset, "file_meta", None)
    transfer_syntax = getattr(file_meta, "TransferSyntaxUID", None)
    check(transfer_syntax is not None, WARNING, "No TransferSyntaxUID in file meta")

    media_sop_class = getattr(file_meta, "MediaStorageSOPClassUID", None)
    sop_class = getattr(dataset, "SOPClassUID", None)
    if media_sop_class and sop_class:
        check(
            media_sop_class == sop_class,
            WARNING,
            "SOPClassUID differs from MediaStorageSOPClassUID in file meta",
        )

    if "PixelData" not in dataset:
        check(False, WARNING, "No pixel data present")
        return issues, checks

    issues_px, checks_px = _validate_pixel_module(dataset, transfer_syntax)
    return issues + issues_px, checks + checks_px


def _validate_pixel_module(dataset, transfer_syntax):
    issues = []
    checks = 0

    def check(condition, severity, message):
        nonlocal checks
        checks += 1
        if not condition:
            issues.append((severity, message))

    rows = getattr(dataset, "Rows", None)
    columns = getattr(dataset, "Columns", None)
    check(rows and columns, ERROR, "PixelData present but Rows/Columns missing")

    bits_allocated = getattr(dataset, "BitsAllocated", None)
    bits_stored = getattr(dataset, "BitsStored", None)
    high_bit = getattr(dataset, "HighBit", None)

    check(bits_allocated in (1, 8, 16, 32), ERROR, f"Unusual BitsAllocated: {bits_allocated}")
    if bits_allocated and bits_stored:
        check(
            bits_stored <= bits_allocated,
            ERROR,
            f"BitsStored ({bits_stored}) > BitsAllocated ({bits_allocated})",
        )
    if bits_stored is not None and high_bit is not None:
        check(
            high_bit == bits_stored - 1,
            WARNING,
            f"HighBit ({high_bit}) is not BitsStored - 1 ({bits_stored - 1})",
        )

    pixel_representation = getattr(dataset, "PixelRepresentation", None)
    check(
        pixel_representation in (0, 1, None),
        ERROR,
        f"Invalid PixelRepresentation: {pixel_representation}",
    )

    # Photometric interpretation vs samples per pixel
    photometric = str(getattr(dataset, "PhotometricInterpretation", "") or "").strip().upper()
    samples = getattr(dataset, "SamplesPerPixel", 1)
    check(photometric != "", WARNING, "Missing PhotometricInterpretation")
    if photometric:
        expected_samples = KNOWN_PHOTOMETRIC.get(photometric)
        check(
            expected_samples is not None,
            WARNING,
            f"Unknown PhotometricInterpretation: {photometric}",
        )
        if expected_samples is not None:
            check(
                samples == expected_samples,
                ERROR,
                f"{photometric} expects SamplesPerPixel {expected_samples}, got {samples}",
            )

    # Pixel data length (uncompressed only; encapsulated data has its own framing)
    if (
        rows
        and columns
        and bits_allocated
        and (transfer_syntax is None or not transfer_syntax.is_compressed)
    ):
        frames = int(getattr(dataset, "NumberOfFrames", 1) or 1)
        expected = int(rows) * int(columns) * int(samples) * frames * (bits_allocated // 8)
        actual = len(dataset.PixelData)
        check(
            abs(actual - expected) <= 1,
            ERROR,
            f"PixelData length {actual} does not match expected {expected} "
            f"({columns}x{rows}, {samples} samples, {frames} frame(s), "
            f"{bits_allocated} bits)",
        )

    # Window values sanity
    window_width = getattr(dataset, "WindowWidth", None)
    if window_width is not None:
        try:
            widths = window_width if isinstance(window_width, (list, tuple)) else [window_width]
            check(
                all(float(width) > 0 for width in widths),
                WARNING,
                f"WindowWidth should be positive, got {window_width}",
            )
        except (TypeError, ValueError):
            check(False, WARNING, f"WindowWidth is not numeric: {window_width}")

    # Decodability + value range
    try:
        pixels = dataset.pixel_array
        checks += 1
        if bits_stored:
            check(
                pixels.max() < 2**bits_stored,
                WARNING,
                f"Pixel values exceed the BitsStored ({bits_stored}) range",
            )
    except Exception as e:
        checks += 1
        issues.append((ERROR, f"Pixel data cannot be decoded: {e}"))

    # Spacing available for measurements
    check(
        getattr(dataset, "PixelSpacing", None) is not None
        or getattr(dataset, "ImagerPixelSpacing", None) is not None,
        WARNING,
        "No PixelSpacing/ImagerPixelSpacing - distance measurements unavailable",
    )

    return issues, checks
