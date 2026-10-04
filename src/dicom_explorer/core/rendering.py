"""DICOM display pipeline for grayscale and color frames.

Grayscale goes through the Modality LUT, the VOI (window or VOI LUT) and the
presentation inversion. Color frames are scaled to 8 bits.
"""

import math
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from pydicom.dataset import Dataset
from pydicom.pixels.processing import apply_color_lut, apply_modality_lut, apply_voi

from dicom_explorer.core.elements import first_float, float_values

VOI_FUNCTIONS = ("LINEAR", "LINEAR_EXACT", "SIGMOID")


@dataclass(frozen=True)
class Window:
    """VOI window as defined in PS3.3 C.11.2.1.2."""

    center: float
    width: float
    function: str = "LINEAR"

    def apply(self, values: np.ndarray) -> np.ndarray:
        """Map values to 0..1."""
        c, w = float(self.center), float(self.width)
        if self.function == "SIGMOID":
            return (1 / (1 + np.exp(-4 * (values - c) / max(w, 1e-6)))).astype(np.float32)
        if self.function == "LINEAR_EXACT":
            return np.clip((values - c) / max(w, 1e-6) + 0.5, 0, 1).astype(np.float32)
        if w <= 1:
            return (values > c - 0.5).astype(np.float32)
        return np.clip((values - (c - 0.5)) / (w - 1) + 0.5, 0, 1).astype(np.float32)

    def dragged(self, dx: float, dy: float, value_span: float) -> "Window":
        """Window after a mouse drag, horizontal changes the width, vertical the level."""
        step = max(abs(self.width), value_span / 64, 1.0) / 300
        return Window(self.center - dy * step, max(self.width + dx * step, 1.0), self.function)


@dataclass(frozen=True, eq=False)
class VoiLut:
    """VOI LUT Sequence item normalized to 0..1."""

    first_mapped: int
    table: np.ndarray = field(repr=False)

    @classmethod
    def of(cls, dataset: Dataset, index: int = 0) -> "VoiLut":
        item = dataset.VOILUTSequence[index]
        entries, first_mapped, _bits = (int(v) for v in item.LUTDescriptor)
        entries = entries or 65536
        # The first mapped value is signed for signed pixel data
        if first_mapped >= 2**15 and dataset.get("PixelRepresentation", 0):
            first_mapped -= 2**16
        table = apply_voi(np.arange(first_mapped, first_mapped + entries), dataset, index)
        table = table.astype(np.float32)
        span = float(table.max() - table.min())
        table = (table - table.min()) / span if span else np.zeros_like(table)
        return cls(first_mapped, table)

    def apply(self, values: np.ndarray) -> np.ndarray:
        indices = np.clip(np.floor(values) - self.first_mapped, 0, len(self.table) - 1)
        return self.table[indices.astype(np.intp)]

    def as_window(self) -> Window:
        """Linear window over the rising part of the LUT."""
        rising = np.nonzero((self.table > 0) & (self.table < 1))[0]
        start, end = (rising[0], rising[-1]) if len(rising) else (0, len(self.table) - 1)
        width = max(int(end) - int(start) + 1, 1)
        return Window(self.first_mapped + int(start) + width / 2, width)


class FrameImage:
    """Decoded frame with the dataset attributes needed to render it."""

    def __init__(self, dataset: Dataset, pixels: np.ndarray, photometric: str):
        self.dataset = dataset
        self.raw = pixels
        self.photometric = photometric
        self.is_color = (pixels.ndim == 3 and pixels.shape[-1] == 3) or (
            photometric == "PALETTE COLOR"
        )
        self.values = None if self.is_color else modality_values(dataset, pixels)

    @property
    def shape(self) -> tuple[int, int]:
        return self.raw.shape[0], self.raw.shape[1]

    @property
    def inverted_by_dataset(self) -> bool:
        shape = str(self.dataset.get("PresentationLUTShape", "")).strip().upper()
        return not self.is_color and (self.photometric == "MONOCHROME1" or shape == "INVERSE")

    @cached_property
    def value_range(self) -> tuple[float, float]:
        data = self.raw if self.values is None else self.values
        return float(np.min(data)), float(np.max(data))

    @cached_property
    def default_voi(self) -> Window | VoiLut | None:
        """VOI LUT, then the first dataset window, then the full value range."""
        if self.is_color:
            return None
        if self.dataset.get("VOILUTSequence"):
            try:
                return VoiLut.of(self.dataset)
            except Exception:
                pass
        centers = float_values(self.dataset.get("WindowCenter"))
        widths = float_values(self.dataset.get("WindowWidth"))
        if centers and widths and widths[0] > 0:
            function = str(self.dataset.get("VOILUTFunction", "LINEAR")).strip().upper()
            return Window(
                centers[0], widths[0], function if function in VOI_FUNCTIONS else "LINEAR"
            )
        low, high = self.value_range
        return Window((low + high) / 2, max(high - low, 1.0))

    def render(self, voi=None, invert: bool = False, step: int = 1) -> np.ndarray:
        """Render to uint8, a step above 1 renders a decimated preview."""
        if self.is_color:
            rgb = self._rgb[::step, ::step]
            return np.ascontiguousarray(255 - rgb if invert else rgb)
        normalized = (voi or self.default_voi).apply(self.values[::step, ::step])
        if self.inverted_by_dataset != invert:
            normalized = 1 - normalized
        return np.rint(normalized * 255).astype(np.uint8)

    def describe_pixel(self, x: int, y: int) -> str | None:
        """Pixel probe text, None outside the image."""
        rows, columns = self.shape
        if not (0 <= y < rows and 0 <= x < columns):
            return None
        if self.is_color:
            r, g, b = (int(v) for v in self._rgb[y, x][:3])
            return f"({x}, {y})  RGB: {r}, {g}, {b}"
        stored, value = self.raw[y, x], float(self.values[y, x])
        text = f"({x}, {y})  value: {value:g}{modality_unit(self.dataset)}"
        return text if float(stored) == value else f"{text}  (stored {stored})"

    @cached_property
    def _rgb(self) -> np.ndarray:
        pixels = self.raw
        if self.photometric == "PALETTE COLOR" and pixels.ndim == 2:
            pixels = apply_color_lut(pixels, self.dataset)
        if pixels.dtype == np.uint8:
            return pixels
        bits = int(self.dataset.get("BitsStored", 0) or 0)
        palette = self.photometric == "PALETTE COLOR"
        maximum = float(pixels.max() or 1) if palette or not bits else float(2**bits - 1)
        return np.clip(pixels.astype(np.float32) / maximum * 255 + 0.5, 0, 255).astype(np.uint8)


def modality_values(dataset: Dataset, pixels: np.ndarray) -> np.ndarray:
    """Apply the Modality LUT (LUT sequence or rescale) as float32."""
    if "ModalityLUTSequence" in dataset:
        try:
            return apply_modality_lut(pixels, dataset).astype(np.float32)
        except Exception:
            pass
    slope = first_float(dataset.get("RescaleSlope"))
    intercept = first_float(dataset.get("RescaleIntercept"))
    values = pixels.astype(np.float32)
    if slope is not None and math.isfinite(slope) and slope not in (0, 1):
        values *= np.float32(slope)
    if intercept and math.isfinite(intercept):
        values += np.float32(intercept)
    return values


def modality_unit(dataset: Dataset) -> str:
    rescale_type = str(dataset.get("RescaleType", "")).strip().upper()
    is_ct = str(dataset.get("Modality", "")).upper() == "CT"
    return " HU" if rescale_type == "HU" or (not rescale_type and is_ct) else ""
