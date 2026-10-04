"""Frame decoding that does not cache the decoded array on the dataset."""

import numpy as np
from pydicom.dataset import Dataset
from pydicom.pixels import get_decoder
from pydicom.uid import ExplicitVRBigEndian, ExplicitVRLittleEndian, ImplicitVRLittleEndian

PIXEL_KEYWORDS = ("PixelData", "FloatPixelData", "DoubleFloatPixelData")


class PixelDecodeError(Exception):
    pass


def has_pixel_data(dataset: Dataset) -> bool:
    return any(keyword in dataset for keyword in PIXEL_KEYWORDS)


def frame_count(dataset: Dataset) -> int:
    try:
        return max(1, int(getattr(dataset, "NumberOfFrames", 1) or 1))
    except (TypeError, ValueError):
        return 1


def transfer_syntax(dataset: Dataset):
    """Transfer syntax from the file meta, inferred from the encoding when missing."""
    syntax = getattr(getattr(dataset, "file_meta", None), "TransferSyntaxUID", None)
    if syntax:
        return syntax
    implicit, little = getattr(dataset, "original_encoding", (None, None))
    if implicit:
        return ImplicitVRLittleEndian
    if little is False:
        return ExplicitVRBigEndian
    return ExplicitVRLittleEndian


def decode_frame(dataset: Dataset, index: int = 0) -> tuple[np.ndarray, str]:
    """Decode one frame and return it with its photometric interpretation.

    Color frames are (rows, columns, 3) and already converted from YBR to RGB.
    """
    if not has_pixel_data(dataset):
        raise PixelDecodeError("The dataset has no pixel data")
    frames = frame_count(dataset)
    if not 0 <= index < frames:
        raise PixelDecodeError(f"Frame {index + 1} is out of range (1-{frames})")

    try:
        decoder = get_decoder(transfer_syntax(dataset))
        array, meta = decoder.as_array(dataset, index=index if frames > 1 else None)
    except Exception as e:
        raise PixelDecodeError(_first_line(e)) from e

    # Some single frame files still carry a leading frame axis
    if array.shape[0] == 1 and (array.ndim == 4 or (array.ndim == 3 and array.shape[-1] != 3)):
        array = array[0]
    photometric = meta.get("photometric_interpretation") or dataset.get(
        "PhotometricInterpretation", "MONOCHROME2"
    )
    return array, str(photometric).strip().upper()


def _first_line(error: Exception) -> str:
    message = (str(error).strip() or type(error).__name__).splitlines()[0]
    return message if len(message) <= 300 else message[:297] + "..."
