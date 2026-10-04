"""De-identification by the DICOM PS3.15 Basic Application Level Confidentiality Profile.

Attribute actions come from the dicom-anonymizer tables generated from the standard.
"""

import contextlib
import io
import logging
from dataclasses import dataclass, field

from dicomanonymizer.simpledicomanonymizer import anonymize_dataset as apply_profile
from dicomanonymizer.simpledicomanonymizer import initialize_actions, keep
from pydicom.datadict import dictionary_VR
from pydicom.dataset import Dataset

from dicom_explorer.core.elements import DatasetSnapshot, value_text, walk

log = logging.getLogger(__name__)

PROFILE_DATABASE = "dicomfields_2026c"
PROFILE_NAME = "DICOM PS3.15 Basic Application Level Confidentiality Profile"
# PatientSex, PatientAge, PatientSize, PatientWeight
PATIENT_CHARACTERISTICS = frozenset({0x00100040, 0x00101010, 0x00101020, 0x00101030})
# Modalities where identifying text is often burned into the pixels
BURNED_IN_RISK_MODALITIES = frozenset(
    {"CR", "DX", "MG", "IO", "PX", "US", "XA", "RF", "OT", "SC", "ES", "XC", "GM", "SM"}
)


@dataclass(frozen=True)
class AnonymizationOptions:
    retain_dates: bool = False
    retain_uids: bool = False
    retain_patient_characteristics: bool = False

    @property
    def codes(self) -> list[tuple[str, str]]:
        """CID 7050 de-identification method codes."""
        codes = [("113100", "Basic Application Confidentiality Profile")]
        if self.retain_dates:
            codes.append(("113106", "Retain Longitudinal Temporal Information Full Dates Option"))
        if self.retain_patient_characteristics:
            codes.append(("113108", "Retain Patient Characteristics Option"))
        if self.retain_uids:
            codes.append(("113110", "Retain UIDs Option"))
        return codes

    def rules(self) -> dict:
        """Profile actions per tag with the retained attributes kept."""
        rules = initialize_actions(PROFILE_DATABASE)
        for tag in [t for t in rules if len(t) == 2]:
            if self._retains((tag[0] << 16) | tag[1]):
                rules[tag] = keep
        return rules

    def _retains(self, tag: int) -> bool:
        if self.retain_patient_characteristics and tag in PATIENT_CHARACTERISTICS:
            return True
        try:
            vr = dictionary_VR(tag)
        except KeyError:
            return False
        return (self.retain_dates and vr in ("DA", "DT", "TM")) or (self.retain_uids and vr == "UI")


@dataclass
class AnonymizationResult:
    changed: int = 0
    removed: int = 0
    warnings: list[str] = field(default_factory=list)


def anonymize_dataset(dataset: Dataset, options: AnonymizationOptions) -> AnonymizationResult:
    """De-identify in place, the dataset is restored when anything fails.

    UIDs map to the same new UIDs for the whole session, so studies stay grouped.
    """
    before = _texts(dataset)
    snapshot = DatasetSnapshot.of(dataset)
    rules = options.rules()
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apply_profile(dataset, None, True, lambda: dict(rules))
        if output.getvalue().strip():
            log.debug("dicom-anonymizer: %s", output.getvalue().strip())
        _mark_deidentified(dataset, options)
    except Exception:
        snapshot.restore(dataset)
        raise

    after = _texts(dataset)
    return AnonymizationResult(
        changed=sum(1 for path, text in before.items() if after.get(path, text) != text),
        removed=sum(1 for path in before if path not in after),
        warnings=_burned_in_warnings(dataset),
    )


def _texts(dataset: Dataset) -> dict:
    return {entry.path: value_text(entry.element) for entry in walk(dataset, include_meta=True)}


def _mark_deidentified(dataset: Dataset, options: AnonymizationOptions) -> None:
    dataset.PatientIdentityRemoved = "YES"
    # LO values are limited to 64 characters, each option is a separate value
    dataset.DeidentificationMethod = [PROFILE_NAME] + [m for _, m in options.codes[1:]]
    dataset.DeidentificationMethodCodeSequence = [_code(*code) for code in options.codes]
    dataset.LongitudinalTemporalInformationModified = (
        "UNMODIFIED" if options.retain_dates else "REMOVED"
    )


def _code(value: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = meaning
    return item


def _burned_in_warnings(dataset: Dataset) -> list[str]:
    if "PixelData" not in dataset:
        return []
    burned_in = str(dataset.get("BurnedInAnnotation", "")).strip().upper()
    modality = str(dataset.get("Modality", "")).strip().upper()
    if burned_in == "YES":
        return ["BurnedInAnnotation is YES, text in the pixel data is not removed."]
    if burned_in != "NO" and modality in BURNED_IN_RISK_MODALITIES:
        return [f"BurnedInAnnotation is not set for {modality}, pixel data may contain text."]
    return []
