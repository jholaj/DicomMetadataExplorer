import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QSizePolicy

from constants import ZOOM_FACTOR
from utils.dicom_properties import DicomImageProperties


class ImageViewer(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._configure_view_settings()

        self.image_item = None
        self.zoom_factor = ZOOM_FACTOR
        self.current_zoom = 1.0
        self.base_scale = 1.0  # Track the initial scaling factor

    def _configure_view_settings(self):
        """Configure all view-related settings."""
        # Enable antialiasing for smoother rendering
        self.setRenderHint(self.renderHints().Antialiasing)
        # Optimize viewport updates
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        # Disable scrollbars for better touch/mouse control
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Set anchor points for transformations
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Enable drag mode for panning
        self.setDragMode(QGraphicsView.ScrollHandDrag)

        # Allow the widget to expand in both directions
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def minimumSizeHint(self) -> QSize:
        """Calculate the minimum allowed size based on screen dimensions."""
        screen_size = QGuiApplication.primaryScreen().availableGeometry().size()
        return QSize(screen_size.width() // 2, screen_size.height() // 2)

    def display_image(self, dataset):
        """Display a DICOM image from the dataset."""
        try:
            if not hasattr(dataset, "pixel_array"):
                return

            dicom_props = DicomImageProperties.from_dataset(dataset)
            processed_pixels = dicom_props.get_processed_pixels()
            image = self.create_qimage(processed_pixels)
            self._setup_image_display(image)

        except Exception as e:
            print(f"Error displaying image: {e}")

    def create_qimage(self, pixel_array):
        """Create QImage from normalized pixel array."""
        if not isinstance(pixel_array, np.ndarray) or len(pixel_array.shape) != 2:
            raise ValueError("Invalid pixel array: Expected a 2D NumPy array")
        height, width = pixel_array.shape
        return QImage(pixel_array.data, width, height, width, QImage.Format_Grayscale8)

    def _setup_image_display(self, image):
        """Setup the image display with the new image."""
        pixmap = QPixmap.fromImage(image)
        self.scene.clear()
        self.image_item = self.scene.addPixmap(pixmap)

        # Reset view properties
        self.current_zoom = 1.0
        self.setTransform(self.transform().scale(1, 1))

        # Update scene and view
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.centerAndScaleImage()
        self.updateGeometry()

    def centerAndScaleImage(self):
        """Center and scale image to fit the view while maintaining aspect ratio."""
        if not self.image_item:
            return

        # Calculate the best scale factor to fit the view
        viewport_rect = self.viewport().rect()
        scene_rect = self.scene.sceneRect()

        scale = min(viewport_rect.width() / scene_rect.width(),
                   viewport_rect.height() / scene_rect.height())

        # Apply transformation
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(scene_rect.center())

        # Store the initial scale as base scale and reset current zoom
        self.base_scale = scale
        self.current_zoom = scale
        # Emit 1.0 as we're at base scale
        self.zoom_changed.emit(1.0)

    def wheelEvent(self, event):
        """Handle mouse wheel zoom events."""
        if self.image_item:
            factor = self.zoom_factor if event.angleDelta().y() > 0 else 1 / self.zoom_factor
            self.current_zoom *= factor
            self.scale(factor, factor)
            # Emit relative zoom compared to base scale
            self.zoom_changed.emit(self.current_zoom / self.base_scale)

    def resizeEvent(self, event):
        """Handle widget resize events."""
        super().resizeEvent(event)
        self.centerAndScaleImage()

    def clear(self):
        """Clear the current image from the viewer."""
        self.scene.clear()
        self.image_item = None
        self.current_zoom = 1.0
        self.base_scale = 1.0
        self.resetTransform()
