import numpy as np
import pytest
from pydicom.dataset import Dataset

from dicom_explorer.core.pixels import PixelDecodeError, decode_frame
from dicom_explorer.core.rendering import FrameImage, VoiLut, Window
from factories import make_image


def frame_image(ds):
    pixels, photometric = decode_frame(ds)
    return FrameImage(ds, pixels, photometric)


def row(values, **attrs):
    pixels = np.array([values], dtype=np.uint16)
    return make_image(pixels, **attrs)


def test_monochrome2_window_maps_window_bounds_to_black_and_white():
    ds = row([0, 750, 1000, 1250, 4095], WindowCenter=1000, WindowWidth=500)
    out = frame_image(ds).render()[0].tolist()
    assert out[0] == 0 and out[1] == 0
    assert 120 <= out[2] <= 135
    assert out[3] == 255 and out[4] == 255


def test_monochrome1_is_inverted_after_windowing():
    ds = row([0, 500, 1000, 1500, 4095], photometric="MONOCHROME1")
    ds.WindowCenter, ds.WindowWidth = 1000, 500
    out = frame_image(ds).render()[0].tolist()
    # Low values are bright in MONOCHROME1, the window still selects 750..1250
    assert out[0] == 255 and out[1] == 255
    assert 120 <= out[2] <= 135
    assert out[3] == 0 and out[4] == 0


def test_user_invert_toggles_on_top_of_monochrome1():
    ds = row([0, 4095], photometric="MONOCHROME1", WindowCenter=2048, WindowWidth=4096)
    image = frame_image(ds)
    assert image.render()[0].tolist() == [255, 0]
    assert image.render(invert=True)[0].tolist() == [0, 255]


def test_window_wider_than_data_keeps_mid_gray():
    ds = row([1000, 1500, 2000], WindowCenter=2048, WindowWidth=4096)
    out = frame_image(ds).render()[0].tolist()
    assert 55 <= out[0] <= 70 and 85 <= out[1] <= 100 and 120 <= out[2] <= 130


def test_rescale_is_applied_before_window():
    # stored 1024 with intercept -1024 -> 0 HU, window centered at 0
    ds = row([0, 1024, 2048], RescaleSlope=1, RescaleIntercept=-1024, Modality="CT")
    ds.WindowCenter, ds.WindowWidth = 0, 400
    image = frame_image(ds)
    out = image.render()[0].tolist()
    assert out[0] == 0 and 120 <= out[1] <= 135 and out[2] == 255
    assert "HU" in image.describe_pixel(1, 0)


def test_sigmoid_and_linear_exact_functions():
    values = np.array([0.0, 100.0, 200.0], dtype=np.float32)
    exact = Window(100, 200, "LINEAR_EXACT").apply(values)
    assert exact.tolist() == pytest.approx([0.0, 0.5, 1.0])
    sigmoid = Window(100, 200, "SIGMOID").apply(values)
    assert sigmoid[1] == pytest.approx(0.5)
    assert sigmoid[0] < 0.2 and sigmoid[2] > 0.8


def test_voi_lut_sequence_is_preferred_over_window():
    ds = row([0, 10, 20, 30])
    item = Dataset()
    item.LUTDescriptor = [4, 10, 8]
    item.LUTData = [0, 50, 200, 255]
    ds.VOILUTSequence = [item]
    ds.WindowCenter, ds.WindowWidth = 15, 10
    image = frame_image(ds)
    assert isinstance(image.default_voi, VoiLut)
    out = image.render()[0].tolist()
    assert out[0] == 0  # below first mapped -> first entry
    assert out[1] == 0  # first entry
    assert out[3] == 255  # above range -> last entry


def test_first_dataset_window_is_default():
    ds = row([0, 100], WindowCenter=[40, 400], WindowWidth=[80, 2000])
    assert frame_image(ds).default_voi == Window(40, 80)


def test_missing_window_uses_full_range():
    ds = row([100, 200, 300])
    out = frame_image(ds).render()[0].tolist()
    assert out[0] == 0 and out[2] == 255


def test_rgb_rendering_and_invert():
    pixels = np.zeros((2, 2, 3), dtype=np.uint8)
    pixels[0, 0] = (255, 0, 0)
    ds = make_image(pixels, photometric="RGB", bits=8)
    image = frame_image(ds)
    assert image.is_color
    assert image.render()[0, 0].tolist() == [255, 0, 0]
    assert image.render(invert=True)[0, 0].tolist() == [0, 255, 255]
    assert "RGB: 255, 0, 0" in image.describe_pixel(0, 0)


def test_multiframe_decodes_requested_frame_only():
    ds = make_image(frames=3)
    first, _ = decode_frame(ds, 0)
    last, _ = decode_frame(ds, 2)
    assert first.shape == (64, 64)
    assert np.array_equal(first, last)  # same gradient in every frame
    with pytest.raises(PixelDecodeError):
        decode_frame(ds, 3)


def test_truncated_pixel_data_raises_decode_error():
    ds = make_image()
    ds.PixelData = ds.PixelData[:100]
    with pytest.raises(PixelDecodeError):
        decode_frame(ds)


def test_preview_step_decimates():
    ds = make_image()
    assert frame_image(ds).render(step=4).shape == (16, 16)


def test_window_drag_changes_width_and_level():
    start = Window(1000, 500)
    wider = start.dragged(dx=30, dy=0, value_span=4096)
    brighter = start.dragged(dx=0, dy=30, value_span=4096)
    assert wider.width > 500 and wider.center == 1000
    assert brighter.center < 1000 and brighter.width == 500
    assert start.dragged(dx=-10_000, dy=0, value_span=4096).width >= 1
