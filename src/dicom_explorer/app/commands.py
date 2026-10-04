"""Undoable edits of a document dataset, addressed by element paths."""

import copy

from pydicom.datadict import keyword_for_tag
from PySide6.QtGui import QUndoCommand

from dicom_explorer.core.anonymizer import (
    AnonymizationOptions,
    AnonymizationResult,
    anonymize_dataset,
)
from dicom_explorer.core.elements import DatasetSnapshot, ElementPath, format_tag


class SetValuesCommand(QUndoCommand):
    def __init__(self, document, values: dict[ElementPath, object], text: str = ""):
        paths = list(values)
        default = (
            f"Edit {_label(paths[0].tag)}" if len(paths) == 1 else f"Edit {len(paths)} elements"
        )
        super().__init__(text or default)
        self.document = document
        self.new_values = copy.deepcopy(values)
        self.old_values = {p: copy.deepcopy(p.element(document.dataset).value) for p in paths}

    def redo(self):
        self._apply(self.new_values)

    def undo(self):
        self._apply(self.old_values)

    def _apply(self, values: dict):
        for path, value in values.items():
            path.element(self.document.dataset).value = copy.deepcopy(value)


class AddElementCommand(QUndoCommand):
    def __init__(self, document, parent: ElementPath, tag, vr: str, value):
        super().__init__(f"Add {_label(tag)}")
        self.document = document
        self.parent = parent
        self.tag = tag
        self.vr = vr
        self.value = copy.deepcopy(value)

    def redo(self):
        self.parent.dataset(self.document.dataset).add_new(
            self.tag, self.vr, copy.deepcopy(self.value)
        )

    def undo(self):
        del self.parent.dataset(self.document.dataset)[self.tag]


class DeleteElementCommand(QUndoCommand):
    def __init__(self, document, path: ElementPath):
        super().__init__(f"Delete {_label(path.tag)}")
        self.document = document
        self.path = path
        self.element = None

    def redo(self):
        self.element = self.path.element(self.document.dataset)
        del self.path.dataset(self.document.dataset)[self.path.tag]

    def undo(self):
        self.path.dataset(self.document.dataset).add(self.element)


class AnonymizeCommand(QUndoCommand):
    """Anonymization restored from snapshots, the dataset is already changed when pushed."""

    def __init__(self, document, options: AnonymizationOptions):
        super().__init__("Anonymize")
        self.document = document
        self.before = DatasetSnapshot.of(document.dataset)
        self.result: AnonymizationResult = anonymize_dataset(document.dataset, options)
        self.after = DatasetSnapshot.of(document.dataset)
        self._pushed = False

    def redo(self):
        if self._pushed:
            self.after.restore(self.document.dataset)
        self._pushed = True

    def undo(self):
        self.before.restore(self.document.dataset)


def _label(tag) -> str:
    return keyword_for_tag(tag) or format_tag(tag)
