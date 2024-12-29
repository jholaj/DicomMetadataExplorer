import sys
import pydicom
import numpy as np
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QDialog,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QFormLayout,
    QFileDialog,
    QDialogButtonBox,
    QLineEdit,
    QHeaderView,
    QMenu,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QStatusBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from pathlib import Path
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Constants for UI
BACKGROUND_COLOR = "#232323"
TEXT_COLOR = "#ffffff"
BUTTON_COLOR = "#0078d4"
BUTTON_HOVER_COLOR = "#106ebe"


class ImageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create matplotlib figure
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
                pixel_array = dataset.pixel_array
                self.image_height, self.image_width = pixel_array.shape[:2]

                # Normalize pixel values for display
                if pixel_array.dtype != np.uint8:
                    pixel_array = (
                        (pixel_array - pixel_array.min())
                        / (pixel_array.max() - pixel_array.min())
                        * 255
                    ).astype(np.uint8)

                # Display image
                self.ax.imshow(pixel_array, cmap="gray")
                self.figure.tight_layout(pad=0)
                self.canvas.draw()
        except Exception as e:
            print(f"Error displaying image: {e}")

class EditTagDialog(QDialog):
    def __init__(self, tag_item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit DICOM Tag")
        self.tag_item = tag_item

        layout = QFormLayout(self)

        # Create input fields
        self.value_edit = QLineEdit(tag_item.text(3))

        # Add fields to layout
        layout.addRow("Tag:", QLabel(tag_item.text(0)))
        layout.addRow("Name:", QLabel(tag_item.text(1)))
        layout.addRow("VR:", QLabel(tag_item.text(2)))
        layout.addRow("Value:", self.value_edit)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        # Apply styles
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BACKGROUND_COLOR};
                color: {TEXT_COLOR};
            }}
            QLabel {{
                color: {TEXT_COLOR};
            }}
            QLineEdit {{
                padding: 6px;
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: {TEXT_COLOR};
            }}
        """)

    def get_value(self):
        return self.value_edit.text()

class MetadataViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = None

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        layout.addWidget(self.search_input)

        # Tree widget for DICOM tags
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Set resize mode for columns
        header = self.tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)

        self.search_input.textChanged.connect(self.filter_items)

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item:
            menu = QMenu()
            edit_action = menu.addAction("Edit Tag")
            action = menu.exec(self.tree.viewport().mapToGlobal(position))

            if action == edit_action:
                self.edit_tag(item)

    def edit_tag(self, item):
        if not self.dataset:
            return
        dialog = EditTagDialog(item, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                # Get tag from the item text (format: "(group,element)")
                tag_str = item.text(0)[1:-1]  # Remove parentheses
                group, element = map(lambda x: int(x, 16), tag_str.split(','))
                tag = (group, element)

                # Update the tag value in the dataset
                data_element = self.dataset[tag]
                new_value = dialog.get_value()

                # Convert the string value to the appropriate type based on VR
                vr = item.text(2)
                if vr in ['DS', 'FL', 'FD']:
                    data_element.value = float(new_value)
                elif vr in ['IS', 'SL', 'SS', 'UL', 'US']:
                    data_element.value = int(new_value)
                else:
                    data_element.value = new_value

                # Update the display
                item.setText(3, str(data_element.value))

                # Show success message in status bar
                if hasattr(self.window(), 'status_bar'):
                    self.window().status_bar.showMessage("Tag updated successfully", 3000)

            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to update tag: {str(e)}")

    def filter_items(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower() for j in range(item.columnCount())
            )
            item.setHidden(not matches)

    def load_metadata(self, dataset):
        self.tree.clear()
        self.dataset = dataset

        for elem in dataset:
            if elem.tag.group != 0x7FE0:  # Skip pixel data
                item = QTreeWidgetItem()
                tag_str = f"({elem.tag.group:04x},{elem.tag.element:04x})"
                value_str = (
                    "<binary data>"
                    if isinstance(elem.value, bytes)
                    else f"<sequence of {len(elem.value)} items>"
                    if isinstance(elem.value, pydicom.sequence.Sequence)
                    else str(elem.value)
                )

                item.setText(0, tag_str)
                item.setText(1, elem.name or "")
                item.setText(2, getattr(elem, "VR", ""))
                item.setText(3, value_str)
                self.tree.addTopLevelItem(item)


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.dataset = None

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # Add actions
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.browse_file)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        layout.addWidget(self.file_path)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create metadata tab
        self.metadata_viewer = MetadataViewer()
        self.tab_widget.addTab(self.metadata_viewer, "Metadata")

        # Create image tab
        self.image_viewer = ImageViewer()
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.addWidget(self.image_viewer, alignment=Qt.AlignCenter)
        self.tab_widget.addTab(image_container, "Content")

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Set application styles
        self.apply_styles()

    def save_file(self):
        if not self.dataset:
            self.status_bar.showMessage("No DICOM file loaded")
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )

        if file_name:
            try:
                self.dataset.save_as(file_name)
                self.status_bar.showMessage(f"File saved successfully to {file_name}", 3000)
            except Exception as e:
                self.status_bar.showMessage(f"Error saving file: {str(e)}")
                QMessageBox.warning(self, "Error", f"Failed to save file: {str(e)}")

    def apply_styles(self):
        style_sheet = f"""
            QMainWindow, QWidget {{
                background-color: {BACKGROUND_COLOR};
                color: {TEXT_COLOR};
            }}
            QTreeWidget {{
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #2d2d2d;
            }}
            QTreeWidget::item {{
                padding: 4px;
                color: {TEXT_COLOR};
            }}
            QTreeWidget::item:alternate {{
                background-color: #333333;
            }}
            QLineEdit {{
                padding: 6px;
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: {TEXT_COLOR};
            }}
            QPushButton {{
                padding: 6px 12px;
                background-color: {BUTTON_COLOR};
                color: {TEXT_COLOR};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER_COLOR};
            }}
            QTabWidget::pane {{
                border: 1px solid #444444;
                background: {BACKGROUND_COLOR};
            }}
            QTabBar::tab {{
                background: #2d2d2d;
                color: {TEXT_COLOR};
                padding: 8px 12px;
                border: 1px solid #444444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {BACKGROUND_COLOR};
            }}
            QToolBar {{
                background: #2d2d2d;
                border: none;
                spacing: 3px;
                padding: 3px;
            }}
            QStatusBar {{
                background: #2d2d2d;
                color: {TEXT_COLOR};
            }}
        """
        self.setStyleSheet(style_sheet)

    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)",
        )
        if file_name:
            self.load_dicom(file_name)

    def load_dicom(self, file_path):
        try:
            self.dataset = pydicom.dcmread(file_path)
            if not self.dataset:
                raise ValueError("No data found in DICOM file.")


            self.file_path.setText(file_path)

            # Load metadata
            self.metadata_viewer.load_metadata(self.dataset)

            # Display image
            if hasattr(self.dataset, "pixel_array"):
                self.image_viewer.display_image(self.dataset)

            # Update status bar
            self.status_bar.showMessage(
                f"Loaded {self.metadata_viewer.tree.topLevelItemCount()} DICOM tags"
            )

        except Exception as e:
            self.status_bar.showMessage(f"Error loading file: {str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DicomExplorer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
