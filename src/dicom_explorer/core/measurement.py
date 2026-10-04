"""Calibration of distance measurements.

ImagerPixelSpacing is measured at the detector plane and is corrected with
EstimatedRadiographicMagnificationFactor when the dataset has it.
"""

import math
from dataclasses import dataclass

from pydicom.dataset import Dataset

from dicom_explorer.core.elements import first_float, float_values


@dataclass(frozen=True)
class Spacing:
    row: float
    column: float
    note: str = ""

    @classmethod
    def of(cls, dataset: Dataset) -> "Spacing | None":
        pixel_spacing = float_values(dataset.get("PixelSpacing"))
        if _valid(pixel_spacing):
            return cls(*pixel_spacing)
        imager = float_values(dataset.get("ImagerPixelSpacing"))
        if not _valid(imager):
            return None
        factor = first_float(dataset.get("EstimatedRadiographicMagnificationFactor"))
        if factor and factor > 0:
            return cls(imager[0] / factor, imager[1] / factor, "magnification corrected")
        return cls(*imager, "at detector plane")

    def distance_text(self, dx: float, dy: float) -> str:
        """Distance of a pixel offset, dx along columns and dy along rows."""
        mm = math.hypot(dx * self.column, dy * self.row)
        note = f", {self.note}" if self.note else ""
        return f"{mm:.1f} mm ({math.hypot(dx, dy):.0f} px{note})"


def _valid(values: list[float]) -> bool:
    return len(values) == 2 and all(v > 0 for v in values)
