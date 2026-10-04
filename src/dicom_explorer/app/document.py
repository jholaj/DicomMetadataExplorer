"""An opened DICOM file with its undo history and decoded frames."""

from collections import OrderedDict
from pathlib import Path

from pydicom.dataset import Dataset
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QUndoCommand, QUndoStack

from dicom_explorer.core.io import save_dataset
from dicom_explorer.core.pixels import decode_frame, frame_count, has_pixel_data
from dicom_explorer.core.rendering import FrameImage

SR_CLASS_PREFIX = "1.2.840.10008.5.1.4.1.1.88."
FRAME_CACHE_SIZE = 4


class Document(QObject):
    """One opened file, modified while its undo stack is not clean."""

    changed = Signal()
    state_changed = Signal()

    def __init__(
        self,
        path: Path,
        dataset: Dataset,
        thumbnail: QImage | None = None,
        thumbnail_error: str | None = None,
    ):
        super().__init__()
        self.path = Path(path)
        self.dataset = dataset
        self.thumbnail = thumbnail
        self.thumbnail_error = thumbnail_error
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(200)
        self.undo_stack.indexChanged.connect(self._on_content_changed)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._frames = OrderedDict()

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_modified(self) -> bool:
        return not self.undo_stack.isClean()

    @property
    def study_uid(self) -> str:
        return str(self.dataset.get("StudyInstanceUID", ""))

    @property
    def has_pixels(self) -> bool:
        return has_pixel_data(self.dataset)

    @property
    def frame_count(self) -> int:
        return frame_count(self.dataset)

    @property
    def is_report(self) -> bool:
        sop_class = str(self.dataset.get("SOPClassUID", ""))
        modality = str(self.dataset.get("Modality", "")).upper()
        return "ContentSequence" in self.dataset and (
            sop_class.startswith(SR_CLASS_PREFIX) or modality in ("SR", "KO") or not self.has_pixels
        )

    def frame(self, index: int = 0) -> FrameImage:
        """Decoded frame, raises PixelDecodeError."""
        if index in self._frames:
            self._frames.move_to_end(index)
            return self._frames[index]
        frame = FrameImage(self.dataset, *decode_frame(self.dataset, index))
        self._frames[index] = frame
        while len(self._frames) > FRAME_CACHE_SIZE:
            self._frames.popitem(last=False)
        return frame

    def release_pixels(self) -> None:
        self._frames.clear()

    def push(self, command: QUndoCommand) -> None:
        self.undo_stack.push(command)

    def save(self, path: Path | None = None) -> None:
        """Save in place or to a new path, which becomes the path of the document."""
        target = Path(path) if path else self.path
        save_dataset(self.dataset, target)
        self.path = target
        self.undo_stack.setClean()
        self.state_changed.emit()

    def _on_clean_changed(self, _clean: bool):
        self.state_changed.emit()

    def _on_content_changed(self, _index: int):
        # Edited attributes may change how the pixels decode or render
        self.release_pixels()
        self.changed.emit()
