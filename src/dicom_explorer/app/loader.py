"""Background loading of files with their thumbnails."""

import contextlib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from dicom_explorer.app.imaging import thumbnail_image
from dicom_explorer.constants import THUMBNAIL_RENDER_SIZE
from dicom_explorer.core.io import OpenRequest, read_dataset
from dicom_explorer.core.pixels import PixelDecodeError, decode_frame, has_pixel_data
from dicom_explorer.core.rendering import FrameImage

log = logging.getLogger(__name__)
CANCELLED = "cancelled"


@dataclass
class LoadResult:
    path: Path
    dataset: Dataset | None = None
    thumbnail: QImage | None = None
    thumbnail_error: str | None = None
    error: str | None = None


@dataclass
class LoadSummary:
    request: OpenRequest
    loaded: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


def load_file(path: Path) -> LoadResult:
    """Read one file and render its thumbnail."""
    try:
        dataset = read_dataset(path)
    except InvalidDicomError:
        return LoadResult(path, error="not a DICOM file")
    except Exception as e:
        log.debug("Failed to read %s", path, exc_info=True)
        return LoadResult(path, error=str(e) or type(e).__name__)

    result = LoadResult(path, dataset)
    if has_pixel_data(dataset):
        try:
            frame = FrameImage(dataset, *decode_frame(dataset))
            result.thumbnail = thumbnail_image(frame.render(), THUMBNAIL_RENDER_SIZE)
        except PixelDecodeError as e:
            result.thumbnail_error = str(e)
        except Exception as e:
            log.warning("Thumbnail failed for %s", path, exc_info=True)
            result.thumbnail_error = str(e) or type(e).__name__
    return result


class LoadJob(QObject):
    """Loads the files of a request in the global thread pool."""

    progress = Signal()
    result_ready = Signal(object)
    finished = Signal(object)

    def __init__(self, request: OpenRequest, files: list[Path], parent=None):
        super().__init__(parent)
        self.files = files
        self.done = 0
        self.summary = LoadSummary(request)
        self._cancelled = threading.Event()
        self._signals = _Signals(self)
        self._signals.result.connect(self._on_result)

    def start(self) -> None:
        for path in self.files:
            QThreadPool.globalInstance().start(_LoadTask(path, self._signals, self._cancelled))

    def cancel(self) -> None:
        self._cancelled.set()

    def _on_result(self, result: LoadResult):
        self.done += 1
        if result.dataset is not None:
            self.summary.loaded.append(result.path)
            self.result_ready.emit(result)
        elif result.error != CANCELLED:
            self.summary.failed.append((result.path, result.error or "unknown error"))
        self.progress.emit()
        if self.done == len(self.files):
            self.summary.cancelled = self._cancelled.is_set()
            self.finished.emit(self.summary)


class _Signals(QObject):
    result = Signal(object)


class _LoadTask(QRunnable):
    def __init__(self, path: Path, signals: _Signals, cancelled: threading.Event):
        super().__init__()
        self.path = path
        self.signals = signals
        self.cancelled = cancelled

    def run(self):
        cancelled = self.cancelled.is_set()
        result = LoadResult(self.path, error=CANCELLED) if cancelled else load_file(self.path)
        # The job may be destroyed while the task runs
        with contextlib.suppress(RuntimeError):
            self.signals.result.emit(result)
