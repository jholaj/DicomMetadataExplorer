"""Left panel with the loaded files grouped by study."""

import bisect
from contextlib import contextmanager

from PySide6.QtCore import QModelIndex, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from dicom_explorer.constants import THUMBNAIL_SIZE
from dicom_explorer.core.elements import format_date
from dicom_explorer.styles.icons import placeholder_thumbnail
from dicom_explorer.ui.text import plural

DOCUMENT_ROLE = Qt.UserRole + 1
STUDY_ROLE = Qt.UserRole + 2
SORT_ROLE = Qt.UserRole + 3


class ThumbnailPanel(QWidget):
    close_requested = Signal(object)
    close_study_requested = Signal(object)
    edit_study_requested = Signal(object)

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._document_items = {}
        self._study_items = {}
        self._updating = False

        self.model = QStandardItemModel(self)
        self.tree = QTreeView()
        self.tree.setObjectName("thumbnail_tree")
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(THUMBNAIL_SIZE)
        self.tree.setIndentation(12)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        workspace.document_added.connect(self._add)
        workspace.document_removed.connect(self._remove)
        workspace.document_changed.connect(self._on_document_changed)
        workspace.document_state_changed.connect(self._update_item)
        workspace.current_changed.connect(self.select)

    def select(self, document) -> None:
        item = self._document_items.get(document)
        with self._quiet():
            if item is None:
                self.tree.clearSelection()
                self.tree.selectionModel().clearCurrentIndex()
            else:
                self.tree.setCurrentIndex(item.index())
                self.tree.scrollTo(item.index())

    def select_relative(self, step: int) -> None:
        """Select the previous or next file across all studies."""
        documents = [
            study.child(row).data(DOCUMENT_ROLE)
            for study in self._study_items_in_order()
            for row in range(study.rowCount())
        ]
        if documents:
            current = self.workspace.current
            index = documents.index(current) if current in documents else -1
            self.workspace.set_current(documents[max(0, min(index + step, len(documents) - 1))])

    @contextmanager
    def _quiet(self):
        # Row moves change the current index without the user selecting anything
        self._updating = True
        try:
            yield
        finally:
            self._updating = False

    def _add(self, document):
        with self._quiet():
            self._insert(document)
        self.select(self.workspace.current)

    def _remove(self, document):
        with self._quiet():
            self._take(document)
        self.select(self.workspace.current)

    def _on_document_changed(self, document):
        item = self._document_items.get(document)
        if item is None:
            return
        if item.parent().data(STUDY_ROLE) != document.study_uid:
            with self._quiet():
                self._take(document)
                self._insert(document)
            self.select(self.workspace.current)
        else:
            item.setData(_sort_key(document), SORT_ROLE)
            self._update_item(document)
            _update_study_label(item.parent())

    def _on_current_changed(self, current: QModelIndex, _previous):
        document = current.data(DOCUMENT_ROLE) if current.isValid() else None
        if not self._updating and document is not None:
            self.workspace.set_current(document)

    def _insert(self, document):
        study = self._study_item(document.study_uid)
        item = QStandardItem()
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setData(document, DOCUMENT_ROLE)
        item.setData(_sort_key(document), SORT_ROLE)
        item.setIcon(_icon(document))
        self._document_items[document] = item
        _insert_sorted(study, item)
        self._update_item(document)
        _update_study_label(study)
        self.tree.expand(study.index())

    def _take(self, document):
        item = self._document_items.pop(document)
        study = item.parent()
        study.removeRow(item.row())
        if study.rowCount():
            _update_study_label(study)
        else:
            del self._study_items[study.data(STUDY_ROLE)]
            self.model.invisibleRootItem().removeRow(study.row())

    def _study_item(self, study_uid: str) -> QStandardItem:
        if study_uid not in self._study_items:
            item = QStandardItem()
            item.setFlags(Qt.ItemIsEnabled)
            item.setData(study_uid, STUDY_ROLE)
            item.setData(study_uid, SORT_ROLE)
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            self._study_items[study_uid] = item
            _insert_sorted(self.model.invisibleRootItem(), item)
        return self._study_items[study_uid]

    def _study_items_in_order(self) -> list[QStandardItem]:
        root = self.model.invisibleRootItem()
        return [root.child(row) for row in range(root.rowCount())]

    def _update_item(self, document):
        item = self._document_items.get(document)
        if item is None:
            return
        ds = document.dataset
        details = [str(ds.get("Modality", ""))]
        if ds.get("InstanceNumber") not in (None, ""):
            details.append(f"#{ds.InstanceNumber}")
        if document.frame_count > 1:
            details.append(f"{document.frame_count} frames")
        marker = " *" if document.is_modified else ""
        item.setText(f"{document.name}{marker}\n{' · '.join(d for d in details if d)}")
        font = QFont()
        font.setItalic(document.is_modified)
        item.setFont(font)

        lines = [str(document.path)]
        lines += [f"{k}: {ds.get(k)}" for k in ("SeriesDescription", "PatientName") if ds.get(k)]
        if document.thumbnail_error:
            lines.append(f"Preview unavailable: {document.thumbnail_error}")
        item.setToolTip("\n".join(lines))

    def _show_menu(self, position):
        index = self.tree.indexAt(position)
        document = index.data(DOCUMENT_ROLE)
        menu = QMenu(self)
        if document is None:
            study = self._study_items.get(index.data(STUDY_ROLE))
            if study is None:
                return
            first = study.child(0).data(DOCUMENT_ROLE)
            menu.addAction("Edit Study Tags...", lambda: self.edit_study_requested.emit(first))
            menu.addAction("Close Study", lambda: self.close_study_requested.emit(first))
        else:
            folder = QUrl.fromLocalFile(str(document.path.parent))
            path = str(document.path)
            menu.addAction("Edit Study Tags...", lambda: self.edit_study_requested.emit(document))
            menu.addSeparator()
            menu.addAction("Close File", lambda: self.close_requested.emit(document))
            menu.addAction("Close Study", lambda: self.close_study_requested.emit(document))
            menu.addSeparator()
            menu.addAction("Copy Path", lambda: QApplication.clipboard().setText(path))
            menu.addAction("Show in Folder", lambda: QDesktopServices.openUrl(folder))
        menu.exec(self.tree.viewport().mapToGlobal(position))


def _sort_key(document) -> tuple:
    try:
        return (0, int(document.dataset.get("InstanceNumber")), document.name)
    except (TypeError, ValueError):
        return (1, 0, document.name)


def _insert_sorted(parent: QStandardItem, item: QStandardItem) -> None:
    keys = [parent.child(row).data(SORT_ROLE) for row in range(parent.rowCount())]
    parent.insertRow(bisect.bisect(keys, item.data(SORT_ROLE)), item)


def _update_study_label(study: QStandardItem) -> None:
    ds = study.child(0).data(DOCUMENT_ROLE).dataset
    description = str(ds.get("StudyDescription", ""))
    date = format_date(ds.get("StudyDate", ""))
    title = description or date or "Unknown study"
    details = [date] if description and date else []
    details.append(plural(study.rowCount(), "file"))
    study.setText(f"{title}\n{' · '.join(details)}")
    study.setToolTip(f"{description}\nDate: {date or '-'}\nStudy UID: {study.data(STUDY_ROLE)}")


def _icon(document) -> QIcon:
    if document.thumbnail is not None:
        return QIcon(QPixmap.fromImage(document.thumbnail))
    if document.thumbnail_error:
        return placeholder_thumbnail("ERR", warning=True)
    return placeholder_thumbnail("SR" if document.is_report else "—")
