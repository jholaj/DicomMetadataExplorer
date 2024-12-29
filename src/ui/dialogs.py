from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit,
    QDialogButtonBox
)
from constants import BACKGROUND_COLOR, TEXT_COLOR

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

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BACKGROUND_COLOR};
                color: {TEXT_COLOR};
            }}
            QLabel {{
                color: {TEXT_COLOR};
            }}
            QLineEdit {{
                padding: 6px;
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: {TEXT_COLOR};
            }}
        """)

    def get_value(self):
        return self.value_edit.text()
