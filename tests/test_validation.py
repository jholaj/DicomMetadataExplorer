import datetime

from dicom_explorer.core.elements import ElementPath
from dicom_explorer.core.validation import (
    ERROR,
    WARNING,
    validate_dataset,
    validate_workspace,
    vm_allows,
)
from factories import COMPREHENSIVE_SR, make_image, make_sr

CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"


def complete_dx(**overrides):
    """A DX For Presentation dataset satisfying the checked module subset."""
    attributes = {
        "PatientBirthDate": "19800101",
        "PatientSex": "F",
        "StudyTime": "101500",
        "ReferringPhysicianName": "",
        "StudyID": "1",
        "AccessionNumber": "A1",
        "SeriesNumber": 1,
        "Manufacturer": "ACME",
        "InstanceNumber": 1,
        "PresentationIntentType": "FOR PRESENTATION",
        "ImageType": ["ORIGINAL", "PRIMARY"],
        "PixelIntensityRelationship": "LIN",
        "PixelIntensityRelationshipSign": 1,
        "RescaleIntercept": 0,
        "RescaleSlope": 1,
        "RescaleType": "US",
        "PresentationLUTShape": "IDENTITY",
        "LossyImageCompression": "00",
        "BurnedInAnnotation": "NO",
        "ImagerPixelSpacing": [0.1, 0.1],
        "DetectorType": "DIRECT",
        "WindowCenter": 2048,
        "WindowWidth": 4096,
        "BitsStored": 12,
    }
    attributes.update(overrides)
    bits = attributes.pop("BitsStored")
    return make_image(bits=bits, **attributes)


def messages(report, severity=None):
    return [i.message for i in report.issues if severity is None or i.severity == severity]


def test_complete_dx_passes():
    report = validate_dataset(complete_dx())
    assert report.iod == "Digital X-Ray Image (For Presentation)"
    assert report.errors == 0, messages(report)
    assert report.warnings == 0, messages(report)


def test_missing_type1_and_type2_attributes():
    ds = complete_dx()
    del ds.ImagerPixelSpacing
    del ds.Manufacturer
    report = validate_dataset(ds)
    assert any("Missing Type 1 ImagerPixelSpacing" in m for m in messages(report, ERROR))
    assert any("Missing Type 2 Manufacturer" in m for m in messages(report, WARNING))


def test_presentation_lut_shape_must_match_monochrome1():
    ds = complete_dx(PhotometricInterpretation="MONOCHROME1")
    report = validate_dataset(ds)
    assert any("must be INVERSE for MONOCHROME1" in m for m in messages(report, ERROR))


def test_intent_must_match_sop_class():
    report = validate_dataset(complete_dx(PresentationIntentType="FOR PROCESSING"))
    assert any("PresentationIntentType FOR PROCESSING" in m for m in messages(report))


def test_modality_must_match_iod():
    report = validate_dataset(complete_dx(Modality="CR"))
    assert any("Modality 'CR' does not match" in m for m in messages(report, ERROR))


def test_vr_and_vm_errors_point_to_elements():
    ds = complete_dx()
    ds.StudyDate = "2024-01-01"
    ds.PixelSpacing = [0.1, 0.1, 0.1]
    report = validate_dataset(ds)
    vr_issue = next(i for i in report.issues if "Invalid value for VR DA" in i.message)
    assert vr_issue.path == ElementPath.top("StudyDate")
    assert any("dictionary VM is 2" in m for m in messages(report))


def test_file_meta_mismatch_and_truncated_pixels():
    ds = complete_dx()
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    ds.PixelData = ds.PixelData[:100]
    report = validate_dataset(ds)
    errors = messages(report, ERROR)
    assert any("MediaStorageSOPInstanceUID" in m for m in errors)
    assert any("PixelData has 100 bytes" in m for m in errors)
    assert any("cannot be decoded" in m for m in errors)


def test_dates_and_age_consistency():
    future = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y%m%d")
    ds = complete_dx(PatientBirthDate="20250101", StudyDate="20240101", PatientAge="030Y")
    ds.ContentDate = future
    report = validate_dataset(ds)
    found = messages(report)
    assert any("is after StudyDate" in m for m in found)
    assert any("PatientAge 030Y" in m for m in found)


def test_value_range_exceeding_bits_stored():
    ds = complete_dx(BitsStored=10)  # gradient goes up to 4095
    report = validate_dataset(ds)
    assert any("bits above BitsStored" in m for m in messages(report, WARNING))


def test_private_element_without_creator():
    ds = complete_dx()
    ds.add_new(0x00091001, "LO", "orphan")
    report = validate_dataset(ds)
    assert any("has no Private Creator" in m for m in messages(report))


def test_sr_document_modules():
    ds = make_sr()
    report = validate_dataset(ds)
    assert report.iod == "Comprehensive SR"
    assert ds.SOPClassUID == COMPREHENSIVE_SR
    assert any("ContinuityOfContent" in m for m in messages(report, ERROR))


def test_ct_requires_image_plane():
    ds = make_image(sop_class=CT_IMAGE, modality="CT")
    report = validate_dataset(ds)
    assert report.iod == "CT Image"
    assert any("ImagePositionPatient" in m for m in messages(report, ERROR))


def test_workspace_duplicates_and_patient_mismatch():
    first = make_image()
    second = make_image(study_uid=first.StudyInstanceUID, PatientID="OTHER")
    second.SOPInstanceUID = first.SOPInstanceUID
    issues = validate_workspace({"a.dcm": first, "b.dcm": second})
    found = [i.message for i in issues["a.dcm"]]
    assert any("Duplicate SOPInstanceUID" in m for m in found)
    assert any("PatientID differs within the study" in m for m in found)


def test_vm_rules():
    assert vm_allows("1", 1) and not vm_allows("1", 2)
    assert vm_allows("1-n", 5)
    assert vm_allows("2-2n", 4) and not vm_allows("2-2n", 3)
    assert vm_allows("1-3", 3) and not vm_allows("1-3", 4)
