from PySide6.QtCore import QSize

# UI
ZOOM_FACTOR = 1.15
ZOOM_MIN = 1.0
ZOOM_MAX = 10

THUMBNAIL_SIZE = QSize(70, 70)
THUMBNAIL_PANEL_WIDTH = 200


sensitive_tags = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex",
    "PatientAge", "PatientWeight", "PatientAddress", "PatientTelephoneNumbers",
    "InstitutionName", "InstitutionAddress", "ReferringPhysicianName",
    "PhysiciansOfRecord", "OperatorsName", "OtherPatientIDs", "OtherPatientNames",
    "PatientBirthName", "PatientMotherBirthName", "MilitaryRank", "BranchOfService",
    "PatientInsurancePlanCodeSequence", "PatientReligiousPreference",
    "MedicalRecordLocator", "ReferencedPatientPhotoSequence",
    "ResponsiblePerson", "ResponsibleOrganization"
]
