import numpy as np
import pydicom
import pydicom.dataset
from dataclasses import dataclass
from typing import Optional, Union, Tuple, List, Dict, Any

def normalize_pixel_array(pixel_array):
    """Normalize pixel array to uint8 range."""
    if pixel_array.dtype != np.uint8:
        return ((pixel_array - pixel_array.min()) /
                (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
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
        sequence_item = {
            "index": i,
            "elements": []
        }
        for elem in item:
            if elem.tag.group != 0x7FE0:
                sequence_item["elements"].append({
                    "tag": (elem.tag.group, elem.tag.element),
                    "name": elem.name,
                    "vr": getattr(elem, "VR", ""),
                    "value": get_tag_value_str(elem)
                })
        items.append(sequence_item)
    return items

@dataclass
class DicomImageProperties:
    """Stores and manages DICOM image properties."""

    pixel_array: np.ndarray
    photometric_interpretation: str = "MONOCHROME2"
    window_center: Optional[float] = None
    window_width: Optional[float] = None
    rescale_slope: float = 1.0
    rescale_intercept: float = 0.0
    bits_stored: int = 8
    bits_allocated: int = 8

    @classmethod
    def from_dataset(cls, dataset: pydicom.dataset.Dataset) -> "DicomImageProperties":
        """Create DicomImageProperties from a pydicom dataset."""
        props = cls(
            pixel_array=dataset.pixel_array,
            photometric_interpretation=getattr(dataset, "PhotometricInterpretation", "MONOCHROME2").strip().upper(),
            window_center=getattr(dataset, "WindowCenter", None),
            window_width=getattr(dataset, "WindowWidth", None),
            rescale_slope=float(getattr(dataset, "RescaleSlope", 1.0)),
            rescale_intercept=float(getattr(dataset, "RescaleIntercept", 0.0)),
            bits_stored=int(getattr(dataset, "BitsStored", 8)),
            bits_allocated=int(getattr(dataset, "BitsAllocated", 8))
        )

        # Handle multiple window values
        if isinstance(props.window_center, list):
            props.window_center = float(props.window_center[0])
        if isinstance(props.window_width, list):
            props.window_width = float(props.window_width[0])

        return props

    def get_processed_pixels(self) -> np.ndarray:
        """Return processed pixel array with all DICOM properties applied."""
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

        # Normalize to 8-bit range using existing function
        return normalize_pixel_array(pixels)

    def get_pixel_value_range(self) -> Tuple[float, float]:
        """Get the theoretical min/max pixel values based on bits stored."""
        if self.bits_stored <= 0:
            return (0, 255)
        max_value = (2 ** self.bits_stored) - 1
        return (0, max_value)

    def get_metadata(self) -> Dict[str, Any]:
        """Get dictionary of basic image metadata."""
        return {
            "photometric_interpretation": self.photometric_interpretation,
            "window_center": self.window_center,
            "window_width": self.window_width,
            "rescale_slope": self.rescale_slope,
            "rescale_intercept": self.rescale_intercept,
            "bits_stored": self.bits_stored,
            "bits_allocated": self.bits_allocated,
            "shape": self.pixel_array.shape,
            "dtype": str(self.pixel_array.dtype)
        }
