import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pydicom.config
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from dicom_explorer.constants import APP_NAME, ORGANIZATION, SETTINGS_APPLICATION
from dicom_explorer.styles.icons import app_icon
from dicom_explorer.styles.theme import application_palette

log = logging.getLogger("dicom_explorer")


def configure_pydicom():
    # Elements with a wrong value length are read as UN instead of failing the file
    pydicom.config.convert_wrong_length_to_UN = True
    pydicom.config.settings.reading_validation_mode = pydicom.config.WARN


def configure_logging() -> Path | None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.captureWarnings(True)
    # pydicom warns about every invalid value, the validator reports them instead
    logging.getLogger("py.warnings").setLevel(logging.ERROR)
    logging.getLogger("pydicom").setLevel(logging.ERROR)

    directory = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    if not directory:
        return None
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        log_file = Path(directory) / "dicom-explorer.log"
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        return log_file
    except OSError:
        return None


def install_exception_hook(log_file: Path | None):
    """Log unhandled exceptions and show them in a dialog."""
    showing = False

    def hook(exc_type, exc, tb):
        nonlocal showing
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        if showing or QApplication.instance() is None:
            return
        showing = True
        try:
            box = QMessageBox(
                QMessageBox.Critical, "Unexpected Error", f"{exc_type.__name__}: {exc}"
            )
            if log_file:
                box.setInformativeText(f"Details were written to {log_file}")
            box.setDetailedText("".join(traceback.format_exception(exc_type, exc, tb)))
            box.exec()
        finally:
            showing = False

    sys.excepthook = hook


def main():
    configure_pydicom()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(SETTINGS_APPLICATION)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(application_palette())
    app.setWindowIcon(app_icon())
    install_exception_hook(configure_logging())

    from dicom_explorer.ui.main_window import DicomExplorer

    window = DicomExplorer()
    window.show()
    if len(sys.argv) > 1:
        window.open_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
