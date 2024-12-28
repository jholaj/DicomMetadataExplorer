import sys
import pydicom
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem,
                              QFileDialog, QLineEdit, QStyle, QHeaderView)
from pathlib import Path

class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Metadata Explorer")
        self.setMinimumSize(1000, 600)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Top bar with file selection
        top_bar = QHBoxLayout()

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        top_bar.addWidget(self.file_path)

        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        top_bar.addWidget(browse_btn)

        layout.addLayout(top_bar)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag name or value...")
        self.search_input.textChanged.connect(self.filter_items)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Tree widget for DICOM tags
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #232323;
            }
            QTreeWidget {
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QPushButton {
                padding: 6px 12px;
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)

    def browse_file(self):
        """Open file dialog and load DICOM file"""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select DICOM file",
            str(Path.home()),
            "DICOM files (*.dcm);;All files (*.*)"
        )

        if file_name:
            self.file_path.setText(file_name)
            self.load_dicom(file_name)

    def load_dicom(self, file_path):
        """Load and display DICOM metadata"""
        try:
            self.statusBar().showMessage("Loading DICOM file...")
            dataset = pydicom.dcmread(file_path)
            self.tree.clear()

            # Add metadata to tree
            for elem in dataset:
                if elem.tag.group != 0x7FE0:  # Skip pixel data
                    item = QTreeWidgetItem()
                    tag = f"({elem.tag.group:04x},{elem.tag.element:04x})"

                    # Convert value to string, handle special cases
                    if isinstance(elem.value, bytes):
                        value = "<binary data>"
                    elif isinstance(elem.value, pydicom.sequence.Sequence):
                        value = f"<sequence of {len(elem.value)} items>"
                    else:
                        value = str(elem.value)

                    item.setText(0, tag)
                    item.setText(1, elem.name)
                    item.setText(2, elem.VR if hasattr(elem, 'VR') else "")
                    item.setText(3, value)

                    self.tree.addTopLevelItem(item)

            self.statusBar().showMessage(f"Loaded {self.tree.topLevelItemCount()} DICOM tags")

        except Exception as e:
            self.statusBar().showMessage(f"Error loading file: {str(e)}")

    def filter_items(self, text):
        """Filter tree items based on search text"""
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            matches = any(
                text in item.text(j).lower()
                for j in range(item.columnCount())
            )
            item.setHidden(not matches)

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = DicomExplorer()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
