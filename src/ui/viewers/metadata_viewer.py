from pydicom.datadict import dictionary_VR
from pydicom.sequence import Sequence
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from styles.icons import add_icon
from ui.dialogs import AddTagDialog, EditTagDialog, resolve_tag
from utils.dicom_properties import get_tag_value_str


def convert_value_for_vr(value, vr):
    """Convert a string value to the proper Python type for the given VR."""
    if vr in ("DS", "FL", "FD"):
        return float(value)
    if vr in ("IS", "SL", "SS", "UL", "US"):
        return int(value)
    if vr in ("UN", "OB", "OW"):
        # Binary VRs are stored as raw bytes, padded to even length
        data = value.encode() if isinstance(value, str) else bytes(value)
        if len(data) % 2:
            data += b"\x00"
        return data
    return value


class MetadataViewer(QWidget):
    dataset_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = None

        # Search input + add-tag button
        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value... (Ctrl+F)")
        self.search_input.setClearButtonEnabled(True)
        top_row.addWidget(self.search_input, stretch=1)

        self.add_tag_button = QPushButton(add_icon(), "Add Tag")
        self.add_tag_button.setIconSize(QSize(14, 14))
        self.add_tag_button.setToolTip("Add a new DICOM tag (Ctrl+T)")
        self.add_tag_button.clicked.connect(self.add_tag)
        top_row.addWidget(self.add_tag_button)
        layout.addLayout(top_row)

        # Focus search input with Ctrl+F
        search_shortcut = QShortcut(QKeySequence.Find, self)
        search_shortcut.activated.connect(self.focus_search)

        # Add a tag with Ctrl+T
        add_tag_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        add_tag_shortcut.activated.connect(self.add_tag)

        # Undo tag operations with Ctrl+Z
        self.undo_stack = []
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.undo_last)

        # Tree widget for displaying metadata
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Connect double-click signal to edit_tag method
        self.tree.itemDoubleClicked.connect(self.edit_tag)

        # Connect key event
        self.tree.keyPressEvent = self.handle_key_press

        # Configure header resizing
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)
        self.search_input.textChanged.connect(self.filter_items)

    def handle_key_press(self, event):
        """Handle key press events in the tree widget."""
        if event.key() == Qt.Key_Delete:
            current_item = self.tree.currentItem()
            if current_item:
                self.delete_tag(current_item)
        elif event.matches(QKeySequence.Copy):
            self.copy_value(self.tree.currentItem())
        else:
            # Call the parent class's keyPressEvent for other keys
            QTreeWidget.keyPressEvent(self.tree, event)

    def copy_value(self, item):
        """Copy the value of the given tree item to the clipboard."""
        if isinstance(item, QTreeWidgetItem):
            QApplication.clipboard().setText(item.text(3))
            self._show_status("Value copied to clipboard")

    def copy_tag_line(self, item):
        """Copy the whole tag line to the clipboard."""
        if isinstance(item, QTreeWidgetItem):
            line = "\t".join(item.text(i) for i in range(4))
            QApplication.clipboard().setText(line)
            self._show_status("Tag copied to clipboard")

    def show_context_menu(self, position):
        """Show a context menu for adding, editing, and deleting tags."""
        if self.dataset is None:
            return

        item = self.tree.itemAt(position)
        menu = QMenu()
        add_action = menu.addAction("Add Tag...")
        edit_action = delete_action = copy_value_action = copy_tag_action = None
        if item:
            edit_action = menu.addAction("Edit Tag")
            delete_action = menu.addAction("Delete Tag")
            menu.addSeparator()
            copy_value_action = menu.addAction("Copy Value")
            copy_tag_action = menu.addAction("Copy Tag Line")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == add_action:
            self.add_tag()
        elif action is not None and action == edit_action:
            self.edit_tag(item)
        elif action is not None and action == delete_action:
            self.delete_tag(item)
        elif action is not None and action == copy_value_action:
            self.copy_value(item)
        elif action is not None and action == copy_tag_action:
            self.copy_tag_line(item)

    def add_tag(self):
        """Add a new tag to the dataset."""
        if self.dataset is None:
            self._show_status("No DICOM file loaded")
            return

        dialog = AddTagDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        tag_text = dialog.get_tag_text()
        if not tag_text:
            return

        try:
            tag = resolve_tag(tag_text)
            if tag is None:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Unknown tag '{tag_text}'. Use a keyword (PatientName) "
                    "or group,element (0010,0010).",
                )
                return

            vr = dialog.get_vr()
            if not vr:
                try:
                    vr = dictionary_VR(tag)
                except KeyError:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Tag {tag} is not in the DICOM dictionary; please specify a VR.",
                    )
                    return

            if tag in self.dataset:
                QMessageBox.warning(
                    self, "Error", f"Tag {tag} already exists. Use Edit Tag to change its value."
                )
                return

            value = convert_value_for_vr(dialog.get_value(), vr)
            self.dataset.add_new(tag, vr, value)
            self._push_undo(("add", self.dataset, tag))
            self.load_metadata(self.dataset)

            self.dataset_modified.emit()
            self._show_status("Tag added successfully")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to add tag: {e!s}")

    def delete_tag(self, item):
        """Delete the selected tag from the dataset."""
        if not isinstance(item, QTreeWidgetItem):
            return

        tag_str = item.text(0)[1:-1]  # Remove parentheses
        try:
            group, element = (int(part, 16) for part in tag_str.split(","))
            tag = (group, element)

            # Show confirmation dialog
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete tag {item.text(0)} ({item.text(1)})?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Attempt to delete the tag
                self.find_and_delete_tag(self.dataset, tag)

                # Remove the item from the tree
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    index = self.tree.indexOfTopLevelItem(item)
                    self.tree.takeTopLevelItem(index)

                self.dataset_modified.emit()
                self._show_status("Tag deleted successfully")

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete tag {tag_str}: {e!s}")

    def find_and_delete_tag(self, dataset, tag):
        """Recursively find and delete a tag in the dataset or its sequences."""
        if tag in dataset:
            self._push_undo(("delete", self.dataset, dataset, dataset[tag]))
            del dataset[tag]
            return True

        # Check sequences
        for element in dataset:
            if isinstance(element.value, Sequence):
                for sub_dataset in element.value:
                    if self.find_and_delete_tag(sub_dataset, tag):
                        return True
        return False

    def _push_undo(self, entry):
        """Push an undo entry, keeping the stack bounded."""
        self.undo_stack.append(entry)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def _find_containers(self, dataset, tag, found):
        """Collect all (sub)datasets that contain the given tag."""
        if tag in dataset:
            found.append(dataset)
        for element in dataset:
            if isinstance(element.value, Sequence):
                for sub_dataset in element.value:
                    self._find_containers(sub_dataset, tag, found)

    def undo_last(self):
        """Undo the most recent add, edit, or delete of a tag."""
        if not self.undo_stack:
            self._show_status("Nothing to undo")
            return

        entry = self.undo_stack.pop()
        kind, dataset = entry[0], entry[1]
        try:
            if kind == "edit":
                for container, tag, old_value in entry[2]:
                    container[tag].value = old_value
            elif kind == "delete":
                container, element = entry[2], entry[3]
                container.add(element)
            elif kind == "add":
                tag = entry[2]
                if tag in dataset:
                    del dataset[tag]

            if dataset is self.dataset:
                self.load_metadata(dataset)
            self.dataset_modified.emit()
            self._show_status(f"Undid {kind}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to undo: {e!s}")

    def _show_status(self, message):
        """Show a temporary message in the main window status bar."""
        if hasattr(self.window(), "status_bar"):
            self.window().status_bar.showMessage(message, 3000)

    def find_and_edit_tag(self, dataset, tag, new_value, vr):
        """Recursively find and edit a tag in the dataset or its sequences."""
        if tag in dataset:
            dataset[tag].value = convert_value_for_vr(new_value, vr)

        # Check if dataset contains sequences
        for element in dataset:
            if isinstance(element.value, Sequence):
                for sub_dataset in element.value:
                    self.find_and_edit_tag(sub_dataset, tag, new_value, vr)

    def edit_tag(self, item):
        """Edit the selected tag."""
        if isinstance(item, QTreeWidgetItem):  # Ensure the item is a QTreeWidgetItem
            dialog = EditTagDialog(item, self)
            if dialog.exec() == QDialog.Accepted:
                try:
                    tag_str = item.text(0)[1:-1]
                    group, element = (int(part, 16) for part in tag_str.split(","))
                    tag = (group, element)

                    # Retrieve VR from data_element or item text
                    data_element = self.dataset.get(tag, None)
                    if data_element:
                        vr = data_element.VR if hasattr(data_element, "VR") else item.text(2)
                    else:
                        vr = item.text(2)  # Fallback VR

                    new_value = dialog.get_value()

                    # Record old values for undo before editing
                    containers = []
                    self._find_containers(self.dataset, tag, containers)
                    if containers:
                        self._push_undo(
                            (
                                "edit",
                                self.dataset,
                                [(c, tag, c[tag].value) for c in containers],
                            )
                        )

                    # Use the recursive function to find and edit the tag
                    self.find_and_edit_tag(self.dataset, tag, new_value, vr)

                    # Update the item display
                    item.setText(3, str(new_value))

                    self.dataset_modified.emit()
                    self._show_status("Tag updated successfully")

                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to update tag {tag}: {e!s}")

    def focus_search(self):
        """Focus the search input and select its content."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def filter_items(self, text):
        """Filter tree items based on search text, including sequence items."""
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            self._filter_item(self.tree.topLevelItem(i), text)

    def _filter_item(self, item, text):
        """Recursively filter an item; keep parents of matching children visible."""
        matches = any(text in item.text(j).lower() for j in range(item.columnCount()))

        child_matches = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), text):
                child_matches = True

        visible = matches or child_matches
        item.setHidden(not visible)

        # Expand parents so matching sequence items are visible
        if text and child_matches:
            item.setExpanded(True)

        return visible

    def create_sequence_tree(self, sequence_items, parent_item):
        """Create a tree structure for DICOM sequences."""
        try:
            for item in sequence_items:
                for elem in item["elements"]:
                    child = QTreeWidgetItem(parent_item)
                    tag_str = f"({elem['tag'][0]:04x},{elem['tag'][1]:04x})"
                    value_str = (
                        str(elem["value"][0])
                        if isinstance(elem["value"], tuple)
                        else str(elem["value"])
                    )

                    child.setText(0, tag_str)
                    child.setText(1, elem["name"])
                    child.setText(2, elem["vr"])
                    child.setText(3, value_str)
        except Exception as e:
            print(f"Error in create_sequence_tree: {e}")

    def clear(self):
        """Clear the metadata view."""
        self.tree.clear()
        self.dataset = None

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
