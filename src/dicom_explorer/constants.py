from PySide6.QtCore import QSize

APP_NAME = "DICOM Explorer"
ORGANIZATION = "DicomMetadataExplorer"
SETTINGS_APPLICATION = "DicomExplorer"

# Image viewer zoom, relative to "fit to window"
ZOOM_FACTOR = 1.15
ZOOM_MIN = 1.0
ZOOM_MAX = 20.0

# Images above this pixel count render a decimated preview while dragging window/level
WL_PREVIEW_THRESHOLD = 2_000_000

# Render size of thumbnails in the loader and their display size
THUMBNAIL_RENDER_SIZE = 128
THUMBNAIL_SIZE = QSize(64, 64)
THUMBNAIL_PANEL_WIDTH = 260
