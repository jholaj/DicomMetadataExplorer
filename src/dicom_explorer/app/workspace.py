"""Opened documents and the current selection."""

from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoGroup

from dicom_explorer.app.document import Document


class Workspace(QObject):
    document_added = Signal(object)
    document_removed = Signal(object)
    document_changed = Signal(object)
    document_state_changed = Signal(object)
    current_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._documents: dict[Path, Document] = {}
        self._current: Document | None = None
        self.undo_group = QUndoGroup(self)

    def __len__(self) -> int:
        return len(self._documents)

    def __iter__(self):
        return iter(self.documents())

    @property
    def current(self) -> Document | None:
        return self._current

    def documents(self) -> list[Document]:
        return list(self._documents.values())

    def get(self, path) -> Document | None:
        return self._documents.get(Path(path))

    def add(self, document: Document) -> None:
        if document.path in self._documents:
            return
        document.setParent(self)
        self._documents[document.path] = document
        self.undo_group.addStack(document.undo_stack)
        document.changed.connect(partial(self.document_changed.emit, document))
        document.state_changed.connect(partial(self._on_state_changed, document))
        self.document_added.emit(document)

    def remove(self, document: Document) -> None:
        documents = self.documents()
        if document not in documents:
            return
        if document is self._current:
            index = documents.index(document)
            others = documents[:index] + documents[index + 1 :]
            self.set_current(others[min(index, len(others) - 1)] if others else None)
        del self._documents[document.path]
        self.undo_group.removeStack(document.undo_stack)
        document.release_pixels()
        self.document_removed.emit(document)
        document.deleteLater()

    def set_current(self, document: Document | None) -> None:
        if document is self._current:
            return
        if self._current is not None:
            self._current.release_pixels()
        self._current = document
        self.undo_group.setActiveStack(document.undo_stack if document else None)
        self.current_changed.emit(document)

    def modified_documents(self) -> list[Document]:
        return [d for d in self._documents.values() if d.is_modified]

    def study_documents(self, document: Document) -> list[Document]:
        return [d for d in self._documents.values() if d.study_uid == document.study_uid]

    def _on_state_changed(self, document: Document) -> None:
        # Save As changes the path the document is indexed by
        old = next(path for path, doc in self._documents.items() if doc is document)
        if old != document.path:
            del self._documents[old]
            self._documents[document.path] = document
        self.document_state_changed.emit(document)
