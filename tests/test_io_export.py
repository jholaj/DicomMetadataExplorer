import csv
import json
from pathlib import Path
from unittest import mock

import pydicom
import pytest

from dicom_explorer.core import io
from dicom_explorer.core.export import ExportFormat
from factories import code, make_image, save


def test_save_is_atomic_on_failure(tmp_path):
    target = Path(save(make_image(), tmp_path / "a.dcm"))
    original = target.read_bytes()
    ds = pydicom.dcmread(target)
    with (
        mock.patch.object(type(ds), "save_as", side_effect=OSError("disk full")),
        pytest.raises(OSError),
    ):
        io.save_dataset(ds, target)
    assert target.read_bytes() == original
    assert [p.name for p in tmp_path.iterdir()] == ["a.dcm"]


def test_save_round_trip(tmp_path):
    ds = make_image()
    ds.PatientName = "Saved^Name"
    io.save_dataset(ds, tmp_path / "out" / "b.dcm")
    assert pydicom.dcmread(tmp_path / "out" / "b.dcm").PatientName == "Saved^Name"


def test_plan_copy_targets_avoids_collisions(tmp_path):
    flat = io.plan_copy_targets([Path("/x/a/one.dcm"), Path("/x/b/two.dcm")], tmp_path)
    assert flat[Path("/x/a/one.dcm")] == tmp_path / "one.dcm"

    clashing = [Path("/x/s1/IM0001"), Path("/x/s2/IM0001")]
    targets = io.plan_copy_targets(clashing, tmp_path)
    assert len(set(targets.values())) == 2
    assert targets[clashing[0]] == tmp_path / "s1" / "IM0001"


def test_expand_paths_skips_hidden_and_dicomdir(tmp_path):
    (tmp_path / "series").mkdir()
    save(make_image(), tmp_path / "series" / "IM1")
    (tmp_path / "DICOMDIR").write_bytes(b"x")
    (tmp_path / ".hidden").write_bytes(b"x")
    request = io.OpenRequest.expand([tmp_path])
    assert [f.name for f in request.files] == ["IM1"]
    assert request.explicit == set()
    assert request.sources_of(request.files) == [tmp_path.resolve()]


def test_exports(tmp_path):
    ds = make_image()
    ds.ImageType = ["ORIGINAL", "PRIMARY"]
    ds.ViewCodeSequence = [code("R-10206", "SRT", "PA")]

    ExportFormat.JSON.write(ds, tmp_path / "m.json")
    data = json.loads((tmp_path / "m.json").read_text())
    image_type = next(e for e in data if e["keyword"] == "ImageType")
    assert image_type["value"] == "ORIGINAL\\PRIMARY"
    assert not any(e["keyword"] == "PixelData" for e in data)

    ExportFormat.CSV.write(ds, tmp_path / "m.csv")
    rows = list(csv.DictReader((tmp_path / "m.csv").open()))
    assert any(r["Path"] == "ViewCodeSequence[0].CodeValue" for r in rows)

    ExportFormat.DICOM_JSON.write(ds, tmp_path / "m.dcm.json")
    dicom_json = json.loads((tmp_path / "m.dcm.json").read_text())
    assert dicom_json["00080008"]["Value"] == ["ORIGINAL", "PRIMARY"]
    assert "7FE00010" not in dicom_json


def test_export_format_from_path():
    assert ExportFormat.for_path(Path("a.csv"), ExportFormat.JSON) is ExportFormat.CSV
    assert ExportFormat.for_path(Path("a.dcm.json"), ExportFormat.JSON) is ExportFormat.DICOM_JSON
    assert ExportFormat.for_path(Path("a.json"), ExportFormat.DICOM_JSON) is ExportFormat.DICOM_JSON
    assert ExportFormat.for_path(Path("a"), ExportFormat.CSV) is ExportFormat.CSV
