from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from constants import BACKGROUND_COLOR
from utils.dicom_utils import normalize_pixel_array

class ImageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(facecolor=BACKGROUND_COLOR)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(BACKGROUND_COLOR)
        self.ax.axis("off")

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_height = 0
        self.image_width = 0

    def display_image(self, dataset):
        self.ax.clear()
        self.ax.axis("off")

        try:
            if hasattr(dataset, "pixel_array"):
                pixel_array = normalize_pixel_array(dataset.pixel_array)
                self.image_height, self.image_width = pixel_array.shape[:2]
                self.ax.imshow(pixel_array, cmap="gray")
                self.figure.tight_layout(pad=0)
                self.canvas.draw()
        except Exception as e:
            print(f"Error displaying image: {e}")
