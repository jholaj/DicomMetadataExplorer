"""Recently opened paths stored in the application settings."""

from pathlib import Path

from PySide6.QtCore import QSettings

LIMIT = 10
KEY = "recent_files"


class RecentFiles:
    def __init__(self, settings: QSettings):
        self.settings = settings

    def paths(self) -> list[str]:
        value = self.settings.value(KEY, [])
        return [value] if isinstance(value, str) else list(value or [])

    def add(self, path: Path) -> None:
        paths = [str(path), *(p for p in self.paths() if p != str(path))]
        self.settings.setValue(KEY, paths[:LIMIT])

    def clear(self) -> None:
        self.settings.setValue(KEY, [])
