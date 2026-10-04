"""Reading, writing, and locating DICOM files."""

import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset

# Skipped inside scanned folders, files opened directly are always read
SKIPPED_NAMES = frozenset({"DICOMDIR", "Thumbs.db", ".DS_Store"})


@dataclass(frozen=True)
class OpenRequest:
    """Paths given by the user mapped to the files found under them."""

    sources: dict[Path, tuple[Path, ...]]

    @classmethod
    def expand(cls, paths) -> "OpenRequest":
        sources = {}
        for raw in paths:
            path = normalize_path(raw)
            if path.is_dir():
                found = (p for p in sorted(path.rglob("*")) if p.is_file())
                sources[path] = tuple(p for p in found if not _skipped(p.relative_to(path)))
            else:
                sources[path] = (path,)
        return cls(sources)

    @property
    def files(self) -> list[Path]:
        return list(dict.fromkeys(f for files in self.sources.values() for f in files))

    @property
    def explicit(self) -> set[Path]:
        """Files the user opened directly, not found in a folder."""
        return {path for path, files in self.sources.items() if files == (path,)}

    def sources_of(self, loaded) -> list[Path]:
        """Given paths that produced at least one loaded file."""
        loaded = set(loaded)
        return [path for path, files in self.sources.items() if loaded.intersection(files)]


def read_dataset(path: str | Path) -> Dataset:
    return pydicom.dcmread(str(path))


def save_dataset(dataset: Dataset, path: str | Path) -> None:
    """Write through a temporary file so a failed save leaves the target intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    try:
        try:
            dataset.save_as(temp_name, enforce_file_format=True)
        except (AttributeError, KeyError, ValueError):
            # Too little information for a conformant file meta header
            dataset.save_as(temp_name)
        if path.exists():
            shutil.copymode(path, temp_name)
        else:
            os.chmod(temp_name, 0o666 & ~_umask())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def plan_copy_targets(sources: list[Path], target_dir: Path) -> dict[Path, Path]:
    """Target paths for copies, repeated file names keep their folder structure."""
    if len({s.name for s in sources}) == len(sources):
        return {s: target_dir / s.name for s in sources}
    try:
        common = Path(os.path.commonpath([s.parent for s in sources]))
        return {s: target_dir / s.relative_to(common) for s in sources}
    except ValueError:
        # Sources on different drives
        used = Counter()
        targets = {}
        for source in sources:
            used[source.name] += 1
            count = used[source.name]
            name = source.name if count == 1 else f"{source.stem}_{count}{source.suffix}"
            targets[source] = target_dir / name
        return targets


def _skipped(relative: Path) -> bool:
    return relative.name in SKIPPED_NAMES or any(part.startswith(".") for part in relative.parts)


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current
