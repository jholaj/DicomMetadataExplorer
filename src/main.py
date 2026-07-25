import sys

from PySide6.QtWidgets import QApplication

from styles.icons import app_icon
from ui.main_window import DicomExplorer


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    window = DicomExplorer()
    window.show()

    # Open files or directories passed on the command line
    if len(sys.argv) > 1:
        window.load_files(sys.argv[1:])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
