from dataclasses import dataclass

import numpy as np
import pydicom
import pydicom.dataset
from pydicom.multival import MultiValue


def frame_count(dataset) -> int:
    """Number of frames in the dataset's pixel data."""
    try:
        return max(1, int(getattr(dataset, "NumberOfFrames", 1) or 1))
    except (TypeError, ValueError):
        return 1


def normalize_pixel_array(pixel_array):
    """Normalize pixel array to uint8 range."""
    if pixel_array.dtype != np.uint8:
        value_range = pixel_array.max() - pixel_array.min()
        if value_range == 0:
            return np.zeros(pixel_array.shape, dtype=np.uint8)
        return ((pixel_array - pixel_array.min()) / value_range * 255).astype(np.uint8)
    return pixel_array


def get_tag_value_str(elem):
    """Get string representation of DICOM element value."""
    if isinstance(elem.value, bytes):
        return "<binary data>", False
    elif isinstance(elem.value, pydicom.sequence.Sequence):
        sequence_items = get_sequence_items(elem.value)
        return f"<sequence of {len(elem.value)} items>", sequence_items
    return str(elem.value), False


def get_sequence_items(sequence):
    """Get items from a DICOM sequence."""
    items = []
    for i, item in enumerate(sequence):
        sequence_item = {"index": i, "elements": []}
        for elem in item:
            if elem.tag.group != 0x7FE0:
                sequence_item["elements"].append(
                    {
                        "tag": (elem.tag.group, elem.tag.element),
                        "name": elem.name,
                        "vr": getattr(elem, "VR", ""),
                        "value": get_tag_value_str(elem),
                    }
                )
        items.append(sequence_item)
    return items


@dataclass
class DicomImageProperties:
    """Stores and manages DICOM image properties."""

    pixel_array: np.ndarray
    photometric_interpretation: str = "MONOCHROME2"
    window_center: float | None = None
    window_width: float | None = None
    rescale_slope: float = 1.0
    rescale_intercept: float = 0.0
    bits_stored: int = 8
    bits_allocated: int = 8
    invert: bool = False

    @property
    def is_color(self) -> bool:
        """True for color pixel data (rows, columns, 3)."""
        return self.pixel_array.ndim == 3 and self.pixel_array.shape[-1] == 3

    @staticmethod
    def _first_float(value):
        """Coerce a DICOM value to float, taking the first entry of
        multi-valued elements (pydicom MultiValue, list, tuple).
        Returns None when the value is missing or not numeric."""
        if value is None:
            return None
        try:
            if isinstance(value, (MultiValue, list, tuple)):
                if not value:
                    return None
                value = value[0]
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def from_dataset(
        cls, dataset: pydicom.dataset.Dataset, frame: int = 0
    ) -> "DicomImageProperties":
        """Create DicomImageProperties from a pydicom dataset.

        For multi-frame files, the requested frame is selected (pydicom
        caches the decoded array, so per-frame access stays cheap).
        """
        pixel_array = dataset.pixel_array
        frames = frame_count(dataset)
        # Multi-frame data has frames on the first axis: (frames, rows, cols)
        # for grayscale, (frames, rows, cols, 3) for color. A single-frame
        # color image is (rows, cols, 3) and must not be sliced.
        if frames > 1 and pixel_array.ndim >= 3 and pixel_array.shape[0] == frames:
            frame = max(0, min(frame, pixel_array.shape[0] - 1))
            pixel_array = pixel_array[frame]

        rescale_slope = cls._first_float(getattr(dataset, "RescaleSlope", None))
        rescale_intercept = cls._first_float(getattr(dataset, "RescaleIntercept", None))

        return cls(
            pixel_array=pixel_array,
            photometric_interpretation=str(
                getattr(dataset, "PhotometricInterpretation", "") or "MONOCHROME2"
            )
            .strip()
            .upper(),
            window_center=cls._first_float(getattr(dataset, "WindowCenter", None)),
            window_width=cls._first_float(getattr(dataset, "WindowWidth", None)),
            rescale_slope=1.0 if rescale_slope is None else rescale_slope,
            rescale_intercept=0.0 if rescale_intercept is None else rescale_intercept,
            bits_stored=int(getattr(dataset, "BitsStored", 8) or 8),
            bits_allocated=int(getattr(dataset, "BitsAllocated", 8) or 8),
        )

    def get_processed_pixels(self) -> np.ndarray:
        """Return processed pixel array with all DICOM properties applied.

        Grayscale data comes back as a 2D uint8 array with rescale,
        photometric interpretation, and windowing applied. Color data
        comes back as an (rows, columns, 3) uint8 array.
        """
        if self.is_color:
            pixels = np.ascontiguousarray(normalize_pixel_array(self.pixel_array))
            if self.invert:
                pixels = 255 - pixels
            return pixels

        pixels = self.pixel_array.copy()

        # Apply rescale
        if self.rescale_slope != 1.0 or self.rescale_intercept != 0.0:
            pixels = pixels * self.rescale_slope + self.rescale_intercept

        # Handle photometric interpretation
        if self.photometric_interpretation == "MONOCHROME1":
            pixel_max = pixels.max()
            pixels = pixel_max - pixels

        # Apply windowing if specified
        if self.window_center is not None and self.window_width is not None:
            min_value = self.window_center - self.window_width / 2
            max_value = self.window_center + self.window_width / 2
            pixels = np.clip(pixels, min_value, max_value)

        pixels = normalize_pixel_array(pixels)
        if self.invert:
            pixels = 255 - pixels
        return pixels
