from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QMessageBox, QMenu,
    QDialog
)
from PySide6.QtCore import Qt
from utils.dicom_utils import get_tag_value_str
from ui.dialogs import EditTagDialog

class MetadataViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = None

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        layout.addWidget(self.search_input)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)
        self.search_input.textChanged.connect(self.filter_items)

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item:
            menu = QMenu()
            edit_action = menu.addAction("Edit Tag")
            action = menu.exec(self.tree.viewport().mapToGlobal(position))

            if action == edit_action:
                self.edit_tag(item)

    def edit_tag(self, item):
        if not self.dataset:
            return

        dialog = EditTagDialog(item, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                tag_str = item.text(0)[1:-1]
                group, element = map(lambda x: int(x, 16), tag_str.split(','))
                tag = (group, element)

                data_element = self.dataset[tag]
                new_value = dialog.get_value()

                vr = item.text(2)
                if vr in ['DS', 'FL', 'FD']:
                    data_element.value = float(new_value)
                elif vr in ['IS', 'SL', 'SS', 'UL', 'US']:
                    data_element.value = int(new_value)
                else:
                    data_element.value = new_value

                item.setText(3, str(data_element.value))

                if hasattr(self.window(), 'status_bar'):
                    self.window().status_bar.showMessage(
                        "Tag updated successfully", 3000
                    )

            except Exception as e:
                QMessageBox.warning(
                    self, "Error", f"Failed to update tag: {str(e)}"
                )

    def filter_items(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower() for j in range(item.columnCount())
            )
            item.setHidden(not matches)

    def load_metadata(self, dataset):
        self.tree.clear()
        self.dataset = dataset

        for elem in dataset:
            if elem.tag.group != 0x7FE0:  # Skip pixel data
                item = QTreeWidgetItem()
                tag_str = f"({elem.tag.group:04x},{elem.tag.element:04x})"
                value_str = get_tag_value_str(elem)

                item.setText(0, tag_str)
                item.setText(1, elem.name or "")
                item.setText(2, getattr(elem, "VR", ""))
                item.setText(3, value_str)
                self.tree.addTopLevelItem(item)
