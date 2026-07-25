import math
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
)

from constants import ZOOM_FACTOR, ZOOM_MAX, ZOOM_MIN
from styles.theme import ACCENT_COLOR
from utils.dicom_properties import DicomImageProperties, frame_count


class ImageViewer(QGraphicsView):
    """Widget for displaying and manipulating DICOM images.

    Supports zooming, panning, window/level adjustment,
    and automatic size adjustment.
    """

    zoom_changed = Signal(float)
    window_level_changed = Signal(float, float)  # center, width
    pixel_info_changed = Signal(str)  # formatted pixel position/value, "" to clear
    frame_changed = Signal(int, int)  # current frame (0-based), frame count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.image_item = None
        self.dicom_props = None
        self.pixel_spacing = None  # (row spacing, column spacing) in mm

        # Multi-frame state
        self._dataset = None
        self._frame = 0
        self.frame_count = 1

        # Orientation state ([, ] rotate; H/V flip)
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False

        # Window/level drag state
        self._wl_dragging = False
        self._wl_start_pos = None
        self._wl_start_values = None
        self._wl_defaults = None
        self._wl_preview_array = None
        self._wl_preview_step = 1

        # Grayscale inversion toggle
        self._inverted = False

        # Distance measurement (Shift + left drag)
        self._measuring = False
        self._measure_start = None
        self._measure_line = None
        self._measure_label = None

        # Initialize zoom variables and UI components
        self._init_zoom_variables()
        self._init_ui()

    def _init_zoom_variables(self):
        """Initialize zoom-related variables."""
        self.zoom_factor = ZOOM_FACTOR
        self.min_zoom = ZOOM_MIN
        self.max_zoom = ZOOM_MAX
        self.current_zoom = 1.0
        self.base_scale = 1.0

    def _init_ui(self):
        """Initialize UI components and their settings."""
        self.setScene(self.scene)
        self._configure_view_settings()
        self._configure_scroll_settings()
        self._configure_size_policy()

    def _configure_view_settings(self):
        """Configure rendering and transformation settings."""
        self.setBackgroundBrush(QColor("#101214"))
        self.setRenderHint(self.renderHints().Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def _configure_scroll_settings(self):
        """Configure scrollbar settings."""
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _configure_size_policy(self):
        """Configure size policy rules."""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def minimumSizeHint(self) -> QSize:
        """Keep a modest minimum so the window stays freely resizable."""
        return QSize(320, 240)

    def display_image(self, dataset):
        """Display a DICOM image from the given dataset.

        Args:
            dataset: DICOM dataset containing pixel_array

        """
        if not self._validate_dataset(dataset):
            return

        try:
            self._dataset = dataset
            self._frame = 0
            self.frame_count = frame_count(dataset)
            self._rotation = 0
            self._flip_h = False
            self._flip_v = False
            self._inverted = False

            image = self._process_dicom_image(dataset)
            self._setup_image_display(image)
            self.window_level_changed.emit(
                self.dicom_props.window_center, self.dicom_props.window_width
            )
            self.frame_changed.emit(self._frame, self.frame_count)
        except Exception as e:
            print(f"Error displaying image: {e}")

    def set_frame(self, frame):
        """Switch to another frame of a multi-frame file, keeping the view state."""
        if (
            self._dataset is None
            or not self.image_item
            or not 0 <= frame < self.frame_count
            or frame == self._frame
        ):
            return

        try:
            center, width = self.dicom_props.window_center, self.dicom_props.window_width
            self._frame = frame
            self.dicom_props = DicomImageProperties.from_dataset(self._dataset, frame=frame)
            self.dicom_props.window_center = center
            self.dicom_props.window_width = width
            self.dicom_props.invert = self._inverted
            self._build_wl_preview()

            image = self.create_qimage(self.dicom_props.get_processed_pixels())
            self.image_item.setPixmap(QPixmap.fromImage(image))
            self.image_item.setScale(1)
            self.frame_changed.emit(self._frame, self.frame_count)
        except Exception as e:
            print(f"Error switching frame: {e}")

    def _validate_dataset(self, dataset):
        """Validate DICOM dataset."""
        return hasattr(dataset, "pixel_array")

    # Above this pixel count, window/level dragging renders a decimated
    # preview and the full resolution is restored on mouse release
    WL_PREVIEW_THRESHOLD = 2_000_000

    def _process_dicom_image(self, dataset):
        """Process DICOM dataset into QImage."""
        self.dicom_props = DicomImageProperties.from_dataset(dataset, frame=self._frame)
        self._ensure_window_defaults()
        self._read_pixel_spacing(dataset)
        self._build_wl_preview()
        processed_pixels = self.dicom_props.get_processed_pixels()
        return self.create_qimage(processed_pixels)

    def _build_wl_preview(self):
        """Prepare a decimated pixel array for fluid window/level dragging."""
        pixels = self.dicom_props.pixel_array
        if pixels.size > self.WL_PREVIEW_THRESHOLD:
            step = int(np.ceil(np.sqrt(pixels.size / 1_000_000)))
            self._wl_preview_array = np.ascontiguousarray(pixels[::step, ::step])
            self._wl_preview_step = step
        else:
            self._wl_preview_array = None
            self._wl_preview_step = 1

    def _read_pixel_spacing(self, dataset):
        """Read pixel spacing (mm) from the dataset if available."""
        spacing = getattr(dataset, "PixelSpacing", None)
        if spacing is None:
            spacing = getattr(dataset, "ImagerPixelSpacing", None)
        try:
            self.pixel_spacing = (float(spacing[0]), float(spacing[1]))
        except (TypeError, ValueError, IndexError):
            self.pixel_spacing = None

    def _ensure_window_defaults(self):
        """Fill in window center/width from pixel data when the dataset lacks them."""
        props = self.dicom_props
        if props.window_center is None or props.window_width is None:
            pixels = props.pixel_array * props.rescale_slope + props.rescale_intercept
            low, high = float(pixels.min()), float(pixels.max())
            props.window_center = (low + high) / 2
            props.window_width = max(high - low, 1.0)
        self._wl_defaults = (props.window_center, props.window_width)

    @staticmethod
    def create_qimage(pixel_array):
        """Create QImage from normalized pixel array.

        This method is used both internally and by other classes to convert
        numpy arrays to QImage objects.

        Args:
            pixel_array: 2D numpy array with pixel values

        Returns:
            QImage: Created QImage object

        Raises:
            ValueError: If pixel_array is not a 2D numpy array

        """
        if not isinstance(pixel_array, np.ndarray):
            raise ValueError("Invalid pixel array: Expected a NumPy array")

        pixel_array = np.ascontiguousarray(pixel_array)

        if pixel_array.ndim == 2:
            height, width = pixel_array.shape
            image = QImage(pixel_array.data, width, height, width, QImage.Format_Grayscale8)
        elif pixel_array.ndim == 3 and pixel_array.shape[2] == 3:
            height, width, _ = pixel_array.shape
            image = QImage(pixel_array.data, width, height, width * 3, QImage.Format_RGB888)
        else:
            raise ValueError(
                "Invalid pixel array: Expected a 2D grayscale or (rows, columns, 3) RGB array"
            )

        # QImage does not own the buffer; keep the array alive as long as
        # the image exists so the data is not freed under it
        image._numpy_ref = pixel_array
        return image

    def _setup_image_display(self, image):
        """Set up display of new image."""
        pixmap = QPixmap.fromImage(image)
        self._clear_and_set_image(pixmap)
        self._reset_view_state()
        self._update_scene_and_view(pixmap)

    def _clear_and_set_image(self, pixmap):
        """Clear scene and set new image."""
        self.scene.clear()
        self._measure_line = None
        self._measure_label = None
        self._measuring = False
        self.image_item = self.scene.addPixmap(pixmap)

    def _reset_view_state(self):
        """Reset view state to default values."""
        self.current_zoom = 1.0

    def _update_scene_and_view(self, pixmap):
        """Update scene and view."""
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.centerAndScaleImage()
        self.updateGeometry()

    def centerAndScaleImage(self):
        """Center and scale image to fit the view."""
        if not self.image_item:
            return

        scale = self._calculate_fit_scale()
        self._apply_center_and_scale(scale)
        self._update_zoom_state(scale)

    def _calculate_fit_scale(self):
        """Calculate scale factor to fit view, honoring the current rotation."""
        viewport_rect = self.viewport().rect()
        scene_rect = self.scene.sceneRect()
        scene_w, scene_h = scene_rect.width(), scene_rect.height()
        if self._rotation % 180 == 90:
            scene_w, scene_h = scene_h, scene_w
        return min(viewport_rect.width() / scene_w, viewport_rect.height() / scene_h)

    def _apply_center_and_scale(self, scale):
        """Apply centering, scaling, rotation, and flips."""
        self.resetTransform()
        self.scale(-scale if self._flip_h else scale, -scale if self._flip_v else scale)
        self.rotate(self._rotation)
        self.centerOn(self.scene.sceneRect().center())

    def rotate_view(self, degrees):
        """Rotate the view by a multiple of 90 degrees and refit."""
        self._rotation = (self._rotation + degrees) % 360
        self.centerAndScaleImage()

    def flip_view(self, horizontal):
        """Mirror the view horizontally or vertically and refit."""
        if horizontal:
            self._flip_h = not self._flip_h
        else:
            self._flip_v = not self._flip_v
        self.centerAndScaleImage()

    def zoom_actual_size(self):
        """Show the image at 100% (one image pixel per screen pixel)."""
        if not self.image_item:
            return
        self._apply_center_and_scale(1.0)
        self.current_zoom = 1.0
        self.zoom_changed.emit(1.0 / self.base_scale)

    def toggle_invert(self):
        """Invert the rendering of the image (grayscale or color)."""
        if not self.dicom_props or not self.image_item:
            return
        self._inverted = not self._inverted
        self.dicom_props.invert = self._inverted
        image = self.create_qimage(self.dicom_props.get_processed_pixels())
        self.image_item.setPixmap(QPixmap.fromImage(image))
        self.image_item.setScale(1)

    def _update_zoom_state(self, scale):
        """Update zoom state."""
        self.base_scale = scale
        self.current_zoom = scale
        self.zoom_changed.emit(1.0)

    def mousePressEvent(self, event):
        """Start window/level (right button) or measurement (Shift + left button)."""
        if event.button() == Qt.RightButton and self.image_item and self.dicom_props:
            self._wl_dragging = True
            self._wl_start_pos = event.position()
            self._wl_start_values = (
                self.dicom_props.window_center,
                self.dicom_props.window_width,
            )
            event.accept()
            return

        if (
            event.button() == Qt.LeftButton
            and event.modifiers() & Qt.ShiftModifier
            and self.image_item
        ):
            self._start_measurement(self.mapToScene(event.position().toPoint()))
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle window/level dragging, measurement, and the pixel probe."""
        if self._wl_dragging:
            delta = event.position() - self._wl_start_pos
            center, width = self._wl_start_values
            step = max(abs(width), 1.0) / 300
            new_width = max(1.0, width + delta.x() * step)
            new_center = center - delta.y() * step
            self.set_window_level(new_center, new_width, preview=True)
            event.accept()
            return

        if self._measuring:
            self._update_measurement(self.mapToScene(event.position().toPoint()))
            event.accept()
            return

        self._emit_pixel_info(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finish window/level adjustment or measurement."""
        if event.button() == Qt.RightButton and self._wl_dragging:
            self._wl_dragging = False
            # Restore full resolution after the preview-quality drag
            if self._wl_preview_array is not None:
                self.set_window_level(
                    self.dicom_props.window_center,
                    self.dicom_props.window_width,
                )
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._measuring:
            self._measuring = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _start_measurement(self, scene_pos):
        """Begin a new distance measurement, replacing any existing one."""
        self._remove_measurement()
        self._measuring = True
        self._measure_start = scene_pos

        pen = QPen(QColor(ACCENT_COLOR), 2)
        pen.setCosmetic(True)
        self._measure_line = self.scene.addLine(
            scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y(), pen
        )
        self._measure_label = self.scene.addSimpleText("")
        self._measure_label.setBrush(QColor("#ffffff"))
        self._measure_label.setFlag(QGraphicsItem.ItemIgnoresTransformations)

    def _update_measurement(self, scene_pos):
        """Update the measurement line and its distance label."""
        start = self._measure_start
        self._measure_line.setLine(start.x(), start.y(), scene_pos.x(), scene_pos.y())

        dx = scene_pos.x() - start.x()
        dy = scene_pos.y() - start.y()
        pixels = math.hypot(dx, dy)
        if self.pixel_spacing:
            row_spacing, col_spacing = self.pixel_spacing
            mm = math.hypot(dx * col_spacing, dy * row_spacing)
            text = f"{mm:.1f} mm ({pixels:.0f} px)"
        else:
            text = f"{pixels:.0f} px"

        self._measure_label.setText(text)
        mid_x = (start.x() + scene_pos.x()) / 2
        mid_y = (start.y() + scene_pos.y()) / 2
        self._measure_label.setPos(mid_x, mid_y)

    def _remove_measurement(self):
        """Remove the measurement overlay from the scene."""
        for item in (self._measure_line, self._measure_label):
            if item is not None:
                self.scene.removeItem(item)
        self._measure_line = None
        self._measure_label = None
        self._measuring = False

    def _emit_pixel_info(self, view_pos):
        """Emit position and value of the pixel under the cursor."""
        if not self.image_item or self.dicom_props is None:
            return

        scene_pos = self.mapToScene(view_pos.toPoint())
        x, y = int(scene_pos.x()), int(scene_pos.y())
        pixels = self.dicom_props.pixel_array
        if 0 <= y < pixels.shape[0] and 0 <= x < pixels.shape[1]:
            if self.dicom_props.is_color:
                r, g, b = (int(v) for v in pixels[y, x][:3])
                self.pixel_info_changed.emit(f"({x}, {y})  RGB: {r}, {g}, {b}")
            else:
                value = (
                    float(pixels[y, x]) * self.dicom_props.rescale_slope
                    + self.dicom_props.rescale_intercept
                )
                self.pixel_info_changed.emit(f"({x}, {y})  value: {value:g}")
        else:
            self.pixel_info_changed.emit("")

    def set_window_level(self, center, width, preview=False):
        """Apply new window center/width and re-render the image.

        With preview=True (used while dragging) a decimated copy of large
        images is rendered instead, keeping the drag fluid.
        """
        if not self.dicom_props or not self.image_item:
            return

        self.dicom_props.window_center = center
        self.dicom_props.window_width = width

        if preview and self._wl_preview_array is not None:
            preview_props = replace(self.dicom_props, pixel_array=self._wl_preview_array)
            image = self.create_qimage(preview_props.get_processed_pixels())
            self.image_item.setPixmap(QPixmap.fromImage(image))
            self.image_item.setScale(self._wl_preview_step)
        else:
            processed_pixels = self.dicom_props.get_processed_pixels()
            image = self.create_qimage(processed_pixels)
            self.image_item.setPixmap(QPixmap.fromImage(image))
            self.image_item.setScale(1)

        self.window_level_changed.emit(center, width)

    def reset_window_level(self):
        """Reset window center/width to the values from the dataset."""
        if self._wl_defaults:
            self.set_window_level(*self._wl_defaults)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for zoom and window/level."""
        if not self.image_item:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self._zoom_by_key(self.zoom_factor)
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):
            self._zoom_by_key(1 / self.zoom_factor)
        elif key == Qt.Key_0:
            self.centerAndScaleImage()
        elif key == Qt.Key_1:
            self.zoom_actual_size()
        elif key == Qt.Key_R:
            self.reset_window_level()
        elif key == Qt.Key_I:
            self.toggle_invert()
        elif key == Qt.Key_BracketLeft:
            self.rotate_view(-90)
        elif key == Qt.Key_BracketRight:
            self.rotate_view(90)
        elif key == Qt.Key_H:
            self.flip_view(horizontal=True)
        elif key == Qt.Key_V:
            self.flip_view(horizontal=False)
        elif key == Qt.Key_Escape:
            self._remove_measurement()
        else:
            super().keyPressEvent(event)

    def _zoom_by_key(self, factor):
        """Zoom by a factor while respecting zoom limits."""
        potential_zoom = self.current_zoom * factor
        if self._is_zoom_in_limits(potential_zoom):
            self._apply_zoom(potential_zoom)

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming.

        Args:
            event: Qt wheel event
        """
        if not self.image_item:
            return

        zoom_factor = self._calculate_zoom_factor(event)
        if self._is_zoom_in_limits(zoom_factor):
            self._apply_zoom(zoom_factor)

    def _calculate_zoom_factor(self, event):
        """Calculate zoom factor based on wheel event."""
        factor = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
        return self.current_zoom * factor

    def _is_zoom_in_limits(self, potential_zoom):
        """Check if potential zoom is within allowed limits."""
        relative_zoom = potential_zoom / self.base_scale
        return self.min_zoom <= relative_zoom <= self.max_zoom

    def _apply_zoom(self, new_zoom):
        """Apply new zoom."""
        factor = new_zoom / self.current_zoom
        self.current_zoom = new_zoom
        self.scale(factor, factor)
        self.zoom_changed.emit(self.current_zoom / self.base_scale)

    def resizeEvent(self, event):
        """Handle widget resize events."""
        super().resizeEvent(event)
        self.centerAndScaleImage()

    def clear(self):
        """Clear current image from viewer."""
        self.scene.clear()
        self.image_item = None
        self.dicom_props = None
        self.pixel_spacing = None
        self._dataset = None
        self._frame = 0
        self.frame_count = 1
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False
        self._inverted = False
        self._wl_defaults = None
        self._wl_dragging = False
        self._wl_preview_array = None
        self._wl_preview_step = 1
        self._measure_line = None
        self._measure_label = None
        self._measuring = False
        self.current_zoom = 1.0
        self.base_scale = 1.0
        self.resetTransform()
        self.pixel_info_changed.emit("")
        self.frame_changed.emit(0, 1)
