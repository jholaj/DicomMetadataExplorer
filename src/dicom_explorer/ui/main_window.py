"""Main window composing the views, actions and file operations."""

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dicom_explorer.app.commands import AnonymizeCommand, SetValuesCommand
from dicom_explorer.app.document import Document
from dicom_explorer.app.loader import LoadJob, LoadResult, LoadSummary
from dicom_explorer.app.recent_files import RecentFiles
from dicom_explorer.app.workspace import Workspace
from dicom_explorer.constants import (
    APP_NAME,
    ORGANIZATION,
    SETTINGS_APPLICATION,
    THUMBNAIL_PANEL_WIDTH,
)
from dicom_explorer.core.elements import ElementPath
from dicom_explorer.core.io import OpenRequest, normalize_path, plan_copy_targets
from dicom_explorer.core.validation import validate_workspace
from dicom_explorer.styles import icons
from dicom_explorer.styles.theme import get_application_style
from dicom_explorer.ui.content_view import ContentView
from dicom_explorer.ui.dialogs import (
    AnonymizeDialog,
    CompareDialog,
    StudyTagsDialog,
    ValidationReportDialog,
)
from dicom_explorer.ui.file_dialogs import FileDialogs
from dicom_explorer.ui.metadata_view import MetadataView
from dicom_explorer.ui.overview_view import OverviewView
from dicom_explorer.ui.text import plural
from dicom_explorer.ui.thumbnails import ThumbnailPanel

log = logging.getLogger(__name__)

SHORTCUTS = (
    ("Ctrl+O, Ctrl+Shift+O", "Open files, open folder"),
    ("Ctrl+S, Ctrl+Shift+S, Ctrl+Alt+S", "Save, save as, save all"),
    ("Ctrl+E", "Export metadata"),
    ("Ctrl+W", "Close file"),
    ("Alt+↑, Alt+↓", "Previous, next file"),
    ("Ctrl+F, Ctrl+T", "Search tags, add tag"),
    ("Enter or F2, Delete", "Edit, delete element"),
    ("Ctrl+Z, Ctrl+Shift+Z", "Undo, redo"),
    ("Right drag, R", "Window/level, reset"),
    ("Shift + drag, Esc", "Measure, remove measurement"),
    ("Wheel, 0, 1", "Zoom, fit, actual size"),
    ("Wheel or ↑↓ in multi-frame", "Previous, next frame"),
    ("[ ], H V, I", "Rotate, flip, invert"),
)


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORGANIZATION, SETTINGS_APPLICATION)
        self.recent_files = RecentFiles(self.settings)
        self.workspace = Workspace(self)
        self.file_dialogs = FileDialogs(self, self.settings)
        self._jobs: list[LoadJob] = []
        self._report_dialog = None
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._connect_signals()
        self._show_document(None)
        self._apply_default_geometry()

    def open_paths(self, paths) -> None:
        """Open files and folders, folders are scanned recursively."""
        request = OpenRequest.expand(paths)
        files = request.files
        new_files = [path for path in files if self.workspace.get(path) is None]
        if not new_files:
            if files:
                self.workspace.set_current(self.workspace.get(files[0]))
            self._flash(f"{files[0].name} is already open" if files else "No files found")
            return
        job = LoadJob(request, new_files, self)
        job.result_ready.connect(self._on_loaded)
        job.progress.connect(self._update_progress)
        job.finished.connect(self._on_job_finished)
        self._jobs.append(job)
        self._update_progress()
        job.start()

    def close_document(self, document: Document) -> None:
        if self._confirm_discard([document]):
            self.workspace.remove(document)

    def close_study(self, document: Document) -> None:
        documents = self.workspace.study_documents(document)
        if self._confirm_discard(documents):
            for doc in documents:
                self.workspace.remove(doc)

    def close_all(self) -> None:
        documents = self.workspace.documents()
        if self._confirm_discard(documents):
            for doc in documents:
                self.workspace.remove(doc)

    def edit_study(self, document: Document) -> None:
        """Edit values shared by all files of the study of the document."""
        documents = self.workspace.study_documents(document)
        dialog = StudyTagsDialog(documents, self)
        if dialog.exec() != StudyTagsDialog.Accepted or not dialog.changes:
            return
        values = {ElementPath.top(tag): value for tag, value in dialog.changes.items()}
        for doc in documents:
            doc.push(SetValuesCommand(doc, values, f"Edit {plural(len(values), 'study tag')}"))
        changed = f"{plural(len(values), 'tag')} in {plural(len(documents), 'file')}"
        self._flash(f"Updated {changed}, Ctrl+Z undoes per file")

    def save_current(self) -> None:
        document = self.workspace.current
        if document is not None and self._save([document]):
            self._flash(f"Saved {document.path}")

    def save_current_as(self) -> None:
        document = self.workspace.current
        target = self.file_dialogs.save_as(document) if document else None
        if target is None:
            return
        target = normalize_path(target)
        if self.workspace.get(target) not in (None, document):
            self.show_error("Save As", f"{target.name} is open as another file.")
            return
        if self._save([document], target):
            self._flash(f"Saved as {target}")

    def save_all(self) -> None:
        modified = self.workspace.modified_documents()
        if not modified:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Save All")
        box.setText(f"Save {plural(len(modified), 'modified file')}?")
        box.setInformativeText("Saved copies replace the open files in the workspace.")
        overwrite = box.addButton("Overwrite Originals", QMessageBox.AcceptRole)
        to_folder = box.addButton("Save Copies To Folder...", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is overwrite:
            if self._save(modified):
                self._flash(f"Saved {plural(len(modified), 'file')}")
        elif box.clickedButton() is to_folder:
            self._save_copies(modified)

    def export_metadata(self) -> None:
        document = self.workspace.current
        choice = self.file_dialogs.export(document) if document else None
        if choice is None:
            return
        path, fmt = choice
        try:
            fmt.write(document.dataset, path)
        except OSError as e:
            self.show_error("Export Failed", f"Could not write {path.name}.", str(e))
            return
        self._flash(f"Metadata exported to {path}")

    def anonymize(self) -> None:
        current = self.workspace.current
        if current is None:
            return
        study = self.workspace.study_documents(current)
        dialog = AnonymizeDialog(current, study, self.workspace.documents(), self)
        if dialog.exec() != AnonymizeDialog.Accepted:
            return
        warnings, failures = set(), []
        for document in dialog.targets():
            try:
                command = AnonymizeCommand(document, dialog.options())
            except Exception as e:
                log.exception("Anonymization of %s failed", document.path)
                failures.append(f"{document.name}: {e}")
                continue
            document.push(command)
            warnings.update(command.result.warnings)
        done = len(dialog.targets()) - len(failures)
        self._flash(f"Anonymized {plural(done, 'file')}, save to write the changes")
        if warnings or failures:
            text = "\n".join(sorted(warnings)) or f"{len(failures)} files failed."
            self.show_error("Anonymization", text, "\n".join(failures))

    def compare_files(self) -> None:
        if len(self.workspace) >= 2:
            CompareDialog(self.workspace.documents(), self.workspace.current, self).exec()

    def validate_all(self) -> None:
        if self._report_dialog is not None:
            self._report_dialog.close()
        dialog = ValidationReportDialog(self.workspace.documents(), self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.document_requested.connect(self._open_overview)
        dialog.destroyed.connect(self._on_report_closed)
        self._report_dialog = dialog
        dialog.show()

    def show_error(self, title: str, message: str, details: str = "") -> None:
        self.statusBar().showMessage(message.splitlines()[0], 8000)
        box = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.Ok, self)
        if details:
            box.setDetailedText(details)
        box.exec()

    def closeEvent(self, event):
        if self._confirm_discard(self.workspace.documents(), verb="quit"):
            for job in self._jobs:
                job.cancel()
            event.accept()
        else:
            event.ignore()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.open_paths(paths)

    def _build_ui(self):
        self.thumbnails = ThumbnailPanel(self.workspace)
        self.thumbnails.setMinimumWidth(180)
        self.thumbnails.setMaximumWidth(520)
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setPlaceholderText("Open DICOM files or drop files and folders here")
        self.metadata_view = MetadataView()
        self.content_view = ContentView()
        self.overview_view = OverviewView()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.metadata_view, "Metadata")
        self.tabs.addTab(self.content_view, "Content")
        self.tabs.addTab(self.overview_view, "Overview")

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.path_field)
        right_layout.addWidget(self.tabs)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.thumbnails)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([THUMBNAIL_PANEL_WIDTH, 1000])
        central = QWidget()
        QHBoxLayout(central).addWidget(splitter)
        self.setCentralWidget(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.cancel_button = QToolButton()
        self.cancel_button.setText("Cancel")
        self.cancel_button.clicked.connect(self._cancel_loading)
        self.pixel_label, self.wl_label, self.zoom_label = QLabel(), QLabel(), QLabel()
        status = self.statusBar()
        for widget in (self.progress, self.cancel_button, *self._image_labels()):
            status.addPermanentWidget(widget)
            widget.hide()
        self.setStyleSheet(get_application_style())

    def _build_actions(self):
        self.open_action = self._action(
            "Open...", self._browse_files, QKeySequence.Open, icons.open_icon()
        )
        self.open_folder_action = self._action(
            "Open Folder...", self._browse_folder, "Ctrl+Shift+O"
        )
        self.save_action = self._action(
            "Save", self.save_current, QKeySequence.Save, icons.save_icon()
        )
        self.save_as_action = self._action("Save As...", self.save_current_as, QKeySequence.SaveAs)
        self.save_all_action = self._action(
            "Save All...", self.save_all, "Ctrl+Alt+S", icons.save_all_icon()
        )
        self.export_action = self._action(
            "Export Metadata...", self.export_metadata, "Ctrl+E", icons.export_icon()
        )
        self.close_action = self._action("Close File", self._close_current, QKeySequence.Close)
        self.close_all_action = self._action("Close All", self.close_all)
        self.quit_action = self._action("Quit", self.close, QKeySequence.Quit)
        self.undo_action = self.workspace.undo_group.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.workspace.undo_group.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.find_action = self._action("Find Tag", self._find_tag, QKeySequence.Find)
        self.add_tag_action = self._action("Add Tag...", self._add_tag, "Ctrl+T")
        self.tab_actions = [
            self._action(tab, lambda _=False, i=i: self.tabs.setCurrentIndex(i), f"Ctrl+{i + 1}")
            for i, tab in enumerate(("Metadata", "Content", "Overview"))
        ]
        self.previous_action = self._action(
            "Previous File", lambda: self.thumbnails.select_relative(-1), "Alt+Up"
        )
        self.next_action = self._action(
            "Next File", lambda: self.thumbnails.select_relative(1), "Alt+Down"
        )
        self.anonymize_action = self._action(
            "Anonymize...", self.anonymize, icon=icons.anonymize_icon()
        )
        self.compare_action = self._action(
            "Compare...", self.compare_files, icon=icons.compare_icon()
        )
        self.validate_action = self._action(
            "Validate All...", self.validate_all, icon=icons.validate_icon()
        )
        self.shortcuts_action = self._action("Keyboard Shortcuts", self._show_shortcuts, "F1")

    def _action(self, text, slot, shortcut=None, icon=None) -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(icon)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{text.rstrip('.')} ({action.shortcut().toString()})")
        action.triggered.connect(slot)
        return action

    def _build_menus(self):
        menus = self.menuBar()
        file_menu = menus.addMenu("&File")
        file_menu.addActions([self.open_action, self.open_folder_action])
        self.recent_menu = file_menu.addMenu("Open Recent")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addActions(
            [self.save_action, self.save_as_action, self.save_all_action, self.export_action]
        )
        file_menu.addSeparator()
        file_menu.addActions([self.close_action, self.close_all_action, self.quit_action])
        edit_menu = menus.addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.find_action, self.add_tag_action])
        view_menu = menus.addMenu("&View")
        view_menu.addActions([*self.tab_actions, self.previous_action, self.next_action])
        tools = [self.anonymize_action, self.compare_action, self.validate_action]
        menus.addMenu("&Tools").addActions(tools)
        menus.addMenu("&Help").addAction(self.shortcuts_action)

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.addActions([self.open_action, self.save_action, self.save_all_action])
        toolbar.addSeparator()
        toolbar.addActions([self.export_action, *tools])
        self.addToolBar(toolbar)

    def _connect_signals(self):
        self.workspace.current_changed.connect(self._show_document)
        self.workspace.document_changed.connect(self._on_document_changed)
        self.workspace.document_state_changed.connect(self._on_document_state_changed)
        self.workspace.document_added.connect(self._update_actions)
        self.workspace.document_removed.connect(self._update_actions)
        self.thumbnails.close_requested.connect(self.close_document)
        self.thumbnails.close_study_requested.connect(self.close_study)
        self.thumbnails.edit_study_requested.connect(self.edit_study)
        self.metadata_view.status_message.connect(self._flash)
        self.content_view.status_message.connect(self._flash)
        self.overview_view.element_requested.connect(self._reveal_element)
        self.tabs.currentChanged.connect(self._update_status)
        viewer = self.content_view.viewer
        viewer.zoom_changed.connect(
            lambda zoom: self._set_label(self.zoom_label, f"Zoom: {zoom:.0%}")
        )
        viewer.window_level_changed.connect(lambda text: self._set_label(self.wl_label, text))
        viewer.pixel_info_changed.connect(lambda text: self._set_label(self.pixel_label, text))
        viewer.decode_failed.connect(self._update_status)

    def _apply_default_geometry(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 800)
            return
        available = screen.availableGeometry()
        width, height = int(available.width() * 0.8), int(available.height() * 0.85)
        self.resize(width, height)
        self.move(available.center().x() - width // 2, available.center().y() - height // 2)

    def _show_document(self, document: Document | None):
        self.path_field.setText(str(document.path) if document else "")
        self.metadata_view.set_document(document)
        self.content_view.set_document(document)
        self._update_overview()
        self._update_title()
        self._update_actions()
        self._update_status()

    def _on_document_changed(self, document: Document):
        if document is self.workspace.current:
            self.metadata_view.refresh()
            self.content_view.refresh()
            self._update_overview()
            self._update_status()

    def _on_document_state_changed(self, document: Document):
        if document is self.workspace.current:
            self.path_field.setText(str(document.path))
            self._update_title()
        self._update_actions()

    def _update_overview(self):
        document = self.workspace.current
        cross = validate_workspace({d.path: d.dataset for d in self.workspace}) if document else {}
        self.overview_view.set_document(document, cross.get(document.path, []) if document else [])

    def _update_title(self):
        document = self.workspace.current
        self.setWindowTitle(f"{document.name}[*] - {APP_NAME}" if document else APP_NAME)
        self.setWindowModified(bool(document and document.is_modified))

    def _update_actions(self):
        count = len(self.workspace)
        for action in (
            self.save_action,
            self.save_as_action,
            self.export_action,
            self.close_action,
            self.anonymize_action,
            self.add_tag_action,
        ):
            action.setEnabled(self.workspace.current is not None)
        self.save_all_action.setEnabled(bool(self.workspace.modified_documents()))
        self.close_all_action.setEnabled(count > 0)
        self.compare_action.setEnabled(count >= 2)
        self.validate_action.setEnabled(count > 0)

    def _update_status(self):
        for label in self._image_labels():
            label.setVisible(self._showing_image() and bool(label.text()))
        self.statusBar().showMessage(self._status_text())

    def _status_text(self) -> str:
        document = self.workspace.current
        if document is None:
            return "No DICOM file loaded"
        ds = document.dataset
        tab = self.tabs.currentWidget()
        if tab is self.metadata_view:
            return f"{self.metadata_view.element_count()} elements"
        if tab is self.overview_view:
            return plural(len(self.overview_view.issues), "validation problem")
        if self._showing_image():
            parts = [
                f"{ds.get('Columns', '?')} x {ds.get('Rows', '?')} px",
                f"{ds.get('BitsStored', '?')} bits",
                str(ds.get("PhotometricInterpretation", "")),
            ]
            if document.frame_count > 1:
                parts.append(f"{document.frame_count} frames")
            return ", ".join(parts)
        if document.is_report:
            return "Structured report"
        return "Pixel data cannot be decoded" if document.has_pixels else "No pixel data"

    def _image_labels(self) -> tuple[QLabel, ...]:
        return self.pixel_label, self.wl_label, self.zoom_label

    def _showing_image(self) -> bool:
        return self.tabs.currentWidget() is self.content_view and self.content_view.showing_image

    def _set_label(self, label: QLabel, text: str):
        label.setText(text)
        label.setVisible(self._showing_image() and bool(text))

    def _flash(self, message: str):
        self.statusBar().showMessage(message, 4000)

    def _reveal_element(self, path):
        self.tabs.setCurrentWidget(self.metadata_view)
        if not self.metadata_view.select(path):
            self._flash("The element is no longer present")

    def _find_tag(self):
        self.tabs.setCurrentWidget(self.metadata_view)
        self.metadata_view.focus_search()

    def _add_tag(self):
        self.tabs.setCurrentWidget(self.metadata_view)
        self.metadata_view.add_element()

    def _close_current(self):
        if self.workspace.current is not None:
            self.close_document(self.workspace.current)

    def _browse_files(self):
        files = self.file_dialogs.open_files()
        if files:
            self.open_paths(files)

    def _browse_folder(self):
        folder = self.file_dialogs.open_folder()
        if folder:
            self.open_paths([folder])

    def _on_loaded(self, result: LoadResult):
        if self.workspace.get(result.path) is None:
            document = Document(
                result.path, result.dataset, result.thumbnail, result.thumbnail_error
            )
            self.workspace.add(document)
            if self.workspace.current is None:
                self.workspace.set_current(document)

    def _on_job_finished(self, summary: LoadSummary):
        finished = [job for job in self._jobs if job.summary is summary]
        self._jobs = [job for job in self._jobs if job.summary is not summary]
        for job in finished:
            job.deleteLater()
        self._update_progress()
        for path in summary.request.sources_of(summary.loaded):
            self.recent_files.add(path)
        self._rebuild_recent_menu()

        explicit = summary.request.explicit
        skipped = [path for path, _ in summary.failed if path not in explicit]
        message = f"Loaded {plural(len(summary.loaded), 'file')}"
        if skipped:
            message += f", skipped {plural(len(skipped), 'unreadable or non-DICOM file')}"
        self._flash(message + (" (cancelled)" if summary.cancelled else ""))

        failures = [(p, e) for p, e in summary.failed if p in explicit or not summary.loaded]
        if failures:
            names = "\n".join(path.name for path, _ in failures[:10])
            more = f"\nand {len(failures) - 10} more" if len(failures) > 10 else ""
            details = "\n".join(f"{path}: {error}" for path, error in failures)
            self.show_error("Files Not Loaded", f"Could not load:\n{names}{more}", details)

    def _update_progress(self):
        total = sum(len(job.files) for job in self._jobs)
        done = sum(job.done for job in self._jobs)
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.progress.setFormat(f"Loading {done}/{total}")
        self.progress.setVisible(bool(self._jobs))
        self.cancel_button.setVisible(bool(self._jobs))

    def _cancel_loading(self):
        for job in self._jobs:
            job.cancel()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        paths = self.recent_files.paths()
        self.recent_menu.setEnabled(bool(paths))
        for path in paths:
            exists = Path(path).exists()
            action = self.recent_menu.addAction(Path(path).name + ("" if exists else " (missing)"))
            action.setToolTip(path)
            action.setEnabled(exists)
            action.triggered.connect(lambda _=False, p=path: self.open_paths([p]))
        if paths:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Clear Recent", self._clear_recent)

    def _clear_recent(self):
        self.recent_files.clear()
        self._rebuild_recent_menu()

    def _confirm_discard(self, documents, verb: str = "close") -> bool:
        """Offer to save modified documents, False when the user cancels."""
        modified = [d for d in documents if d.is_modified]
        if not modified:
            return True
        names = "\n".join(d.name for d in modified[:10])
        more = f"\nand {len(modified) - 10} more" if len(modified) > 10 else ""
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes before you {verb}?\n\n{names}{more}",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if reply == QMessageBox.Save:
            return self._save(modified)
        return reply == QMessageBox.Discard

    def _save(self, documents, target: Path | None = None) -> bool:
        errors = []
        for document in documents:
            try:
                document.save(target)
            except Exception as e:
                log.exception("Saving %s failed", document.path)
                errors.append(f"{document.name}: {e}")
        if errors:
            self.show_error("Save Failed", "Some files could not be saved.", "\n".join(errors))
        return not errors

    def _save_copies(self, documents):
        folder = self.file_dialogs.choose_folder("Save Copies To Folder")
        if folder is None:
            return
        targets = plan_copy_targets([d.path for d in documents], normalize_path(folder))
        conflicts = [d for d in documents if self.workspace.get(targets[d.path]) not in (None, d)]
        if conflicts:
            names = "\n".join(str(targets[d.path]) for d in conflicts)
            self.show_error("Save Copies", f"These targets are open as other files:\n{names}")
            return
        existing = sum(1 for target in targets.values() if target.exists())
        if existing:
            reply = QMessageBox.question(
                self,
                "Overwrite Files",
                f"{existing} files already exist in the folder. Overwrite them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        saved = sum(self._save([document], targets[document.path]) for document in documents)
        self._flash(f"Saved {plural(saved, 'file')} to {folder}")

    def _open_overview(self, document):
        if document in self.workspace.documents():
            self.workspace.set_current(document)
            self.tabs.setCurrentWidget(self.overview_view)

    def _on_report_closed(self):
        self._report_dialog = None

    def _show_shortcuts(self):
        rows = "".join(
            f"<tr><td style='padding-right:16px'>{keys}</td><td>{what}</td></tr>"
            for keys, what in SHORTCUTS
        )
        QMessageBox.information(self, "Keyboard Shortcuts", f"<table>{rows}</table>")
