from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QMessageBox, QMenu,
    QDialog
)
from PySide6.QtCore import Qt
from pydicom.sequence import Sequence
from utils.dicom_utils import get_tag_value_str
from ui.dialogs import EditTagDialog

class MetadataViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = None

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        layout.addWidget(self.search_input)

        # Tree widget for displaying metadata
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Configure header resizing
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)
        self.search_input.textChanged.connect(self.filter_items)

    def show_context_menu(self, position):
        """Show a context menu for editing tags."""
        item = self.tree.itemAt(position)
        if item:
            menu = QMenu()
            edit_action = menu.addAction("Edit Tag")
            action = menu.exec(self.tree.viewport().mapToGlobal(position))

            if action == edit_action:
                self.edit_tag(item)

    def find_and_edit_tag(self, dataset, tag, new_value, vr):
        """Recursively find and edit a tag in the dataset or its sequences."""
        if tag in dataset:
            # Update the tag based on VR
            if vr in ['DS', 'FL', 'FD']:
                dataset[tag].value = float(new_value)
            elif vr in ['IS', 'SL', 'SS', 'UL', 'US']:
                dataset[tag].value = int(new_value)
            else:
                dataset[tag].value = new_value

        # Check if dataset contains sequences
        for element in dataset:
            if isinstance(element.value, Sequence):
                for sub_dataset in element.value:
                    self.find_and_edit_tag(sub_dataset, tag, new_value, vr)

    def edit_tag(self, item):
        """Edit the selected tag."""
        dialog = EditTagDialog(item, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                tag_str = item.text(0)[1:-1]
                group, element = map(lambda x: int(x, 16), tag_str.split(','))
                tag = (group, element)

                # Retrieve VR from data_element or item text
                data_element = self.dataset.get(tag, None)
                if data_element:
                    vr = data_element.VR if hasattr(data_element, 'VR') else item.text(2)
                else:
                    vr = item.text(2)  # Fallback VR

                new_value = dialog.get_value()

                # Use the recursive function to find and edit the tag
                self.find_and_edit_tag(self.dataset, tag, new_value, vr)

                # Update the item display
                item.setText(3, str(new_value))

                if hasattr(self.window(), 'status_bar'):
                    self.window().status_bar.showMessage(
                        "Tag updated successfully", 3000
                    )

            except Exception as e:
                QMessageBox.warning(
                    self, "Error", f"Failed to update tag {tag}: {str(e)}"
                )

    def filter_items(self, text):
        """Filter tree items based on search text."""
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower() for j in range(item.columnCount())
            )
            item.setHidden(not matches)

    def create_sequence_tree(self, sequence_items, parent_item):
        """Create a tree structure for DICOM sequences."""
        try:
            for item in sequence_items:
                for elem in item['elements']:
                    child = QTreeWidgetItem(parent_item)
                    tag_str = f"({elem['tag'][0]:04x},{elem['tag'][1]:04x})"
                    value_str = str(elem['value'][0]) if isinstance(elem['value'], tuple) else str(elem['value'])

                    child.setText(0, tag_str)
                    child.setText(1, elem['name'])
                    child.setText(2, elem['vr'])
                    child.setText(3, value_str)
        except Exception as e:
            print(f"Error in create_sequence_tree: {e}")

    def load_metadata(self, dataset):
        """Load DICOM metadata into the tree widget."""
        self.tree.clear()
        self.dataset = dataset

        for elem in dataset:
            if elem.tag.group != 0x7FE0:  # Skip pixel data
                item = QTreeWidgetItem()
                tag_str = f"({elem.tag.group:04x},{elem.tag.element:04x})"
                value_str, sequence_items = get_tag_value_str(elem)
                item.setText(0, tag_str)
                item.setText(1, elem.name or "")
                item.setText(2, getattr(elem, "VR", ""))
                item.setText(3, value_str)
                self.tree.addTopLevelItem(item)

                if sequence_items:
                    self.create_sequence_tree(sequence_items, item)
