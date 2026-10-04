"""Dialogs for editing elements, comparing files, anonymization and validation."""

import csv
from pathlib import Path

from pydicom.datadict import (
    DicomDictionary,
    dictionary_description,
    dictionary_VM,
    dictionary_VR,
)
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QRadioButton,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from dicom_explorer.core.anonymizer import AnonymizationOptions
from dicom_explorer.core.elements import (
    BINARY_VRS,
    SINGLE_VALUE_TEXT_VRS,
    common_elements,
    element_name,
    element_vr,
    format_tag,
    is_pixel_data,
    parse_tag,
    parse_value,
    value_text,
    walk,
)
from dicom_explorer.core.validation import ERROR, WARNING, validate_dataset, validate_workspace
from dicom_explorer.styles.icons import add_icon
from dicom_explorer.styles.theme import ERROR_COLOR, WARNING_COLOR
from dicom_explorer.ui.text import plural

LONG_TEXT_VRS = frozenset({"LT", "ST", "UT"})
VR_CHOICES = (
    ("LO", "Long String"),
    ("SH", "Short String"),
    ("LT", "Long Text"),
    ("ST", "Short Text"),
    ("UT", "Unlimited Text"),
    ("CS", "Code String"),
    ("PN", "Person Name"),
    ("DA", "Date (YYYYMMDD)"),
    ("TM", "Time (HHMMSS)"),
    ("DT", "Date Time"),
    ("IS", "Integer String"),
    ("DS", "Decimal String"),
    ("US", "Unsigned Short"),
    ("UL", "Unsigned Long"),
    ("SS", "Signed Short"),
    ("SL", "Signed Long"),
    ("FL", "Float"),
    ("FD", "Double"),
    ("UI", "Unique Identifier"),
    ("AT", "Attribute Tag"),
)
KEYWORDS = sorted({entry[4] for entry in DicomDictionary.values() if entry[4]})
ROW_HEIGHT = 26


class _ValidatedDialog(QDialog):
    """Form dialog with OK enabled only for valid input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.error_label = QLabel()
        self.error_label.setObjectName("error_label")
        self.error_label.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not message)


class EditValueDialog(_ValidatedDialog):
    def __init__(self, element, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit DICOM Element")
        self.setMinimumWidth(520)
        self.vr = str(element.VR)
        self.value = None
        self.original_text = value_text(element)
        try:
            vm = dictionary_VM(element.tag)
        except KeyError:
            vm = "-"

        if self.vr in LONG_TEXT_VRS:
            self.editor = QPlainTextEdit(self.original_text)
            self.editor.setMinimumHeight(140)
        else:
            self.editor = QLineEdit(self.original_text)
        self.editor.textChanged.connect(self._validate)

        layout = QFormLayout(self)
        layout.addRow("Tag:", QLabel(format_tag(element.tag)))
        layout.addRow("Name:", QLabel(element.name))
        layout.addRow("VR / VM:", QLabel(f"{self.vr}  ·  dictionary VM {vm}"))
        layout.addRow("Value:", self.editor)
        if self.vr not in SINGLE_VALUE_TEXT_VRS:
            hint = QLabel("Separate multiple values with a backslash.")
            hint.setObjectName("hint_label")
            layout.addRow("", hint)
        layout.addRow("", self.error_label)
        layout.addRow(self.buttons)
        self._validate()

    @property
    def unchanged(self) -> bool:
        return self._text() == self.original_text

    def _text(self) -> str:
        if isinstance(self.editor, QPlainTextEdit):
            return self.editor.toPlainText()
        return self.editor.text()

    def _validate(self):
        try:
            self.value = parse_value(self._text(), self.vr)
            self._set_error("")
        except ValueError as e:
            self._set_error(str(e))


class AddElementDialog(_ValidatedDialog):
    def __init__(self, target: str, existing_tags, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add DICOM Element")
        self.setMinimumWidth(480)
        self.existing_tags = {int(tag) for tag in existing_tags}
        self.tag = None
        self.vr = ""
        self.value = None

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("Keyword (PatientName) or group,element (0010,0010)")
        completer = QCompleter(KEYWORDS, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.tag_edit.setCompleter(completer)
        self.hint_label = QLabel(" ")
        self.hint_label.setObjectName("hint_label")

        self.vr_edit = QComboBox()
        self.vr_edit.setEditable(True)
        self.vr_edit.addItem("")
        for index, (vr, description) in enumerate(VR_CHOICES, start=1):
            self.vr_edit.addItem(vr)
            self.vr_edit.setItemData(index, description, Qt.ToolTipRole)
        self.vr_edit.lineEdit().setPlaceholderText("Auto (from dictionary)")
        self.vr_edit.lineEdit().setMaxLength(2)
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Multiple values separated by a backslash")

        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setText("Add")
        ok.setIcon(add_icon())
        ok.setIconSize(QSize(12, 12))
        target_label = QLabel(target)
        target_label.setObjectName("hint_label")

        layout = QFormLayout(self)
        layout.addRow("Add to:", target_label)
        layout.addRow("Tag:", self.tag_edit)
        layout.addRow("", self.hint_label)
        layout.addRow("VR:", self.vr_edit)
        layout.addRow("Value:", self.value_edit)
        layout.addRow("", self.error_label)
        layout.addRow(self.buttons)

        self.tag_edit.textChanged.connect(self._validate)
        self.vr_edit.currentTextChanged.connect(self._validate)
        self.value_edit.textChanged.connect(self._validate)
        self.tag_edit.setFocus()
        self._validate()

    def _validate(self):
        self.hint_label.setText(" ")
        try:
            self.tag = parse_tag(self.tag_edit.text())
        except ValueError:
            self.tag = None
            self._set_error("")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        try:
            dictionary_vr = dictionary_VR(self.tag).split(" or ")[0]
            description = dictionary_description(self.tag)
            self.hint_label.setText(f"{format_tag(self.tag)}  VR {dictionary_vr}  ·  {description}")
        except KeyError:
            dictionary_vr = ""
            self.hint_label.setText(f"{format_tag(self.tag)}  private or unknown tag")
        self.vr = self.vr_edit.currentText().strip().upper() or dictionary_vr
        self._set_error(self._problem())

    def _problem(self) -> str:
        if int(self.tag) in self.existing_tags:
            return "This element already exists here."
        if self.tag.group == 0x0002:
            return "File meta elements cannot be added."
        if not self.vr:
            return "Choose a VR for this tag."
        if self.vr == "SQ" or self.vr in BINARY_VRS:
            return f"Elements with VR {self.vr} cannot be entered as text."
        try:
            self.value = parse_value(self.value_edit.text(), self.vr)
        except ValueError as e:
            return str(e)
        return ""


class StudyTagsDialog(_ValidatedDialog):
    """Values shared by all files of a study, edited for all of them at once."""

    def __init__(self, documents, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Study Tags")
        self.resize(860, 620)
        elements = common_elements([document.dataset for document in documents])
        self.elements = {int(element.tag): element for element in elements}
        self.changes = {}
        self._errors = {}

        intro = QLabel(
            f"Tags with the same value in all {plural(len(documents), 'file')} of the study. "
            "Double-click a value to edit it, changes are written to every file."
        )
        intro.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tag, name or value")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((110, 260, 44)):
            header.resizeSection(column, width)
        for element in elements:
            texts = [format_tag(element.tag), element_name(element), element_vr(element)]
            item = QTreeWidgetItem([*texts, value_text(element)])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(0, Qt.UserRole, int(element.tag))
            item.setSizeHint(0, QSize(0, ROW_HEIGHT))
            self.tree.addTopLevelItem(item)
        self.tree.setItemDelegateForColumn(3, _FullCellDelegate(self.tree))
        self.tree.itemActivated.connect(lambda item: self.tree.editItem(item, 3))
        self.tree.itemChanged.connect(self._on_changed)

        self.buttons.button(QDialogButtonBox.Ok).setText(
            f"Apply to {plural(len(documents), 'file')}"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.search)
        layout.addWidget(self.tree)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self._update_state()

    def _on_changed(self, item: QTreeWidgetItem, column: int):
        if column != 3:
            return
        tag = item.data(0, Qt.UserRole)
        element = self.elements[tag]
        self.changes.pop(tag, None)
        self._errors.pop(tag, None)
        if item.text(3) != value_text(element):
            try:
                self.changes[tag] = parse_value(item.text(3), element_vr(element))
            except ValueError as e:
                self._errors[tag] = f"{element.keyword or format_tag(tag)}: {e}"

        font = QFont()
        font.setBold(tag in self.changes or tag in self._errors)
        self.tree.blockSignals(True)
        item.setFont(3, font)
        item.setData(3, Qt.ForegroundRole, QColor(ERROR_COLOR) if tag in self._errors else None)
        item.setToolTip(3, self._errors.get(tag, ""))
        self.tree.blockSignals(False)
        self._update_state()

    def _update_state(self):
        self._set_error(next(iter(self._errors.values()), ""))
        if not self._errors:
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.changes))

    def _filter(self, text: str):
        needle = text.strip().lower()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            haystack = " ".join(item.text(column) for column in range(4)).lower()
            item.setHidden(needle not in haystack)


class CompareDialog(QDialog):
    """Element by element comparison of two documents, nested sequences included."""

    def __init__(self, documents, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Metadata")
        self.resize(1000, 640)
        self.documents = list(documents)

        self.combo_a, self.combo_b = QComboBox(), QComboBox()
        for document in self.documents:
            for combo in (self.combo_a, self.combo_b):
                combo.addItem(document.name)
                combo.setItemData(combo.count() - 1, str(document.path), Qt.ToolTipRole)
        index_a = self.documents.index(current) if current in self.documents else 0
        self.combo_a.setCurrentIndex(index_a)
        self.combo_b.setCurrentIndex(1 if index_a == 0 else 0)
        self.diff_only = QCheckBox("Show only differences")
        self.diff_only.setChecked(True)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Element", "Tag", "File A", "File B"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((300, 170, 240)):
            header.resizeSection(column, width)
        self.summary_label = QLabel()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("File A:"))
        selectors.addWidget(self.combo_a, stretch=1)
        selectors.addSpacing(12)
        selectors.addWidget(QLabel("File B:"))
        selectors.addWidget(self.combo_b, stretch=1)
        layout = QVBoxLayout(self)
        layout.addLayout(selectors)
        layout.addWidget(self.diff_only)
        layout.addWidget(self.tree)
        layout.addWidget(self.summary_label)
        layout.addWidget(buttons)

        self.combo_a.currentIndexChanged.connect(self.populate)
        self.combo_b.currentIndexChanged.connect(self.populate)
        self.diff_only.toggled.connect(self.populate)
        self.populate()

    def populate(self):
        values_a = _texts(self.documents[self.combo_a.currentIndex()].dataset)
        values_b = _texts(self.documents[self.combo_b.currentIndex()].dataset)
        paths = sorted(values_a.keys() | values_b.keys())
        show_all = not self.diff_only.isChecked()
        differences = 0
        items = []
        for path in paths:
            a, b = values_a.get(path, "—"), values_b.get(path, "—")
            differences += a != b
            if a != b or show_all:
                items.append(_compare_item(path, a, b, highlight=a != b and show_all))
        self.tree.clear()
        self.tree.addTopLevelItems(items)
        self.summary_label.setText(f"{differences} of {len(paths)} elements differ")


class AnonymizeDialog(QDialog):
    def __init__(self, current, study: list, documents: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anonymize")
        self.setMinimumWidth(560)
        self._targets = ([current], study, documents)

        intro = QLabel(
            "Applies the DICOM PS3.15 Basic Application Level Confidentiality Profile. "
            "Changes can be undone and are written to disk on save."
        )
        intro.setWordWrap(True)
        self.scope = QButtonGroup(self)
        labels = (
            f"Current file ({current.name})",
            f"Current study ({plural(len(study), 'file')})",
            f"All loaded files ({len(documents)})",
        )
        for scope, label in enumerate(labels):
            button = QRadioButton(label)
            button.setEnabled(scope == 0 or len(self._targets[scope]) > 1)
            button.setChecked(scope == 0)
            self.scope.addButton(button, scope)

        self.retain_dates = QCheckBox("Retain dates and times")
        self.retain_characteristics = QCheckBox("Retain patient sex, age, size and weight")
        self.retain_uids = QCheckBox("Retain UIDs")
        warning = QLabel("Text burned into the pixel data is not removed.")
        warning.setObjectName("warning_label")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Anonymize")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        for button in self.scope.buttons():
            layout.addWidget(button)
        layout.addSpacing(6)
        for box in (self.retain_dates, self.retain_characteristics, self.retain_uids):
            layout.addWidget(box)
        layout.addWidget(warning)
        layout.addWidget(buttons)

    def targets(self) -> list:
        return self._targets[self.scope.checkedId()]

    def options(self) -> AnonymizationOptions:
        return AnonymizationOptions(
            retain_dates=self.retain_dates.isChecked(),
            retain_uids=self.retain_uids.isChecked(),
            retain_patient_characteristics=self.retain_characteristics.isChecked(),
        )


class ValidationReportDialog(QDialog):
    """Validation summary of all loaded files."""

    document_requested = Signal(object)

    def __init__(self, documents, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validation Report")
        self.resize(1000, 520)
        self.rows = []

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "IOD", "Errors", "Warnings", "First problem"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.itemDoubleClicked.connect(self._open)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((220, 250, 64, 84)):
            header.resizeSection(column, width)
        self.summary_label = QLabel()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        export = buttons.addButton("Export CSV...", QDialogButtonBox.ActionRole)
        export.clicked.connect(self.export_csv)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(self.summary_label)
        layout.addWidget(buttons)
        self._validate(documents)

    def export_csv(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Export Validation Report", "validation_report.csv", "CSV (*.csv)"
        )
        if not file_name:
            return
        try:
            with open(file_name, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["File", "IOD", "Severity", "Category", "Message", "Element"])
                for document, iod, issues in self.rows:
                    for issue in issues:
                        element = issue.path.keywords() if issue.path else ""
                        severity, category = issue.severity.value, issue.category.value
                        writer.writerow(
                            [document.path, iod, severity, category, issue.message, element]
                        )
        except OSError as e:
            QMessageBox.warning(self, "Export Failed", str(e))
            return
        self.summary_label.setText(f"Report exported to {Path(file_name).name}")

    def _open(self, item: QTreeWidgetItem):
        self.document_requested.emit(item.data(0, Qt.UserRole))

    def _validate(self, documents):
        progress = QProgressDialog("Validating files...", "Cancel", 0, len(documents), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(400)
        cross = validate_workspace({d.path: d.dataset for d in documents})
        for index, document in enumerate(documents):
            if progress.wasCanceled():
                break
            progress.setValue(index)
            report = validate_dataset(document.dataset)
            issues = report.sorted_issues() + cross.get(document.path, [])
            self.rows.append((document, report.iod, issues))
            self.tree.addTopLevelItem(_report_item(document, report.iod, issues))
        progress.setValue(len(documents))
        severities = [issue.severity for _, _, issues in self.rows for issue in issues]
        errors, warnings = severities.count(ERROR), severities.count(WARNING)
        self.summary_label.setText(
            f"{plural(len(self.rows), 'file')}, {plural(errors, 'error')}, "
            f"{plural(warnings, 'warning')}. "
            "Double-click a file to open its overview."
        )


class _FullCellDelegate(QStyledItemDelegate):
    """Editor over the whole cell including the item padding."""

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class _ReportItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column in (2, 3):
            return int(self.text(column)) < int(other.text(column))
        return self.text(column).lower() < other.text(column).lower()


def _texts(dataset) -> dict:
    return {
        entry.path: value_text(entry.element)
        for entry in walk(dataset)
        if not is_pixel_data(entry.element)
    }


def _compare_item(path, a: str, b: str, highlight: bool) -> QTreeWidgetItem:
    item = QTreeWidgetItem([path.keywords(), path.tags(), a, b])
    item.setToolTip(2, a[:2000])
    item.setToolTip(3, b[:2000])
    if highlight:
        for column in range(4):
            item.setBackground(column, QColor(WARNING_COLOR).darker(400))
    return item


def _report_item(document, iod: str, issues) -> QTreeWidgetItem:
    errors = sum(1 for issue in issues if issue.severity is ERROR)
    warnings = sum(1 for issue in issues if issue.severity is WARNING)
    first = next((i.message for i in issues if i.severity in (ERROR, WARNING)), "OK")
    item = _ReportItem([document.name, iod, str(errors), str(warnings), first])
    item.setToolTip(0, str(document.path))
    item.setData(0, Qt.UserRole, document)
    if errors:
        item.setForeground(2, QColor(ERROR_COLOR))
    if warnings:
        item.setForeground(3, QColor(WARNING_COLOR))
    return item
