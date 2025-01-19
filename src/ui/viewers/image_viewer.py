import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QSizePolicy

from constants import ZOOM_FACTOR, ZOOM_MAX, ZOOM_MIN
from utils.dicom_properties import DicomImageProperties


class ImageViewer(QGraphicsView):
    """Widget for displaying and manipulating DICOM images.

    Supports zooming, panning, and automatic size adjustment.
    """

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.image_item = None

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
        """Calculate minimum allowed size based on screen dimensions."""
        screen_size = QGuiApplication.primaryScreen().availableGeometry().size()
        return QSize(screen_size.width() // 2, screen_size.height() // 2)

    def display_image(self, dataset):
        """Display a DICOM image from the given dataset.

        Args:
            dataset: DICOM dataset containing pixel_array

        """
        if not self._validate_dataset(dataset):
            return

        try:
            image = self._process_dicom_image(dataset)
            self._setup_image_display(image)
        except Exception as e:
            print(f"Error displaying image: {e}")

    def _validate_dataset(self, dataset):
        """Validate DICOM dataset."""
        return hasattr(dataset, "pixel_array")

    def _process_dicom_image(self, dataset):
        """Process DICOM dataset into QImage."""
        dicom_props = DicomImageProperties.from_dataset(dataset)
        processed_pixels = dicom_props.get_processed_pixels()
        return self.create_qimage(processed_pixels)

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
        if not isinstance(pixel_array, np.ndarray) or len(pixel_array.shape) != 2:
            raise ValueError("Invalid pixel array: Expected a 2D NumPy array")

        height, width = pixel_array.shape
        return QImage(pixel_array.data, width, height, width, QImage.Format_Grayscale8)

    def _setup_image_display(self, image):
        """Set up display of new image."""
        pixmap = QPixmap.fromImage(image)
        self._clear_and_set_image(pixmap)
        self._reset_view_state()
        self._update_scene_and_view(pixmap)

    def _clear_and_set_image(self, pixmap):
        """Clear scene and set new image."""
        self.scene.clear()
        self.image_item = self.scene.addPixmap(pixmap)

    def _reset_view_state(self):
        """Reset view state to default values."""
        self.current_zoom = 1.0
        self.setTransform(self.transform().scale(1, 1))

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
        """Calculate scale factor to fit view."""
        viewport_rect = self.viewport().rect()
        scene_rect = self.scene.sceneRect()
        return min(viewport_rect.width() / scene_rect.width(),
                  viewport_rect.height() / scene_rect.height())

    def _apply_center_and_scale(self, scale):
        """Apply centering and scaling."""
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(self.scene.sceneRect().center())

    def _update_zoom_state(self, scale):
        """Update zoom state."""
        self.base_scale = scale
        self.current_zoom = scale
        self.zoom_changed.emit(1.0)

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
        self.current_zoom = 1.0
        self.base_scale = 1.0
        self.resetTransform()
