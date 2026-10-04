import pytest
from pydicom.dataset import Dataset

from dicom_explorer.core.measurement import Spacing


def dataset(**attributes):
    ds = Dataset()
    for keyword, value in attributes.items():
        setattr(ds, keyword, value)
    return ds


def test_pixel_spacing_is_calibrated():
    spacing = Spacing.of(dataset(PixelSpacing=[0.2, 0.1], ImagerPixelSpacing=[0.3, 0.3]))
    assert spacing == Spacing(0.2, 0.1)
    # dx runs along columns, dy along rows
    assert spacing.distance_text(30, 40).startswith("8.5 mm")


def test_imager_spacing_is_labelled_as_detector_plane():
    spacing = Spacing.of(dataset(ImagerPixelSpacing=[0.15, 0.15]))
    assert spacing.distance_text(100, 0) == "15.0 mm (100 px, at detector plane)"


def test_magnification_factor_corrects_imager_spacing():
    spacing = Spacing.of(
        dataset(ImagerPixelSpacing=[0.15, 0.15], EstimatedRadiographicMagnificationFactor=1.5)
    )
    assert spacing.row == pytest.approx(0.1)
    assert spacing.note == "magnification corrected"


def test_without_valid_spacing():
    assert Spacing.of(dataset()) is None
    assert Spacing.of(dataset(PixelSpacing=[0, 0.1])) is None
