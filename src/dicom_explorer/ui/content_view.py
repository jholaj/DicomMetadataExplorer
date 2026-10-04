"""Content tab with image tools, the image, report or message, and a frame slider."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dicom_explorer.ui.image_viewer import ImageViewer
from dicom_explorer.ui.report_view import ReportView

HINT = "W/L: right drag · Measure: Shift + drag"
FRAMES_HINT = " · Frames: wheel or ↑↓, zoom: Ctrl + wheel"


class ContentView(QWidget):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.viewer = ImageViewer()
        self.report_view = ReportView()
        self.message = QLabel()
        self.message.setObjectName("content_message")
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.stack = QStackedWidget()
        for widget in (self.viewer, self.report_view, self.message):
            self.stack.addWidget(widget)

        self.hint = QLabel(HINT)
        self.hint.setObjectName("image_tools_hint")
        self.tools_bar = self._tools_bar()

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_label = QLabel("1 / 1")
        self.frame_bar = QWidget()
        frame_layout = QHBoxLayout(self.frame_bar)
        frame_layout.setContentsMargins(8, 0, 8, 4)
        frame_layout.addWidget(QLabel("Frame"))
        frame_layout.addWidget(self.frame_slider, stretch=1)
        frame_layout.addWidget(self.frame_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.tools_bar)
        layout.addWidget(self.stack)
        layout.addWidget(self.frame_bar)

        self.frame_slider.valueChanged.connect(self.viewer.set_frame)
        self.viewer.frame_changed.connect(self._on_frame_changed)
        self.viewer.decode_failed.connect(self._on_decode_failed)
        self.show_message("No DICOM file loaded")

    @property
    def showing_image(self) -> bool:
        return self.stack.currentWidget() is self.viewer and self.viewer.image_item is not None

    def set_document(self, document) -> None:
        self.document = document
        self.viewer.clear()
        if document is None:
            self.show_message("No DICOM file loaded")
        elif document.has_pixels:
            self.stack.setCurrentWidget(self.viewer)
            self.tools_bar.show()
            self.hint.setText(HINT + (FRAMES_HINT if document.frame_count > 1 else ""))
            self.viewer.show_document(document)
        elif document.is_report:
            self.report_view.load_report(document.dataset)
            self.stack.setCurrentWidget(self.report_view)
            self.tools_bar.hide()
        else:
            self.show_message("This file has no pixel data or structured report.")

    def refresh(self) -> None:
        """Show the current document again after its dataset changed."""
        if self.showing_image and self.document.has_pixels:
            self.viewer.reload()
        else:
            self.set_document(self.document)

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)
        self.tools_bar.hide()
        self.frame_bar.hide()

    def copy_view(self) -> None:
        if self.showing_image:
            QApplication.clipboard().setPixmap(self.viewer.grab())
            self.status_message.emit("View copied")

    def save_view_as_png(self) -> None:
        if not self.showing_image:
            return
        default = str(self.document.path.with_suffix(".png"))
        file_name, _ = QFileDialog.getSaveFileName(self, "Save View As PNG", default, "PNG (*.png)")
        if not file_name:
            return
        if not file_name.lower().endswith(".png"):
            file_name += ".png"
        saved = self.viewer.grab().save(file_name, "PNG")
        self.status_message.emit(f"View saved to {file_name}" if saved else "Saving failed")

    def _tools_bar(self) -> QWidget:
        viewer = self.viewer
        tools = (
            ("Fit", "Fit to window (0)", viewer.fit_to_window),
            ("1:1", "One image pixel per screen pixel (1)", viewer.zoom_actual_size),
            ("⟲", "Rotate left ([)", lambda: viewer.rotate_view(-90)),
            ("⟳", "Rotate right (])", lambda: viewer.rotate_view(90)),
            ("↔", "Flip horizontally (H)", lambda: viewer.flip_view(True)),
            ("↕", "Flip vertically (V)", lambda: viewer.flip_view(False)),
            ("Invert", "Invert the display (I)", viewer.toggle_invert),
            ("Reset W/L", "Window/level from the dataset (R)", viewer.reset_window_level),
            ("Copy", "Copy the view to the clipboard", self.copy_view),
            ("PNG", "Save the view as PNG", self.save_view_as_png),
        )
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 0)
        layout.setSpacing(4)
        for text, tooltip, callback in tools:
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch()
        layout.addWidget(self.hint)
        return bar

    def _on_decode_failed(self, error: str):
        self.show_message(f"The pixel data cannot be decoded.\n\n{error}")

    def _on_frame_changed(self, frame: int, count: int):
        self.frame_bar.setVisible(count > 1)
        if count > 1:
            self.frame_slider.blockSignals(True)
            self.frame_slider.setMaximum(count - 1)
            self.frame_slider.setValue(frame)
            self.frame_slider.blockSignals(False)
            self.frame_label.setText(f"{frame + 1} / {count}")
