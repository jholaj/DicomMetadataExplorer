from pathlib import Path

from pydicom.datadict import DicomDictionary, dictionary_description, dictionary_VR, tag_for_keyword
from pydicom.tag import Tag
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from styles.icons import add_icon
from styles.theme import SELECTED_COLOR, TEXT_MUTED_COLOR
from utils.dicom_properties import get_tag_value_str


def resolve_tag(text):
    """Resolve user input (keyword or 'group,element') to a pydicom Tag.

    Returns None when the input matches neither a dictionary keyword
    nor a hexadecimal group,element pair.
    """
    keyword_tag = tag_for_keyword(text)
    if keyword_tag is not None:
        return Tag(keyword_tag)

    cleaned = text.strip().strip("()")
    if "," in cleaned:
        try:
            group, element = (int(part.strip(), 16) for part in cleaned.split(",", 1))
            return Tag(group, element)
        except ValueError:
            return None
    return None


class CompareMetadataDialog(QDialog):
    """Dialog comparing metadata of two loaded DICOM files side by side."""

    MISSING = "-"

    def __init__(self, datasets, current_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Metadata")
        self.datasets = datasets
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        # File selectors
        selector_row = QHBoxLayout()
        self.combo_a = QComboBox()
        self.combo_b = QComboBox()
        for path in datasets:
            for combo in (self.combo_a, self.combo_b):
                combo.addItem(Path(path).name, path)
                combo.setItemData(combo.count() - 1, path, Qt.ToolTipRole)

        paths = list(datasets)
        self.combo_a.setCurrentIndex(paths.index(current_file))
        other = next((i for i, p in enumerate(paths) if p != current_file), 0)
        self.combo_b.setCurrentIndex(other)

        selector_row.addWidget(QLabel("File A:"))
        selector_row.addWidget(self.combo_a, stretch=1)
        selector_row.addSpacing(12)
        selector_row.addWidget(QLabel("File B:"))
        selector_row.addWidget(self.combo_b, stretch=1)
        layout.addLayout(selector_row)

        self.diff_only = QCheckBox("Show only differences")
        self.diff_only.setChecked(True)
        layout.addWidget(self.diff_only)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "File A", "File B"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.combo_a.currentIndexChanged.connect(self.populate)
        self.combo_b.currentIndexChanged.connect(self.populate)
        self.diff_only.toggled.connect(self.populate)
        self.populate()

    @staticmethod
    def _tag_values(dataset):
        """Map (group, element) -> (tag string, name, value string)."""
        values = {}
        for elem in dataset:
            if elem.tag.group == 0x7FE0:
                continue
            value_str, _ = get_tag_value_str(elem)
            key = (elem.tag.group, elem.tag.element)
            tag_str = f"({elem.tag.group:04x},{elem.tag.element:04x})"
            values[key] = (tag_str, elem.name or "", value_str)
        return values

    def populate(self):
        """Fill the tree with the union of tags from both files."""
        self.tree.clear()
        ds_a = self.datasets.get(self.combo_a.currentData())
        ds_b = self.datasets.get(self.combo_b.currentData())
        if ds_a is None or ds_b is None:
            return

        values_a = self._tag_values(ds_a)
        values_b = self._tag_values(ds_b)
        highlight = QColor(SELECTED_COLOR)

        differences = 0
        for key in sorted(set(values_a) | set(values_b)):
            tag_str, name, value_a = values_a.get(key, (None, None, self.MISSING))
            tag_b, name_b, value_b = values_b.get(key, (None, None, self.MISSING))
            tag_str = tag_str or tag_b
            name = name or name_b

            differs = value_a != value_b
            if differs:
                differences += 1
            elif self.diff_only.isChecked():
                continue

            item = QTreeWidgetItem([tag_str, name, value_a, value_b])
            if differs:
                for column in range(4):
                    item.setBackground(column, highlight)
            self.tree.addTopLevelItem(item)

        total = len(set(values_a) | set(values_b))
        self.summary_label.setText(f"{differences} of {total} tags differ")


class AddTagDialog(QDialog):
    """Dialog for adding a new DICOM tag to the dataset."""

    # All keywords from the DICOM dictionary, for autocompletion
    _KEYWORDS = sorted({entry[4] for entry in DicomDictionary.values() if entry[4]})

    # Common VRs offered for private/unknown tags
    VR_CHOICES = (
        ("LO", "Long String (text, up to 64 chars)"),
        ("SH", "Short String (text, up to 16 chars)"),
        ("LT", "Long Text"),
        ("IS", "Integer String"),
        ("DS", "Decimal String"),
        ("US", "Unsigned Short (binary integer)"),
        ("UL", "Unsigned Long (binary integer)"),
        ("FL", "Float"),
        ("FD", "Double"),
        ("CS", "Code String"),
        ("DA", "Date (YYYYMMDD)"),
        ("TM", "Time (HHMMSS)"),
        ("DT", "DateTime"),
        ("PN", "Person Name"),
        ("UI", "Unique Identifier"),
        ("UN", "Unknown (raw bytes)"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add DICOM Tag")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("Keyword (PatientName) or group,element (0010,0010)")

        completer = QCompleter(self._KEYWORDS, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.tag_edit.setCompleter(completer)

        self.hint_label = QLabel(" ")
        self.hint_label.setStyleSheet(f"color: {TEXT_MUTED_COLOR}; font-size: 12px;")

        self.vr_edit = QComboBox()
        self.vr_edit.setEditable(True)
        self.vr_edit.addItem("")  # empty = resolve from dictionary
        for index, (code, description) in enumerate(self.VR_CHOICES, start=1):
            self.vr_edit.addItem(code)
            self.vr_edit.setItemData(index, description, Qt.ToolTipRole)
        self.vr_edit.lineEdit().setPlaceholderText("Auto (from dictionary)")
        self.vr_edit.lineEdit().setMaxLength(2)
        self.value_edit = QLineEdit()

        layout.addRow("Tag:", self.tag_edit)
        layout.addRow("", self.hint_label)
        layout.addRow("VR:", self.vr_edit)
        layout.addRow("Value:", self.value_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        add_button = button_box.button(QDialogButtonBox.Ok)
        add_button.setText("Add")
        add_button.setIcon(add_icon())
        add_button.setIconSize(QSize(12, 12))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.tag_edit.textChanged.connect(self._update_hint)
        self.tag_edit.setFocus()

    def _update_hint(self, text):
        """Show the resolved tag, VR, and name for the current input."""
        text = text.strip()
        if not text:
            self.hint_label.setText(" ")
            return

        tag = resolve_tag(text)
        if tag is None:
            self.hint_label.setText("Unknown tag - enter a keyword or group,element")
            return

        try:
            vr = dictionary_VR(tag)
            description = dictionary_description(tag)
            self.hint_label.setText(
                f"({tag.group:04x},{tag.element:04x})  VR {vr}  -  {description}"
            )
            if not self.get_vr():
                self.vr_edit.lineEdit().setPlaceholderText(f"Auto ({vr})")
        except KeyError:
            self.hint_label.setText(
                f"({tag.group:04x},{tag.element:04x})  private/unknown tag - "
                "pick a VR (IS for integers, LO for text)"
            )

    def get_tag_text(self):
        return self.tag_edit.text().strip()

    def get_vr(self):
        return self.vr_edit.currentText().strip().upper()

    def get_value(self):
        return self.value_edit.text()


class EditTagDialog(QDialog):
    def __init__(self, tag_item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit DICOM Tag")
        self.tag_item = tag_item

        layout = QFormLayout(self)
        self.value_edit = QLineEdit(tag_item.text(3))

        layout.addRow("Tag:", QLabel(tag_item.text(0)))
        layout.addRow("Name:", QLabel(tag_item.text(1)))
        layout.addRow("VR:", QLabel(tag_item.text(2)))
        layout.addRow("Value:", self.value_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_value(self):
        return self.value_edit.text()
