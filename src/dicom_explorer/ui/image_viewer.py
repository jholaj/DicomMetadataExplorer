"""Image view with zoom, pan, rotation, window/level, frames and measurement."""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QSizePolicy,
)

from dicom_explorer.app.imaging import to_qimage
from dicom_explorer.constants import WL_PREVIEW_THRESHOLD, ZOOM_FACTOR, ZOOM_MAX, ZOOM_MIN
from dicom_explorer.core.measurement import Spacing
from dicom_explorer.core.pixels import PixelDecodeError
from dicom_explorer.core.rendering import VoiLut, Window
from dicom_explorer.styles.theme import ACCENT_COLOR, VIEWER_BACKGROUND

WHEEL_NOTCH = 120


class ImageViewer(QGraphicsView):
    zoom_changed = Signal(float)
    window_level_changed = Signal(str)
    pixel_info_changed = Signal(str)
    frame_changed = Signal(int, int)
    decode_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(QColor(VIEWER_BACKGROUND))
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._reset()

    def minimumSizeHint(self) -> QSize:
        return QSize(320, 240)

    def show_document(self, document) -> bool:
        """Show the first frame, False when the pixels cannot be decoded."""
        self.clear()
        self.document = document
        self.spacing = Spacing.of(document.dataset)
        return self._load_frame(0)

    def reload(self) -> None:
        """Render again after the dataset changed."""
        if self.image_item is not None:
            self._load_frame(self.frame_index)

    def set_frame(self, index: int) -> None:
        loaded = self.image_item is not None and index != self.frame_index
        if loaded and 0 <= index < self.document.frame_count:
            self._load_frame(index)

    def step_frame(self, delta: int) -> None:
        if self.document is not None:
            self.set_frame(max(0, min(self.frame_index + delta, self.document.frame_count - 1)))

    def reset_window_level(self) -> None:
        if self.frame is not None and not self.frame.is_color:
            self.voi = None
            self._render()

    def toggle_invert(self) -> None:
        if self.image_item is not None:
            self.user_invert = not self.user_invert
            self._render()

    def fit_to_window(self) -> None:
        if self.image_item is None:
            return
        rect = self.scene.sceneRect()
        width, height = rect.width(), rect.height()
        if self.rotation % 180 == 90:
            width, height = height, width
        viewport = self.viewport().rect()
        self.fit_mode = True
        if viewport.width() <= 0 or viewport.height() <= 0:
            return
        scale = min(viewport.width() / max(width, 1), viewport.height() / max(height, 1))
        self._apply_transform(scale)
        self.base_scale = self.current_zoom = scale
        self._update_interpolation()
        self.zoom_changed.emit(1.0)

    def zoom_actual_size(self) -> None:
        if self.image_item is not None:
            self._apply_transform(1.0)
            self.current_zoom = 1.0
            self.fit_mode = False
            self._update_interpolation()
            self.zoom_changed.emit(1.0 / self.base_scale)

    def zoom_by(self, factor: float) -> None:
        if self.image_item is None:
            return
        relative = self.current_zoom * factor / self.base_scale
        # Zooming back into the range is allowed after 1:1 left it
        if (relative > ZOOM_MAX and factor > 1) or (relative < ZOOM_MIN and factor < 1):
            return
        self.scale(factor, factor)
        self.current_zoom *= factor
        self.fit_mode = math.isclose(relative, 1.0)
        self._update_interpolation()
        self.zoom_changed.emit(relative)

    def rotate_view(self, degrees: int) -> None:
        self.rotation = (self.rotation + degrees) % 360
        self.fit_to_window()

    def flip_view(self, horizontal: bool) -> None:
        if horizontal:
            self.flip_h = not self.flip_h
        else:
            self.flip_v = not self.flip_v
        self.fit_to_window()

    def measurement_text(self) -> str:
        return self.measurement.text if self.measurement else ""

    def clear(self) -> None:
        self.scene.clear()
        self.resetTransform()
        self._reset()
        self.pixel_info_changed.emit("")
        self.window_level_changed.emit("")
        self.frame_changed.emit(0, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_to_window()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if self.image_item is None or delta == 0:
            return
        if self.document.frame_count > 1 and not event.modifiers() & Qt.ControlModifier:
            # Touchpads send fractions of a notch
            self._wheel_frames += delta
            while abs(self._wheel_frames) >= WHEEL_NOTCH:
                step = -1 if self._wheel_frames > 0 else 1
                self._wheel_frames += WHEEL_NOTCH * step
                self.step_frame(step)
        else:
            self.zoom_by(ZOOM_FACTOR ** (delta / WHEEL_NOTCH))
        event.accept()

    def mousePressEvent(self, event):
        grayscale = self.frame is not None and not self.frame.is_color
        if event.button() == Qt.RightButton and grayscale:
            window = self.voi or self.frame.default_voi
            window = window.as_window() if isinstance(window, VoiLut) else window
            self._drag_start = (event.position(), window)
        elif event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier:
            if self.image_item is not None:
                self.measurement = _Measurement(
                    self.scene, self._scene_pos(event), self.measurement
                )
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            start, window = self._drag_start
            delta = event.position() - start
            low, high = self.frame.value_range
            self.voi = window.dragged(delta.x(), delta.y(), high - low)
            self._render(preview=True)
        elif self.measurement and self.measurement.active:
            self.measurement.update(self._scene_pos(event), self.spacing)
        else:
            self._emit_pixel_info(event)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and self._drag_start is not None:
            self._drag_start = None
            self._render()
        elif event.button() == Qt.LeftButton and self.measurement and self.measurement.active:
            self.measurement.active = False
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.pixel_info_changed.emit("")
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        handler = self._key_handlers().get(event.key())
        modifiers = event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)
        if self.image_item is None or handler is None or modifiers:
            super().keyPressEvent(event)
            return
        handler()
        event.accept()

    def _reset(self):
        self.document = None
        self.frame = None
        self.frame_index = 0
        self.image_item = None
        self.voi = None
        self.user_invert = False
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.fit_mode = True
        self.current_zoom = 1.0
        self.base_scale = 1.0
        self.spacing = None
        self.measurement = None
        self._drag_start = None
        self._wheel_frames = 0

    def _load_frame(self, index: int) -> bool:
        try:
            self.frame = self.document.frame(index)
        except PixelDecodeError as e:
            self.decode_failed.emit(str(e))
            return False
        first = self.image_item is None
        self.frame_index = index
        self._render()
        if first:
            self.scene.setSceneRect(QRectF(self.image_item.pixmap().rect()))
            self.fit_to_window()
        self.frame_changed.emit(index, self.document.frame_count)
        return True

    def _render(self, preview: bool = False) -> None:
        rows, columns = self.frame.shape
        step = 1
        if preview and rows * columns > WL_PREVIEW_THRESHOLD:
            step = math.ceil(math.sqrt(rows * columns / 1_000_000))
        rendered = self.frame.render(self.voi, self.user_invert, step)
        pixmap = QPixmap.fromImage(to_qimage(rendered))
        if self.image_item is None:
            self.image_item = self.scene.addPixmap(pixmap)
        else:
            self.image_item.setPixmap(pixmap)
        self.image_item.setScale(step)
        self._update_interpolation()
        self.window_level_changed.emit(self._window_level_text())

    def _window_level_text(self) -> str:
        voi = None if self.frame.is_color else self.voi or self.frame.default_voi
        if isinstance(voi, VoiLut):
            return "VOI LUT"
        if isinstance(voi, Window):
            return f"W: {voi.width:g}  L: {voi.center:g}"
        return ""

    def _update_interpolation(self):
        # Nearest neighbour keeps single pixels visible when magnified
        if self.image_item is not None:
            magnified = self.current_zoom * self.image_item.scale() >= 1.5
            mode = Qt.FastTransformation if magnified else Qt.SmoothTransformation
            self.image_item.setTransformationMode(mode)

    def _apply_transform(self, scale: float) -> None:
        self.resetTransform()
        self.scale(-scale if self.flip_h else scale, -scale if self.flip_v else scale)
        self.rotate(self.rotation)
        self.centerOn(self.scene.sceneRect().center())

    def _scene_pos(self, event) -> QPointF:
        return self.mapToScene(event.position().toPoint())

    def _emit_pixel_info(self, event):
        if self.frame is not None:
            position = self._scene_pos(event)
            text = self.frame.describe_pixel(int(position.x()), int(position.y()))
            self.pixel_info_changed.emit(text or "")

    def _remove_measurement(self):
        if self.measurement:
            self.measurement.remove()
            self.measurement = None

    def _key_handlers(self) -> dict:
        handlers = {
            Qt.Key_Plus: lambda: self.zoom_by(ZOOM_FACTOR),
            Qt.Key_Equal: lambda: self.zoom_by(ZOOM_FACTOR),
            Qt.Key_Minus: lambda: self.zoom_by(1 / ZOOM_FACTOR),
            Qt.Key_0: self.fit_to_window,
            Qt.Key_1: self.zoom_actual_size,
            Qt.Key_R: self.reset_window_level,
            Qt.Key_I: self.toggle_invert,
            Qt.Key_BracketLeft: lambda: self.rotate_view(-90),
            Qt.Key_BracketRight: lambda: self.rotate_view(90),
            Qt.Key_H: lambda: self.flip_view(True),
            Qt.Key_V: lambda: self.flip_view(False),
            Qt.Key_Escape: self._remove_measurement,
        }
        if self.document is not None and self.document.frame_count > 1:
            # Arrow keys browse frames, single frame images keep them for panning
            handlers[Qt.Key_Up] = lambda: self.step_frame(-1)
            handlers[Qt.Key_Down] = lambda: self.step_frame(1)
            handlers[Qt.Key_Home] = lambda: self.set_frame(0)
            handlers[Qt.Key_End] = lambda: self.set_frame(self.document.frame_count - 1)
        return handlers


class _Measurement:
    """Distance line with a label that stays readable at any zoom."""

    def __init__(self, scene: QGraphicsScene, start: QPointF, previous=None):
        if previous:
            previous.remove()
        self.scene = scene
        self.start = start
        self.active = True
        pen = QPen(QColor(ACCENT_COLOR), 2)
        pen.setCosmetic(True)
        self.line = scene.addLine(start.x(), start.y(), start.x(), start.y(), pen)
        self.box = scene.addRect(0, 0, 0, 0, QPen(Qt.NoPen), QColor(0, 0, 0, 170))
        self.box.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.label = QGraphicsSimpleTextItem("", self.box)
        self.label.setBrush(QColor("#ffffff"))
        self.label.setPos(6, 3)

    @property
    def text(self) -> str:
        return self.label.text()

    def update(self, end: QPointF, spacing: Spacing | None) -> None:
        dx, dy = end.x() - self.start.x(), end.y() - self.start.y()
        self.line.setLine(self.start.x(), self.start.y(), end.x(), end.y())
        text = spacing.distance_text(dx, dy) if spacing else f"{math.hypot(dx, dy):.0f} px"
        self.label.setText(text)
        bounds = self.label.boundingRect()
        self.box.setRect(0, 0, bounds.width() + 12, bounds.height() + 6)
        self.box.setPos((self.start + end) / 2)

    def remove(self) -> None:
        self.scene.removeItem(self.line)
        self.scene.removeItem(self.box)
