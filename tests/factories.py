"""Synthetic DICOM datasets for tests (no real patient data)."""

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

DX_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.1"
COMPREHENSIVE_SR = "1.2.840.10008.5.1.4.1.1.88.33"


def make_image(
    pixels: np.ndarray | None = None,
    photometric: str = "MONOCHROME2",
    bits: int = 16,
    frames: int = 1,
    sop_class: str = DX_FOR_PRESENTATION,
    modality: str = "DX",
    study_uid: str | None = None,
    **attributes,
) -> Dataset:
    """A small image dataset; pixels default to a 64x64 gradient."""
    if pixels is None:
        rows = columns = 64
        maximum = 255 if bits == 8 else 4095
        frame = np.linspace(0, maximum, rows * columns).reshape(rows, columns)
        pixels = np.stack([frame] * frames) if frames > 1 else frame
        pixels = pixels.astype(np.uint8 if bits == 8 else np.uint16)

    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = sop_class
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modality
    ds.PatientName = "Test^Patient"
    ds.PatientID = "TEST001"
    ds.StudyDate = "20240115"

    color = pixels.ndim == 3 + (frames > 1) and pixels.shape[-1] == 3
    ds.Rows, ds.Columns = pixels.shape[-3:-1] if color else pixels.shape[-2:]
    ds.SamplesPerPixel = 3 if color else 1
    if color:
        ds.PlanarConfiguration = 0
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = 8 if bits == 8 else 16
    ds.BitsStored = bits
    ds.HighBit = bits - 1
    ds.PixelRepresentation = 0
    if frames > 1:
        ds.NumberOfFrames = frames
    for keyword, value in attributes.items():
        setattr(ds, keyword, value)
    ds.PixelData = pixels.tobytes()
    return ds


def make_sr(**attributes) -> Dataset:
    """A tiny comprehensive SR with a container, text, and a measurement."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = COMPREHENSIVE_SR
    ds.SOPClassUID = COMPREHENSIVE_SR
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "SR"
    ds.PatientName = "Test^Patient"
    ds.PatientID = "TEST001"
    ds.CompletionFlag = "COMPLETE"
    ds.VerificationFlag = "UNVERIFIED"
    ds.ContentDate = "20240115"
    ds.ContentTime = "120000"
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = [code("18748-4", "LN", "Diagnostic imaging report")]

    text = Dataset()
    text.RelationshipType = "CONTAINS"
    text.ValueType = "TEXT"
    text.ConceptNameCodeSequence = [code("121071", "DCM", "Finding")]
    text.TextValue = "No acute findings."

    num = Dataset()
    num.RelationshipType = "CONTAINS"
    num.ValueType = "NUM"
    num.ConceptNameCodeSequence = [code("410668003", "SCT", "Length")]
    measured = Dataset()
    measured.NumericValue = "12.5"
    measured.MeasurementUnitsCodeSequence = [code("mm", "UCUM", "millimeter")]
    num.MeasuredValueSequence = [measured]

    ds.ContentSequence = Sequence([text, num])
    for keyword, value in attributes.items():
        setattr(ds, keyword, value)
    return ds


def code(value: str, scheme: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def save(ds: Dataset, path) -> str:
    ds.save_as(str(path), enforce_file_format=True)
    return str(path)
