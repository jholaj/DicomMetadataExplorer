"""Conversion of rendered arrays to QImage, usable from worker threads."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def to_qimage(pixels: np.ndarray) -> QImage:
    """QImage owning a copy of a uint8 (rows, columns) or (rows, columns, 3) array."""
    pixels = np.ascontiguousarray(pixels, dtype=np.uint8)
    height, width = pixels.shape[:2]
    if pixels.ndim == 2:
        image = QImage(pixels.data, width, height, width, QImage.Format_Grayscale8)
    elif pixels.shape[2] == 3:
        image = QImage(pixels.data, width, height, width * 3, QImage.Format_RGB888)
    else:
        raise ValueError(f"Unsupported pixel array shape {pixels.shape}")
    return image.copy()


def thumbnail_image(pixels: np.ndarray, size: int) -> QImage:
    return to_qimage(pixels).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
