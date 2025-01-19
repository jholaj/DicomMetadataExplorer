import random
import string
from datetime import datetime, timedelta

import pydicom
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class ToolsViewer(QWidget):
    metadata_modified = Signal(str)  # Emits file path of modified dataset

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initialize_ui()

    def initialize_ui(self):
        """Initialize the tools panel UI."""
        layout = QVBoxLayout(self)

        # Create group boxes for different tool categories
        self.create_anonymization_group(layout)
        self.create_tag_operations_group(layout)

        # Progress bar for operations
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Add stretcher at the bottom
        layout.addStretch()

    def create_anonymization_group(self, layout):
        """Create the anonymization tools group."""
        group = QGroupBox("Anonymization Tools")
        group_layout = QVBoxLayout()

        # Radio buttons for anonymization type
        self.anon_type_group = QButtonGroup(self)

        self.basic_radio = QRadioButton("Basic Anonymization (Empty Values)")
        self.pseudo_radio = QRadioButton("Pseudo-Anonymization (Random Values)")
        self.basic_radio.setChecked(True)

        self.anon_type_group.addButton(self.basic_radio)
        self.anon_type_group.addButton(self.pseudo_radio)

        group_layout.addWidget(self.basic_radio)
        group_layout.addWidget(self.pseudo_radio)

        # Info label with specific tags
        info_label = QLabel(
            "Will anonymize following DICOM tags:\n"
            "- Patient Name (0010,0010)\n"
            "- Patient ID (0010,0020)\n"
            "- Birth Date (0010,0030)\n"
            "- Patient's Age (0010,1010)\n"
            "- Patient's Sex (0010,0040)\n"
            "- Other identifying information"
        )
        info_label.setStyleSheet("color: gray;")
        group_layout.addWidget(info_label)

        # Anonymize buttons
        self.anonymize_btn = QPushButton("Anonymize Current Image")
        self.anonymize_btn.clicked.connect(self.anonymize_current)
        group_layout.addWidget(self.anonymize_btn)

        self.anonymize_all_btn = QPushButton("Anonymize All Loaded Images")
        self.anonymize_all_btn.clicked.connect(self.anonymize_all)
        group_layout.addWidget(self.anonymize_all_btn)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def create_tag_operations_group(self, layout):
        """Create the tag operations tools group."""
        group = QGroupBox("Tag Operations")
        group_layout = QVBoxLayout()

        # Remove private tags button
        self.remove_private_btn = QPushButton("Remove Private Tags")
        self.remove_private_btn.setToolTip("Removes all private DICOM tags (odd group numbers)")
        self.remove_private_btn.clicked.connect(self.remove_private_tags)
        group_layout.addWidget(self.remove_private_btn)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def _check_current_file(self):
        """Check if there's a current file selected."""
        if not hasattr(self.window(), 'current_file') or not self.window().current_file:
            QMessageBox.warning(self, "Error", "No DICOM file selected")
            return False
        return True

    def anonymize_current(self):
        """Anonymize the currently selected DICOM file."""
        if not self._check_current_file():
            return

        try:
            dataset = self.window().datasets[self.window().current_file]
            self._anonymize_dataset(dataset)
            self.metadata_modified.emit(self.window().current_file)
            QMessageBox.information(self, "Success", "Current image anonymized successfully")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to anonymize: {str(e)}")

    def anonymize_all(self):
        """Anonymize all loaded DICOM files."""
        if not self.window().datasets:
            QMessageBox.warning(self, "Error", "No DICOM files loaded")
            return

        try:
            self.progress_bar.setMaximum(len(self.window().datasets))
            self.progress_bar.setValue(0)
            self.progress_bar.show()

            for i, (file_path, dataset) in enumerate(self.window().datasets.items()):
                self._anonymize_dataset(dataset)
                self.metadata_modified.emit(file_path)
                self.progress_bar.setValue(i + 1)

            self.progress_bar.hide()
            QMessageBox.information(self, "Success", "All images anonymized successfully")
        except Exception as e:
            self.progress_bar.hide()
            QMessageBox.warning(self, "Error", f"Failed to anonymize all images: {str(e)}")

    def _anonymize_dataset(self, dataset):
        """Perform the actual anonymization on a dataset."""
        sensitive_tags = [
            'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex',
            'PatientAge', 'PatientWeight', 'PatientAddress', 'PatientTelephoneNumbers',
            'InstitutionName', 'InstitutionAddress', 'ReferringPhysicianName',
            'PhysiciansOfRecord', 'OperatorsName', 'OtherPatientIDs', 'OtherPatientNames',
            'PatientBirthName', 'PatientMotherBirthName', 'MilitaryRank', 'BranchOfService',
            'PatientInsurancePlanCodeSequence', 'PatientReligiousPreference',
            'MedicalRecordLocator', 'ReferencedPatientPhotoSequence',
            'ResponsiblePerson', 'ResponsibleOrganization'
        ]

        use_random = self.pseudo_radio.isChecked()

        for tag in sensitive_tags:
            if hasattr(dataset, tag):
                if use_random:
                    if tag == 'PatientName':
                        setattr(dataset, tag, self._generate_random_name())
                    elif tag == 'PatientID':
                        setattr(dataset, tag, self._generate_random_id())
                    elif tag == 'PatientBirthDate':
                        setattr(dataset, tag, self._generate_random_date())
                    elif tag == 'PatientSex':
                        setattr(dataset, tag, random.choice(['M', 'F', 'O']))
                    else:
                        setattr(dataset, tag, self._generate_random_string(8))
                else:
                    setattr(dataset, tag, '')

    def remove_private_tags(self):
        """Remove all private tags from the current DICOM file."""
        if not self._check_current_file():
            return

        try:
            dataset = self.window().datasets[self.window().current_file]
            dataset.remove_private_tags()
            self.metadata_modified.emit(self.window().current_file)
            QMessageBox.information(self, "Success", "Private tags removed successfully")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to remove private tags: {str(e)}")

    def _generate_random_string(self, length):
        """Generate a random string of specified length."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def _generate_random_name(self):
        """Generate a random patient name."""
        return f"Anonymous_{self._generate_random_string(6)}"

    def _generate_random_id(self):
        """Generate a random patient ID."""
        return f"ID_{self._generate_random_string(8)}"

    def _generate_random_date(self):
        """Generate a random date within the last 80 years."""
        end_date = datetime.now() - timedelta(days=365*18)  # At least 18 years old
        start_date = end_date - timedelta(days=365*62)  # Up to 80 years old
        days_between = (end_date - start_date).days
        random_days = random.randint(0, days_between)
        random_date = start_date + timedelta(days=random_days)
        return random_date.strftime('%Y%m%d')

    def _remove_uids(self, dataset):
        """Remove all UIDs from dataset."""
        uid_tags = [tag for tag in dataset.dir() if 'UID' in tag]
        for tag in uid_tags:
            if hasattr(dataset, tag):
                setattr(dataset, tag, '')

    def _reset_study_datetime(self, dataset):
        """Reset study date and time tags."""
        datetime_tags = ['StudyDate', 'StudyTime', 'SeriesDate', 'SeriesTime',
                        'AcquisitionDate', 'AcquisitionTime', 'ContentDate', 'ContentTime']
        for tag in datetime_tags:
            if hasattr(dataset, tag):
                setattr(dataset, tag, '')

    def _remove_institution_info(self, dataset):
        """Remove institution-related information."""
        institution_tags = ['InstitutionName', 'InstitutionAddress', 'InstitutionalDepartmentName',
                          'InstitutionCodeSequence']
        for tag in institution_tags:
            if hasattr(dataset, tag):
                setattr(dataset, tag, '')

    def _remove_dates(self, dataset):
        """Remove all date and time related tags."""
        date_tags = [tag for tag in dataset.dir() if 'Date' in tag or 'Time' in tag]
        for tag in date_tags:
            if hasattr(dataset, tag):
                setattr(dataset, tag, '')

    def _remove_device_info(self, dataset):
        """Remove device-related information."""
        device_tags = ['Manufacturer', 'ManufacturerModelName', 'DeviceSerialNumber',
                      'SoftwareVersions', 'StationName', 'DeviceUID']
        for tag in device_tags:
            if hasattr(dataset, tag):
                setattr(dataset, tag, '')
