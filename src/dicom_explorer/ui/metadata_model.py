"""Tree model of a dataset where every row knows its element path."""

import contextlib
from dataclasses import dataclass, field
from enum import Enum

from pydicom.datadict import dictionary_VM
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont

from dicom_explorer.core.elements import (
    ElementPath,
    display_text,
    element_name,
    element_vr,
    format_tag,
    is_editable,
    value_multiplicity,
    value_text,
)
from dicom_explorer.styles.theme import ACCENT_COLOR, TEXT_MUTED_COLOR

COLUMNS = ("Tag", "Name", "VR", "Value")
TAG, NAME, VR, VALUE = range(4)
PATH_ROLE = Qt.UserRole + 1
NO_INDEX = QModelIndex()


class Kind(Enum):
    GROUP = "group"
    ELEMENT = "element"
    ITEM = "item"


@dataclass(eq=False)
class Node:
    kind: Kind
    path: ElementPath
    texts: tuple[str, str, str, str] = ("", "", "", "")
    read_only: bool = False
    editable: bool = False
    private: bool = False
    tooltip: str = ""
    search_text: str = ""
    parent: "Node | None" = None
    row: int = 0
    children: list["Node"] = field(default_factory=list)

    def add(self, child: "Node") -> "Node":
        child.parent = self
        child.row = len(self.children)
        self.children.append(child)
        return child

    @property
    def target_dataset(self) -> ElementPath:
        """Dataset a new element is added to when this node is selected."""
        if self.read_only:
            return ElementPath()
        return self.path if self.kind is Kind.ITEM else self.path.parent


class DatasetModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = Node(Kind.GROUP, ElementPath())
        self._nodes: dict[ElementPath, Node] = {}
        self._muted = QColor(TEXT_MUTED_COLOR)
        self._accent = QColor(ACCENT_COLOR)
        self._italic = QFont()
        self._italic.setItalic(True)

    def set_dataset(self, dataset: Dataset | None) -> None:
        self.beginResetModel()
        self._root = Node(Kind.GROUP, ElementPath())
        self._nodes = {}
        if dataset is not None:
            file_meta = getattr(dataset, "file_meta", None)
            if file_meta:
                texts = ("(0002,xxxx)", "File Meta Information", "", "")
                group = Node(Kind.GROUP, ElementPath(meta=True), texts, read_only=True)
                self._register(self._root.add(group))
                self._add_elements(group, file_meta)
            self._add_elements(self._root, dataset)
        self.endResetModel()

    def node(self, index: QModelIndex) -> Node:
        return index.internalPointer() if index.isValid() else self._root

    def index_for(self, path: ElementPath) -> QModelIndex:
        node = self._nodes.get(path)
        return self.createIndex(node.row, 0, node) if node else QModelIndex()

    def element_count(self) -> int:
        return sum(1 for node in self._nodes.values() if node.kind is Kind.ELEMENT)

    def index(self, row, column, parent=NO_INDEX):
        children = self.node(parent).children
        return (
            self.createIndex(row, column, children[row]) if 0 <= row < len(children) else NO_INDEX
        )

    def parent(self, index=NO_INDEX):
        if not index.isValid():
            return QModelIndex()
        parent = index.internalPointer().parent
        if parent is None or parent is self._root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def rowCount(self, parent=NO_INDEX):
        return 0 if parent.column() > 0 else len(self.node(parent).children)

    def columnCount(self, parent=NO_INDEX):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == Qt.DisplayRole:
            return node.texts[index.column()]
        if role == Qt.ToolTipRole and node.kind is Kind.ELEMENT and index.column() in (NAME, VALUE):
            return node.tooltip
        if role == PATH_ROLE:
            return node.path
        if role == Qt.ForegroundRole:
            if node.kind is Kind.ITEM:
                return self._accent
            if node.read_only or node.private or node.kind is Kind.GROUP:
                return self._muted
        if role == Qt.FontRole and (node.kind is Kind.ITEM or node.private):
            return self._italic
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable if index.isValid() else Qt.NoItemFlags

    def _register(self, node: Node) -> Node:
        self._nodes[node.path] = node
        return node

    def _add_elements(self, parent: Node, dataset: Dataset):
        for element in dataset:
            tag = element.tag
            texts = (
                format_tag(tag),
                element_name(element),
                element_vr(element),
                display_text(element),
            )
            node = self._register(
                parent.add(
                    Node(
                        Kind.ELEMENT,
                        parent.path.child(tag),
                        texts,
                        read_only=parent.read_only,
                        editable=not parent.read_only and is_editable(element),
                        private=tag.is_private,
                        tooltip=_tooltip(element),
                        search_text=_search_text(element, texts),
                    )
                )
            )
            if isinstance(element.value, Sequence):
                for index, item in enumerate(element.value):
                    texts = ("", f"Item {index + 1}", "", "")
                    item_node = Node(Kind.ITEM, node.path.child(index), texts, parent.read_only)
                    self._register(node.add(item_node))
                    self._add_elements(item_node, item)


class DatasetFilterProxy(QSortFilterProxyModel):
    """Search over tag, keyword, name, VR and value, matching sequences show all children."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
        self.setRecursiveFilteringEnabled(True)
        self.setAutoAcceptChildRows(True)

    @property
    def searching(self) -> bool:
        return bool(self._needle)

    def set_search(self, text: str) -> None:
        self._needle = text.strip().lower().replace("(", "").replace(")", "")
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._needle:
            return True
        model = self.sourceModel()
        return self._needle in model.node(model.index(source_row, 0, source_parent)).search_text


def _tooltip(element) -> str:
    vm = f"VR {element_vr(element)}, VM {value_multiplicity(element)}"
    with contextlib.suppress(KeyError):
        vm += f" (dictionary VM {dictionary_VM(element.tag)})"
    lines = [element.keyword or element_name(element), vm]
    text = value_text(element)
    if len(text) > 60:
        lines.append(text[:2000] + ("…" if len(text) > 2000 else ""))
    return "\n".join(lines)


def _search_text(element, texts) -> str:
    tag = element.tag
    text = " ".join((*texts, element.keyword or "", f"{tag.group:04x}{tag.element:04x}"))
    return text.lower().replace("(", "").replace(")", "")
