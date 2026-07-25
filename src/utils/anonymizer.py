from pydicom.sequence import Sequence

# Identifying tags (by keyword) and their replacement values.
# Person names (VR PN) are anonymized in addition to this list.
REPLACEMENTS = {
    "PatientID": "ANONYMOUS",
    "OtherPatientIDs": "ANONYMOUS",
    "PatientBirthDate": "",
    "PatientBirthTime": "",
    "PatientAddress": "",
    "PatientTelephoneNumbers": "",
    "ReferringPhysicianAddress": "",
    "ReferringPhysicianTelephoneNumbers": "",
    "InstitutionName": "",
    "InstitutionAddress": "",
    "InstitutionalDepartmentName": "",
    "StationName": "",
    "AccessionNumber": "",
    "DeviceSerialNumber": "",
}


def anonymize_dataset(dataset):
    """Anonymize identifying tags in the dataset (recursively into sequences).

    Replaces all person names (VR PN), the tags listed in REPLACEMENTS,
    and removes private tags. Returns the number of changed elements.
    """
    changed = _anonymize(dataset)
    dataset.remove_private_tags()
    return changed


def _anonymize(dataset):
    changed = 0
    for elem in dataset:
        if isinstance(elem.value, Sequence):
            for item in elem.value:
                changed += _anonymize(item)
        elif elem.VR == "PN":
            if str(elem.value):
                elem.value = "ANONYMOUS"
                changed += 1
        elif elem.keyword in REPLACEMENTS:
            replacement = REPLACEMENTS[elem.keyword]
            if str(elem.value) != replacement:
                elem.value = replacement
                changed += 1
    return changed
