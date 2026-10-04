from unittest import mock

import pytest
from pydicom.dataset import Dataset

from dicom_explorer.core import anonymizer
from dicom_explorer.core.anonymizer import AnonymizationOptions, anonymize_dataset
from factories import make_image, make_sr


def identifiable():
    ds = make_image(
        PatientName="Doe^John",
        PatientID="PID-12345",
        PatientBirthDate="19700101",
        PatientSex="M",
        PatientAge="054Y",
        StudyDate="20240101",
        InstitutionName="General Hospital",
        AccessionNumber="ACC123",
        ImageComments="John Doe, follow-up",
        ReferringPhysicianName="Smith^Anna",
    )
    other = Dataset()
    other.PatientID = "OTHER-PID-999"
    ds.OtherPatientIDsSequence = [other]
    ds.add_new(0x00090010, "LO", "VENDOR")
    ds.add_new(0x00091001, "LO", "secret")
    return ds


def all_text(ds):
    return " ".join(str(e.value) for e in ds.iterall() if isinstance(e.value, str))


def test_profile_removes_identifiers_and_marks_dataset():
    ds = identifiable()
    original_study = ds.StudyInstanceUID
    result = anonymize_dataset(ds, AnonymizationOptions())

    text = all_text(ds)
    secrets = ("Doe", "PID-12345", "General Hospital", "ACC123", "Smith", "secret", "OTHER-PID")
    for secret in secrets:
        assert secret not in text
    assert ds.PatientBirthDate != "19700101"
    assert "ImageComments" not in ds
    assert 0x00091001 not in ds
    assert ds.StudyInstanceUID != original_study
    assert ds.file_meta.MediaStorageSOPInstanceUID == ds.SOPInstanceUID
    assert ds.PatientIdentityRemoved == "YES"
    assert ds.DeidentificationMethodCodeSequence[0].CodeValue == "113100"
    assert ds.LongitudinalTemporalInformationModified == "REMOVED"
    assert result.changed > 0 and result.removed > 0


def test_uids_are_replaced_consistently_across_files():
    first = identifiable()
    second = make_image(study_uid=first.StudyInstanceUID)
    anonymize_dataset(first, AnonymizationOptions())
    anonymize_dataset(second, AnonymizationOptions())
    assert first.StudyInstanceUID == second.StudyInstanceUID


def test_retain_options():
    ds = identifiable()
    study_uid = ds.StudyInstanceUID
    options = AnonymizationOptions(
        retain_dates=True, retain_uids=True, retain_patient_characteristics=True
    )
    anonymize_dataset(ds, options)
    assert ds.StudyDate == "20240101"
    assert ds.StudyInstanceUID == study_uid
    assert ds.PatientSex == "M" and ds.PatientAge == "054Y"
    assert "Doe" not in all_text(ds)
    codes = [item.CodeValue for item in ds.DeidentificationMethodCodeSequence]
    assert codes == ["113100", "113106", "113108", "113110"]
    assert ds.LongitudinalTemporalInformationModified == "UNMODIFIED"
    assert all(len(v) <= 64 for v in ds.DeidentificationMethod)


def test_burned_in_annotation_warnings():
    ds = identifiable()
    ds.BurnedInAnnotation = "YES"
    assert any("not removed" in w for w in anonymize_dataset(ds, AnonymizationOptions()).warnings)

    unknown = identifiable()
    assert any(
        "may contain" in w for w in anonymize_dataset(unknown, AnonymizationOptions()).warnings
    )

    clean = identifiable()
    clean.BurnedInAnnotation = "NO"
    assert anonymize_dataset(clean, AnonymizationOptions()).warnings == []


def test_structured_report_text_is_replaced():
    ds = make_sr()
    anonymize_dataset(ds, AnonymizationOptions())
    assert "No acute findings" not in all_text(ds)


def test_failure_restores_the_dataset():
    ds = identifiable()

    def half_done_then_fail(dataset, *args):
        dataset.PatientName = "ANONYMIZED"
        del dataset[0x00091001]
        raise RuntimeError("boom")

    with (
        mock.patch.object(anonymizer, "apply_profile", side_effect=half_done_then_fail),
        pytest.raises(RuntimeError),
    ):
        anonymize_dataset(ds, AnonymizationOptions())
    assert ds.PatientName == "Doe^John"
    assert 0x00091001 in ds
