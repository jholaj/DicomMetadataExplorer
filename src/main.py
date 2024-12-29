import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import DicomExplorer

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DicomExplorer()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
