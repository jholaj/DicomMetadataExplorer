"""Module requirements of common IODs, a practical subset of PS3.3."""

from collections.abc import Callable
from dataclasses import dataclass

from pydicom.dataset import Dataset

from dicom_explorer.core.pixels import has_pixel_data

MONOCHROME = ("MONOCHROME1", "MONOCHROME2")


@dataclass(frozen=True)
class Condition:
    text: str
    test: Callable[[Dataset], bool]


@dataclass(frozen=True)
class Attr:
    keyword: str
    type: int  # 1 must be present and not empty, 2 must be present
    enum: tuple = ()
    condition: Condition | None = None


FOR_PRESENTATION = Condition(
    "PresentationIntentType is FOR PRESENTATION",
    lambda ds: str(ds.get("PresentationIntentType", "")).upper() == "FOR PRESENTATION",
)
MULTI_SAMPLE = Condition(
    "SamplesPerPixel > 1", lambda ds: str(ds.get("SamplesPerPixel", 1)) not in ("1", "")
)

MODULES = {
    "Patient": (
        Attr("PatientName", 2),
        Attr("PatientID", 2),
        Attr("PatientBirthDate", 2),
        Attr("PatientSex", 2, ("M", "F", "O")),
    ),
    "General Study": (
        Attr("StudyInstanceUID", 1),
        Attr("StudyDate", 2),
        Attr("StudyTime", 2),
        Attr("ReferringPhysicianName", 2),
        Attr("StudyID", 2),
        Attr("AccessionNumber", 2),
    ),
    "General Series": (Attr("Modality", 1), Attr("SeriesInstanceUID", 1), Attr("SeriesNumber", 2)),
    "General Equipment": (Attr("Manufacturer", 2),),
    "General Image": (Attr("InstanceNumber", 2),),
    "Image Pixel": (
        Attr("SamplesPerPixel", 1),
        Attr("PhotometricInterpretation", 1),
        Attr("Rows", 1),
        Attr("Columns", 1),
        Attr("BitsAllocated", 1),
        Attr("BitsStored", 1),
        Attr("HighBit", 1),
        Attr("PixelRepresentation", 1, (0, 1)),
        Attr("PlanarConfiguration", 1, (0, 1), MULTI_SAMPLE),
        Attr("PixelData", 1),
    ),
    "SOP Common": (Attr("SOPClassUID", 1), Attr("SOPInstanceUID", 1)),
    "CR Series": (Attr("BodyPartExamined", 2), Attr("ViewPosition", 2)),
    "CR Image": (Attr("PhotometricInterpretation", 1, MONOCHROME),),
    "DX Series": (Attr("PresentationIntentType", 1, ("FOR PRESENTATION", "FOR PROCESSING")),),
    "DX Image": (
        Attr("ImageType", 1),
        Attr("PhotometricInterpretation", 1, MONOCHROME),
        Attr("PixelIntensityRelationship", 1),
        Attr("PixelIntensityRelationshipSign", 1, (1, -1)),
        Attr("RescaleIntercept", 1),
        Attr("RescaleSlope", 1),
        Attr("RescaleType", 1),
        Attr("PresentationLUTShape", 1, ("IDENTITY", "INVERSE"), FOR_PRESENTATION),
        Attr("LossyImageCompression", 1, ("00", "01")),
        Attr("BurnedInAnnotation", 1, ("YES", "NO")),
    ),
    "DX Detector": (Attr("ImagerPixelSpacing", 1), Attr("DetectorType", 2)),
    "Mammography Image": (
        Attr("ImageLaterality", 1, ("R", "L", "U", "B")),
        Attr("ViewCodeSequence", 1),
    ),
    "Image Plane": (
        Attr("PixelSpacing", 1),
        Attr("ImageOrientationPatient", 1),
        Attr("ImagePositionPatient", 1),
        Attr("SliceThickness", 2),
    ),
    "CT Image": (
        Attr("ImageType", 1),
        Attr("PhotometricInterpretation", 1, MONOCHROME),
        Attr("BitsAllocated", 1, (16,)),
        Attr("RescaleIntercept", 1),
        Attr("RescaleSlope", 1),
        Attr("KVP", 2),
        Attr("AcquisitionNumber", 2),
    ),
    "MR Image": (
        Attr("ImageType", 1),
        Attr("ScanningSequence", 1),
        Attr("SequenceVariant", 1),
        Attr("ScanOptions", 2),
        Attr("MRAcquisitionType", 2),
        Attr("EchoTime", 2),
        Attr("EchoTrainLength", 2),
    ),
    "SC Equipment": (Attr("ConversionType", 1),),
    "SR Document Series": (
        Attr("Modality", 1),
        Attr("SeriesInstanceUID", 1),
        Attr("SeriesNumber", 1),
    ),
    "SR Document General": (
        Attr("InstanceNumber", 1),
        Attr("CompletionFlag", 1, ("PARTIAL", "COMPLETE")),
        Attr("VerificationFlag", 1, ("UNVERIFIED", "VERIFIED")),
        Attr("ContentDate", 1),
        Attr("ContentTime", 1),
    ),
    "SR Document Content": (
        Attr("ValueType", 1, ("CONTAINER",)),
        Attr("ConceptNameCodeSequence", 1),
        Attr("ContinuityOfContent", 1, ("SEPARATE", "CONTINUOUS")),
    ),
    "Key Object Document": (
        Attr("InstanceNumber", 1),
        Attr("ContentDate", 1),
        Attr("ContentTime", 1),
        Attr("ValueType", 1, ("CONTAINER",)),
        Attr("ConceptNameCodeSequence", 1),
    ),
}

IMAGE = (
    "Patient",
    "General Study",
    "General Series",
    "General Equipment",
    "General Image",
    "Image Pixel",
    "SOP Common",
)
DX = (*IMAGE, "DX Series", "DX Image", "DX Detector")
MG = (*DX, "Mammography Image")
SR = (
    "Patient",
    "General Study",
    "SR Document Series",
    "General Equipment",
    "SR Document General",
    "SR Document Content",
    "SOP Common",
)
KO = ("Patient", "General Study", "General Equipment", "Key Object Document", "SOP Common")


@dataclass(frozen=True)
class IOD:
    name: str
    modules: tuple[str, ...]
    modalities: tuple[str, ...] = ()
    intent: str = ""

    @classmethod
    def of(cls, dataset: Dataset) -> "IOD":
        known = IODS.get(str(dataset.get("SOPClassUID", "")))
        if known:
            return known
        if has_pixel_data(dataset):
            return cls("Generic image (limited module checks)", IMAGE)
        return cls("Generic (limited module checks)", ("Patient", "General Study", "SOP Common"))

    @property
    def is_projection(self) -> bool:
        return "DX Image" in self.modules

    def requirements(self) -> list[tuple[str, Attr]]:
        """Attributes of all modules, each listed once."""
        seen = set()
        result = []
        for module in self.modules:
            for attr in MODULES[module]:
                if attr not in seen:
                    seen.add(attr)
                    result.append((module, attr))
        return result


IODS = {
    "1.2.840.10008.5.1.4.1.1.1": IOD("CR Image", (*IMAGE, "CR Series", "CR Image"), ("CR",)),
    "1.2.840.10008.5.1.4.1.1.1.1": IOD(
        "Digital X-Ray Image (For Presentation)", DX, ("DX",), "FOR PRESENTATION"
    ),
    "1.2.840.10008.5.1.4.1.1.1.1.1": IOD(
        "Digital X-Ray Image (For Processing)", DX, ("DX",), "FOR PROCESSING"
    ),
    "1.2.840.10008.5.1.4.1.1.1.2": IOD(
        "Digital Mammography Image (For Presentation)", MG, ("MG",), "FOR PRESENTATION"
    ),
    "1.2.840.10008.5.1.4.1.1.1.2.1": IOD(
        "Digital Mammography Image (For Processing)", MG, ("MG",), "FOR PROCESSING"
    ),
    "1.2.840.10008.5.1.4.1.1.1.3": IOD(
        "Digital Intra-Oral X-Ray Image (For Presentation)", DX, ("IO",), "FOR PRESENTATION"
    ),
    "1.2.840.10008.5.1.4.1.1.1.3.1": IOD(
        "Digital Intra-Oral X-Ray Image (For Processing)", DX, ("IO",), "FOR PROCESSING"
    ),
    "1.2.840.10008.5.1.4.1.1.2": IOD("CT Image", (*IMAGE, "Image Plane", "CT Image"), ("CT",)),
    "1.2.840.10008.5.1.4.1.1.4": IOD("MR Image", (*IMAGE, "Image Plane", "MR Image"), ("MR",)),
    "1.2.840.10008.5.1.4.1.1.7": IOD("Secondary Capture Image", (*IMAGE, "SC Equipment")),
    "1.2.840.10008.5.1.4.1.1.88.11": IOD("Basic Text SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.22": IOD("Enhanced SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.33": IOD("Comprehensive SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.34": IOD("Comprehensive 3D SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.50": IOD("Mammography CAD SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.65": IOD("Chest CAD SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.67": IOD("X-Ray Radiation Dose SR", SR, ("SR",)),
    "1.2.840.10008.5.1.4.1.1.88.59": IOD("Key Object Selection Document", KO, ("KO",)),
}
