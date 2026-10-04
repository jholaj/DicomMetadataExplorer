import pytest
from pydicom.tag import Tag

from dicom_explorer.core.elements import (
    DatasetSnapshot,
    ElementPath,
    common_elements,
    format_date,
    is_editable,
    parse_tag,
    parse_value,
    value_text,
    walk,
)
from factories import code, make_image


def nested_dataset():
    ds = make_image()
    ds.ImageType = ["ORIGINAL", "PRIMARY"]
    ds.AnatomicRegionSequence = [code("T-D3000", "SRT", "Chest")]
    ds.ViewCodeSequence = [code("R-10206", "SRT", "PA")]
    ds.add_new(0x00090010, "LO", "VENDOR")
    ds.add_new(0x00091001, "OB", b"\x01\x02\x03\x04")
    return ds


def test_multi_value_text_uses_backslash():
    ds = nested_dataset()
    assert value_text(ds["ImageType"]) == "ORIGINAL\\PRIMARY"


def test_binary_and_sequence_values_are_not_editable():
    ds = nested_dataset()
    assert value_text(ds[0x00091001]) == "<binary data, 4 bytes>"
    assert not is_editable(ds[0x00091001])
    assert not is_editable(ds["ViewCodeSequence"])
    assert not is_editable(ds["PixelData"])
    assert is_editable(ds["ImageType"])


def test_parse_value_splits_multi_values_and_validates():
    assert parse_value("ORIGINAL\\PRIMARY", "CS") == ["ORIGINAL", "PRIMARY"]
    assert parse_value("0.1\\0.1", "DS") == ["0.1", "0.1"]
    assert parse_value("12", "US") == 12
    assert parse_value("", "US") is None
    assert parse_value("a\\b", "LT") == "a\\b"  # backslash is text for LT
    assert parse_value("(0010,0010)", "AT") == Tag(0x00100010)
    with pytest.raises(ValueError):
        parse_value("2024-01-01", "DA")
    with pytest.raises(ValueError):
        parse_value("70000", "US")
    with pytest.raises(ValueError):
        parse_value("abc", "IS")
    with pytest.raises(ValueError):
        parse_value("x", "OB")


def test_walk_yields_nested_paths():
    ds = nested_dataset()
    paths = {entry.path.keywords() for entry in walk(ds)}
    assert "AnatomicRegionSequence[0].CodeValue" in paths
    assert "ViewCodeSequence[0].CodeValue" in paths
    assert any(entry.path.meta for entry in walk(ds, include_meta=True))


def test_element_path_addresses_the_right_nested_element():
    ds = nested_dataset()
    path = ElementPath.top("ViewCodeSequence").child(0).child(Tag("CodeValue"))
    assert path.dataset(ds) is ds.ViewCodeSequence[0]
    assert path.element(ds).value == "R-10206"
    assert path.keywords() == "ViewCodeSequence[0].CodeValue"
    assert path.tags() == "(0054,0220)[0] > (0008,0100)"
    assert path.parent.dataset(ds) is ds.ViewCodeSequence[0]
    missing = ElementPath.top("ViewCodeSequence").child(5).child(Tag("CodeValue"))
    assert missing.element(ds) is None


def test_parse_tag_and_format_date():
    assert parse_tag("PatientName") == Tag(0x00100010)
    assert parse_tag("(0010, 0010)") == Tag(0x00100010)
    assert parse_tag("00100010") == Tag(0x00100010)
    with pytest.raises(ValueError):
        parse_tag("nope")
    assert format_date("20240115") == "15.01.2024"
    assert format_date("") == ""


def test_snapshot_restore_round_trip():
    ds = nested_dataset()
    snapshot = DatasetSnapshot.of(ds)
    ds.PatientName = "Changed"
    del ds.ViewCodeSequence
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    snapshot.restore(ds)
    assert ds.PatientName == "Test^Patient"
    assert ds.ViewCodeSequence[0].CodeValue == "R-10206"
    assert ds.file_meta.MediaStorageSOPInstanceUID == ds.SOPInstanceUID


def test_common_elements_keep_only_equal_editable_values():
    first, second = nested_dataset(), nested_dataset()
    second.SeriesInstanceUID = first.SeriesInstanceUID
    second.StudyInstanceUID = first.StudyInstanceUID
    second.PatientID = "OTHER"
    keywords = {element.keyword for element in common_elements([first, second])}
    assert {"PatientName", "ImageType", "SeriesInstanceUID", "StudyInstanceUID"} <= keywords
    assert "PatientID" not in keywords  # differs
    assert "SOPInstanceUID" not in keywords  # unique per file
    assert "ViewCodeSequence" not in keywords  # sequences are not editable
    assert "PixelData" not in keywords
