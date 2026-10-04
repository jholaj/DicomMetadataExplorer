"""Metadata tab with a searchable element tree edited through undo commands."""

from PySide6.QtCore import QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from dicom_explorer.app.commands import AddElementCommand, DeleteElementCommand, SetValuesCommand
from dicom_explorer.core.elements import ElementPath, value_text
from dicom_explorer.styles.icons import add_icon
from dicom_explorer.ui.dialogs import AddElementDialog, EditValueDialog
from dicom_explorer.ui.metadata_model import (
    NAME,
    PATH_ROLE,
    TAG,
    VALUE,
    VR,
    DatasetFilterProxy,
    DatasetModel,
    Kind,
    Node,
)


class MetadataView(QWidget):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tag, keyword, name or value (Ctrl+F)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search)

        self.add_button = QPushButton(add_icon(), "Add Tag")
        self.add_button.setIconSize(QSize(14, 14))
        self.add_button.setToolTip("Add to the dataset or to the selected sequence item (Ctrl+T)")
        self.add_button.clicked.connect(self.add_element)

        self.model = DatasetModel(self)
        self.proxy = DatasetFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self.edit_element)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.resizeSection(TAG, 150)
        header.resizeSection(NAME, 300)
        header.resizeSection(VR, 56)

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_input, stretch=1)
        top_row.addWidget(self.add_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.tree)

        self.copy_value_action = self._action("Copy Value", self.copy_value, QKeySequence.Copy)
        self.copy_line_action = self._action("Copy Tag Line", self.copy_line, "Ctrl+Shift+C")
        self.copy_path_action = self._action("Copy Path", self.copy_path)
        self.expand_action = self._action("Expand All", self.tree.expandAll)
        self.collapse_action = self._action("Collapse All", self.tree.collapseAll)
        self._action("Edit Value", self.edit_element, "F2")
        self._action("Edit Value", self.edit_element, Qt.Key_Return)
        self._action("Delete", self.delete_element, QKeySequence.Delete)

    def set_document(self, document) -> None:
        self.document = document
        self.model.set_dataset(document.dataset if document else None)
        self._expand_for_search()
        self.add_button.setEnabled(document is not None)

    def refresh(self) -> None:
        """Rebuild after an edit, keeping expansion, selection and scroll position."""
        expanded = self._expanded_paths(QModelIndex())
        current = self._current_node()
        scroll = self.tree.verticalScrollBar().value()
        self.model.set_dataset(self.document.dataset if self.document else None)
        if self.proxy.searching:
            self.tree.expandAll()
        for path in expanded:
            self.tree.expand(self._proxy_index(path))
        if current is not None:
            self.select(current.path, scroll=False)
        self.tree.verticalScrollBar().setValue(scroll)

    def element_count(self) -> int:
        return self.model.element_count()

    def select(self, path: ElementPath, scroll: bool = True) -> bool:
        """Select the row of an element path, False when the element is gone."""
        index = self._proxy_index(path)
        if not index.isValid() and self.proxy.searching:
            self.search_input.clear()
            index = self._proxy_index(path)
        if not index.isValid():
            return False
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        self.tree.setCurrentIndex(index)
        if scroll:
            self.tree.scrollTo(index, QAbstractItemView.PositionAtCenter)
        return True

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def add_element(self) -> None:
        if self.document is None:
            return
        node = self._current_node()
        parent = node.target_dataset if node else ElementPath()
        try:
            existing = parent.dataset(self.document.dataset).keys()
        except (KeyError, IndexError):
            parent, existing = ElementPath(), self.document.dataset.keys()
        target = parent.keywords() if parent.parts else "Dataset (top level)"
        dialog = AddElementDialog(target, existing, self)
        if dialog.exec() != AddElementDialog.Accepted:
            return
        command = AddElementCommand(self.document, parent, dialog.tag, dialog.vr, dialog.value)
        self.document.push(command)
        self.select(parent.child(dialog.tag))
        self.status_message.emit(command.text())

    def edit_element(self) -> None:
        node = self._current_node()
        if node is None or node.kind is not Kind.ELEMENT:
            return
        if not node.editable:
            reason = "read-only" if node.read_only else "binary, sequence or pixel data"
            self.status_message.emit(f"{node.texts[NAME]} cannot be edited ({reason})")
            return
        dialog = EditValueDialog(node.path.element(self.document.dataset), self)
        if dialog.exec() == EditValueDialog.Accepted and not dialog.unchanged:
            self.document.push(SetValuesCommand(self.document, {node.path: dialog.value}))
            self.status_message.emit(f"Updated {node.path.keywords()}")

    def delete_element(self) -> None:
        node = self._current_node()
        if node is None or node.kind is not Kind.ELEMENT or node.read_only:
            return
        reply = QMessageBox.question(
            self,
            "Delete Element",
            f"Delete {node.path.keywords()} {node.texts[TAG]}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.document.push(DeleteElementCommand(self.document, node.path))
            self.status_message.emit(f"Deleted {node.path.keywords()}")

    def copy_value(self) -> None:
        node = self._current_node()
        if node is None:
            return
        element = node.path.element(self.document.dataset) if node.kind is Kind.ELEMENT else None
        QApplication.clipboard().setText(value_text(element) if element else node.texts[VALUE])
        self.status_message.emit("Value copied")

    def copy_line(self) -> None:
        node = self._current_node()
        if node is not None:
            QApplication.clipboard().setText("\t".join(node.texts))
            self.status_message.emit("Tag line copied")

    def copy_path(self) -> None:
        node = self._current_node()
        if node is not None and node.kind is not Kind.GROUP:
            QApplication.clipboard().setText(node.path.keywords())
            self.status_message.emit("Path copied")

    def _action(self, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.WidgetShortcut)
        action.triggered.connect(slot)
        self.tree.addAction(action)
        return action

    def _show_context_menu(self, position):
        if self.document is None:
            return
        node = self._current_node()
        menu = QMenu(self)
        item = node is not None and node.kind is Kind.ITEM
        menu.addAction("Add Tag to Item..." if item else "Add Tag...", self.add_element)
        if node is not None and node.kind is Kind.ELEMENT:
            menu.addAction("Edit Value...", self.edit_element).setEnabled(node.editable)
            menu.addAction("Delete", self.delete_element).setEnabled(not node.read_only)
            menu.addSeparator()
            menu.addActions([self.copy_value_action, self.copy_line_action, self.copy_path_action])
        menu.addSeparator()
        menu.addActions([self.expand_action, self.collapse_action])
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _proxy_index(self, path: ElementPath) -> QModelIndex:
        return self.proxy.mapFromSource(self.model.index_for(path))

    def _current_node(self) -> Node | None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return None
        return self.model.node(self.proxy.mapToSource(index.siblingAtColumn(0)))

    def _expanded_paths(self, parent: QModelIndex) -> list[ElementPath]:
        paths = []
        for row in range(self.proxy.rowCount(parent)):
            index = self.proxy.index(row, 0, parent)
            if self.tree.isExpanded(index):
                paths.append(index.data(PATH_ROLE))
                paths.extend(self._expanded_paths(index))
        return paths

    def _on_search(self, text: str):
        current = self._current_node()
        self.proxy.set_search(text)
        self._expand_for_search()
        if current is not None and not text:
            self.select(current.path)

    def _expand_for_search(self):
        if self.proxy.searching:
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
