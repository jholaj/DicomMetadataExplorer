from pathlib import Path

import pydicom
import pydicom.config
from pydicom.errors import InvalidDicomError
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from constants import THUMBNAIL_PANEL_WIDTH
from styles import icons
from styles.theme import get_application_style
from ui.dialogs import CompareMetadataDialog
from ui.managers.file_browser_manager import FileBrowserManager
from ui.managers.thumbnail_manager import ThumbnailManager
from ui.viewers.image_viewer import ImageViewer
from ui.viewers.metadata_viewer import MetadataViewer
from ui.viewers.overview_viewer import OverviewViewer
from ui.viewers.report_viewer import ReportViewer
from utils.anonymizer import anonymize_dataset
from utils.dicom_properties import frame_count

# Constants
ERROR_MESSAGE_TEMPLATE = "Error: {}"
# Ignore invalid data and replace with UN
pydicom.config.convert_wrong_length_to_UN = True


class DicomExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Explorer")
        self.setAcceptDrops(True)
        self.datasets = {}  # Dictionary to store opened DICOM datasets
        self.current_file = None
        self.study_groups = {}  # Dictionary to group datasets by StudyInstanceUID
        self.modified_files = set()  # Files with unsaved metadata changes
        self.settings = QSettings("DicomMetadataExplorer", "DicomExplorer")

        # Initialize FileBrowserManager
        self.file_browser_manager = FileBrowserManager(self)

        self.initialize_ui()
        self.initialize_menu_bar()
        self.setup_signal_slots()

        # Initialize ThumbnailManager
        self.thumbnail_manager = ThumbnailManager(
            self.thumbnail_panel, self.thumbnail_layout, self.study_groups
        )

        self._apply_default_geometry()

    def _apply_default_geometry(self):
        """Open at a comfortable size, centered on the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 800)
            return
        available = screen.availableGeometry()
        width = int(available.width() * 0.8)
        height = int(available.height() * 0.85)
        self.resize(width, height)
        self.move(
            available.left() + (available.width() - width) // 2,
            available.top() + (available.height() - height) // 2,
        )

    def initialize_ui(self):
        """Initialize the user interface."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Resizable split between the thumbnail panel and the main content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        # Left panel for DICOM thumbnails
        scroll_area = self.initialize_left_panel()
        splitter.addWidget(scroll_area)

        # Right panel for main content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Store actions as instance variables
        self.open_action = QAction(icons.open_icon(), "Open", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.setToolTip("Open DICOM files (Ctrl+O)")
        self.save_action = QAction(icons.save_icon(), "Save", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setToolTip("Save current DICOM file (Ctrl+S)")
        self.save_all_action = QAction(icons.save_all_icon(), "Save All", self)
        self.save_all_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_all_action.setToolTip(
            "Save all modified files - in place or as copies to a folder (Ctrl+Shift+S)"
        )
        self.export_action = QAction(icons.export_icon(), "Export", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setToolTip("Export metadata to JSON or CSV (Ctrl+E)")
        self.anonymize_action = QAction(icons.anonymize_icon(), "Anonymize", self)
        self.anonymize_action.setToolTip("Remove identifying information from the current file")
        self.compare_action = QAction(icons.compare_icon(), "Compare", self)
        self.compare_action.setToolTip("Compare metadata of two loaded files")
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.save_all_action)
        toolbar.addSeparator()
        toolbar.addAction(self.export_action)
        toolbar.addAction(self.anonymize_action)
        toolbar.addAction(self.compare_action)

        # File path display
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Select a DICOM file...")
        right_layout.addWidget(self.file_path)

        # Tab widget for metadata, image, and overview
        self.tab_widget = QTabWidget()
        self.metadata_viewer = MetadataViewer()
        self.image_viewer = ImageViewer()
        self.overview_viewer = OverviewViewer()
        self.tab_widget.addTab(self.metadata_viewer, "Metadata")
        self.tab_widget.addTab(self.build_content_tab(), "Content")
        self.tab_widget.addTab(self.overview_viewer, "Overview")
        right_layout.addWidget(self.tab_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.pixel_label = QLabel()
        self.pixel_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.pixel_label.setToolTip("Pixel under cursor - Shift + left drag to measure distance")
        self.status_bar.addPermanentWidget(self.pixel_label)
        self.pixel_label.hide()
        self.wl_label = QLabel()
        self.wl_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.wl_label.setToolTip("Window/Level - drag with right mouse button, R to reset")
        self.status_bar.addPermanentWidget(self.wl_label)
        self.wl_label.hide()
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_bar.addPermanentWidget(self.zoom_label)
        self.zoom_label.hide()

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([THUMBNAIL_PANEL_WIDTH, 1000])
        self.setStyleSheet(get_application_style())

    def build_content_tab(self):
        """Wrap the image viewer with image tools, a frame slider, and
        an alternative report view for structured reports."""
        content_tab = QWidget()
        layout = QVBoxLayout(content_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.image_tools_bar = self.build_image_tools_bar()
        layout.addWidget(self.image_tools_bar)

        self.report_viewer = ReportViewer()
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.image_viewer)
        self.content_stack.addWidget(self.report_viewer)
        layout.addWidget(self.content_stack)

        self.frame_bar = QWidget()
        bar_layout = QHBoxLayout(self.frame_bar)
        bar_layout.setContentsMargins(8, 0, 8, 4)
        bar_layout.addWidget(QLabel("Frame"))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        bar_layout.addWidget(self.frame_slider, stretch=1)
        self.frame_label = QLabel("1 / 1")
        bar_layout.addWidget(self.frame_label)
        self.frame_bar.hide()
        layout.addWidget(self.frame_bar)

        return content_tab

    def build_image_tools_bar(self):
        """Build the row of image tools shown above the viewer."""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 0)
        layout.setSpacing(4)

        def add_tool(text, tooltip, callback):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            layout.addWidget(button)
            return button

        viewer = self.image_viewer
        add_tool("Fit", "Fit image to window (0)", viewer.centerAndScaleImage)
        add_tool(
            "1:1", "Actual size - one image pixel per screen pixel (1)", viewer.zoom_actual_size
        )
        add_tool("⟲", "Rotate left ([)", lambda: viewer.rotate_view(-90))
        add_tool("⟳", "Rotate right (])", lambda: viewer.rotate_view(90))
        add_tool("↔", "Flip horizontally (H)", lambda: viewer.flip_view(True))
        add_tool("↕", "Flip vertically (V)", lambda: viewer.flip_view(False))
        add_tool("Invert", "Invert grayscale (I)", viewer.toggle_invert)
        add_tool("Reset W/L", "Reset window/level to dataset values (R)", viewer.reset_window_level)
        layout.addSpacing(12)
        add_tool("Copy", "Copy the current view to the clipboard", self.copy_view_to_clipboard)
        add_tool("PNG", "Save the current view as a PNG image", self.save_view_as_png)

        layout.addStretch()
        hint = QLabel("W/L: right drag · Measure: Shift + drag")
        hint.setObjectName("image_tools_hint")
        layout.addWidget(hint)

        return bar

    def copy_view_to_clipboard(self):
        """Copy the rendered image view (with W/L and overlays) to the clipboard."""
        if not self.image_viewer.image_item:
            self.status_bar.showMessage("No image to copy")
            return
        QApplication.clipboard().setPixmap(self.image_viewer.grab())
        self.status_bar.showMessage("View copied to clipboard", 3000)

    def save_view_as_png(self):
        """Save the rendered image view as a PNG file."""
        if not self.image_viewer.image_item:
            self.status_bar.showMessage("No image to save")
            return

        default_name = str(
            Path(self.file_browser_manager.last_used_directory)
            / f"{Path(self.current_file).stem}.png"
        )
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save View As PNG", default_name, "PNG image (*.png)"
        )
        if not file_name:
            return
        if not file_name.lower().endswith(".png"):
            file_name += ".png"

        if self.image_viewer.grab().save(file_name, "PNG"):
            self.status_bar.showMessage(f"View saved to {file_name}", 3000)
        else:
            self.show_error_message(f"Failed to save view to {file_name}")

    def initialize_menu_bar(self):
        """Build the menu bar (File and Tools menus)."""
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.open_action)
        self.recent_menu = QMenu("Open Recent", self)
        file_menu.addMenu(self.recent_menu)
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_all_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _recent_files(self):
        """Read the recent-files list from settings."""
        value = self.settings.value("recent_files", [])
        if isinstance(value, str):
            value = [value]
        return list(value or [])

    def add_recent_file(self, path):
        """Record a successfully opened path and refresh the menu."""
        recent = self._recent_files()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.settings.setValue("recent_files", recent[:10])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        recent = self._recent_files()
        self.recent_menu.setEnabled(bool(recent))
        for path in recent:
            action = self.recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.load_files([p]))
        if recent:
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction("Clear Recent")
            clear_action.triggered.connect(self._clear_recent)

    def _clear_recent(self):
        self.settings.setValue("recent_files", [])
        self._rebuild_recent_menu()

    def setup_signal_slots(self):
        """Set up signal-slot connections."""
        self.tab_widget.currentChanged.connect(self.update_status_bar)
        self.image_viewer.zoom_changed.connect(self.update_zoom_status)
        self.image_viewer.window_level_changed.connect(self.update_wl_status)
        self.image_viewer.pixel_info_changed.connect(self.update_pixel_status)
        self.image_viewer.frame_changed.connect(self.update_frame_bar)
        self.frame_slider.valueChanged.connect(self.image_viewer.set_frame)
        self.metadata_viewer.dataset_modified.connect(self.mark_current_modified)

        # Connect toolbar actions
        self.open_action.triggered.connect(self.browse_file)
        self.save_action.triggered.connect(self.save_file)
        self.save_all_action.triggered.connect(self.save_all_files)
        self.export_action.triggered.connect(self.export_metadata)
        self.anonymize_action.triggered.connect(self.anonymize_current_file)
        self.compare_action.triggered.connect(self.compare_files)

    def update_frame_bar(self, frame, count):
        """Sync the frame slider with the viewer state."""
        if count > 1:
            self.frame_slider.blockSignals(True)
            self.frame_slider.setMaximum(count - 1)
            self.frame_slider.setValue(frame)
            self.frame_slider.blockSignals(False)
            self.frame_label.setText(f"{frame + 1} / {count}")
            self.frame_bar.show()
        else:
            self.frame_bar.hide()

    def initialize_left_panel(self):
        """Initialize the left panel with thumbnails and scroll area."""
        self.thumbnail_panel = QWidget()
        self.thumbnail_panel.setObjectName("thumbnail_panel")
        self.thumbnail_layout = QGridLayout(self.thumbnail_panel)
        self.thumbnail_layout.setAlignment(Qt.AlignTop)

        # Create a QScrollArea and set the thumbnail_panel as its widget
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.thumbnail_panel)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_area.setMinimumWidth(160)
        scroll_area.setMaximumWidth(420)

        return scroll_area

    def on_thumbnail_clicked(self):
        """Handle thumbnail click events."""
        thumbnail = self.sender()  # Get the clicked thumbnail button
        file_path = thumbnail.property("file_path")

        self.thumbnail_manager.select_thumbnail(file_path)
        self.load_selected_dicom(file_path)

    def load_selected_dicom(self, file_path):
        """Load the selected DICOM file from the left panel."""
        if file_path in self.datasets:
            self.current_file = file_path
            self.update_display(self.datasets[file_path])
            self.thumbnail_manager.select_thumbnail(file_path)

    def update_display(self, dataset):
        """Update the metadata and image display for the selected DICOM file."""
        self.file_path.setText(self.current_file)
        self._update_window_title()
        self.metadata_viewer.load_metadata(dataset)
        self.overview_viewer.load_data(dataset, self.current_file)

        if hasattr(dataset, "pixel_array"):
            self.image_viewer.display_image(dataset)
            self.content_stack.setCurrentWidget(self.image_viewer)
            self.image_tools_bar.show()
        elif ReportViewer.is_report(dataset):
            self.image_viewer.clear()
            self.report_viewer.load_report(dataset)
            self.content_stack.setCurrentWidget(self.report_viewer)
            self.image_tools_bar.hide()
        else:
            self.image_viewer.clear()
            self.content_stack.setCurrentWidget(self.image_viewer)
            self.image_tools_bar.show()

        self.update_status_bar(self.tab_widget.currentIndex())

    def clear_display(self):
        """Clear all views when no file is loaded."""
        self.file_path.clear()
        self.metadata_viewer.clear()
        self.image_viewer.clear()
        self.report_viewer.clear()
        self.content_stack.setCurrentWidget(self.image_viewer)
        self.image_tools_bar.show()
        self.overview_viewer.clear()
        self._update_window_title()
        self.status_bar.showMessage("No DICOM file loaded")

    def _update_window_title(self):
        """Show the current file (with a modification marker) in the title."""
        if self.current_file:
            marker = " *" if self.current_file in self.modified_files else ""
            self.setWindowTitle(f"DICOM Explorer - {Path(self.current_file).name}{marker}")
        else:
            self.setWindowTitle("DICOM Explorer")

    def mark_current_modified(self):
        """Mark the current file as having unsaved changes."""
        if self.current_file:
            self.modified_files.add(self.current_file)
            self._update_window_title()

    def close_file(self, file_path, confirm=True):
        """Remove a file from the workspace."""
        if file_path not in self.datasets:
            return

        if confirm and file_path in self.modified_files:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"{Path(file_path).name} has unsaved changes. Close anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        del self.datasets[file_path]
        self.modified_files.discard(file_path)
        self.thumbnail_manager.forget_file(file_path)
        for study_uid in list(self.study_groups):
            entries = [e for e in self.study_groups[study_uid] if e[0] != file_path]
            if entries:
                self.study_groups[study_uid] = entries
            else:
                del self.study_groups[study_uid]

        if self.current_file == file_path:
            self.current_file = next(iter(self.datasets), None)
            if self.current_file:
                self.update_display(self.datasets[self.current_file])
            else:
                self.clear_display()

        self.thumbnail_manager.rebuild_thumbnail_layout()
        self.status_bar.showMessage(f"Closed {Path(file_path).name}", 3000)

    def close_study(self, file_path):
        """Remove all files of the study containing file_path."""
        dataset = self.datasets.get(file_path)
        if dataset is None:
            return

        study_uid = getattr(dataset, "StudyInstanceUID", "Unknown")
        paths = [path for path, _ in self.study_groups.get(study_uid, [])]

        modified = [p for p in paths if p in self.modified_files]
        if modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"{len(modified)} file(s) in this study have unsaved changes. Close anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        for path in paths:
            self.close_file(path, confirm=False)

    def update_status_bar(self, index: int) -> None:
        """Update the status bar based on the active tab."""
        if not self.current_file or self.current_file not in self.datasets:
            self.status_bar.showMessage("No DICOM file loaded")
            self.zoom_label.hide()
            return

        dataset = self.datasets[self.current_file]

        if index != 1:
            self.pixel_label.hide()

        if index == 0:  # Metadata tab
            tag_count = self.metadata_viewer.tree.topLevelItemCount()
            self.status_bar.showMessage(f"Loaded {tag_count} DICOM tags")
            self.zoom_label.hide()
            self.wl_label.hide()

        elif index == 1:  # Content tab
            if hasattr(dataset, "pixel_array"):
                width = getattr(dataset, "Columns", "?")
                height = getattr(dataset, "Rows", "?")
                bits = getattr(dataset, "BitsStored", "unknown")
                message = f"Dimensions: {width}x{height}, {bits} bits/pixel"
                if int(getattr(dataset, "SamplesPerPixel", 1) or 1) == 3:
                    message += ", color"
                frames = frame_count(dataset)
                if frames > 1:
                    message += f", {frames} frames"
                self.status_bar.showMessage(message)
                self.zoom_label.show()
                self.wl_label.show()
            else:
                self.zoom_label.hide()
                self.wl_label.hide()
                if ReportViewer.is_report(dataset):
                    items = len(dataset.ContentSequence)
                    self.status_bar.showMessage(
                        f"Structured report - {items} top-level content item(s)"
                    )

        elif index == 2:  # Overview tab
            self.zoom_label.hide()
            self.wl_label.hide()
            issues = self.overview_viewer.issue_count
            if issues:
                self.status_bar.showMessage(f"Validation found {issues} issue(s)")
            else:
                self.status_bar.showMessage("Validation passed with no issues")

    def update_zoom_status(self, relative_zoom):
        """Update the zoom level display."""
        zoom_percentage = int(relative_zoom * 100)
        self.zoom_label.setText(f"Zoom: {zoom_percentage}%")
        self.zoom_label.show()

    def update_wl_status(self, center, width):
        """Update the window/level display."""
        self.wl_label.setText(f"W: {width:.0f}  L: {center:.0f}")
        if self.tab_widget.currentIndex() == 1:
            self.wl_label.show()

    def update_pixel_status(self, text):
        """Update the pixel-under-cursor display."""
        if text and self.tab_widget.currentIndex() == 1:
            self.pixel_label.setText(text)
            self.pixel_label.show()
        else:
            self.pixel_label.hide()

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle file drop event."""
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            self.handle_dropped_files(files)
        else:
            event.ignore()

    def handle_dropped_files(self, files):
        """Process dropped files and directories."""
        self.load_files(files)

    def load_files(self, paths):
        """Load a batch of files and directories with a single layout rebuild."""
        expanded = []
        inputs = {}  # original input -> its expanded files
        for file_path in paths:
            path = Path(file_path)
            if path.is_dir():
                children = [p for p in sorted(path.rglob("*")) if p.is_file()]
                inputs[path] = children
                expanded.extend(children)
            else:
                inputs[path] = [path]
                expanded.append(path)

        failed = []
        for path in expanded:
            if not self.load_dicom(str(path), show_error=False, rebuild=False):
                failed.append(path.name)

        self.thumbnail_manager.rebuild_thumbnail_layout()

        # Remember inputs that produced at least one loaded file
        for original, children in inputs.items():
            if any(str(child) in self.datasets for child in children):
                self.add_recent_file(str(original.resolve()))

        loaded = len(expanded) - len(failed)
        if loaded:
            self.status_bar.showMessage(f"Loaded {loaded} file(s)", 3000)

        if failed:
            shown = "\n".join(failed[:10])
            if len(failed) > 10:
                shown += f"\n... and {len(failed) - 10} more"
            QMessageBox.warning(
                self,
                "Invalid Files",
                f"The following files could not be loaded as DICOM:\n{shown}",
            )

    def browse_file(self):
        """Open one or more DICOM files using FileBrowserManager."""
        self.file_browser_manager.browse_file()

    def load_dicom(self, file_path, show_error=True, rebuild=True):
        """Load a DICOM file and add it to the dataset.

        Returns True on success (or if the file is already loaded).
        """
        if file_path in self.datasets:
            self.current_file = file_path
            self.update_display(self.datasets[file_path])
            self.thumbnail_manager.select_thumbnail(file_path)
            self.status_bar.showMessage(f"{Path(file_path).name} is already loaded", 3000)
            return True

        try:
            dataset = pydicom.dcmread(file_path)
            if not dataset:
                raise ValueError("No data found in DICOM file.")

            self.datasets[file_path] = dataset
            self.add_thumbnail(file_path, dataset, rebuild=rebuild)

            if not self.current_file:
                self.current_file = file_path
                self.update_display(dataset)

            if rebuild:
                self.status_bar.showMessage(f"Loaded {Path(file_path).name}", 3000)
            return True
        except InvalidDicomError:
            if show_error:
                self.show_error_message(f"{Path(file_path).name} is not a valid DICOM file.")
            return False
        except Exception as e:
            if show_error:
                self.show_error_message(f"Error loading file: {e!s}")
            return False

    def add_thumbnail(self, file_path, dataset, rebuild=True):
        """Add a thumbnail of the DICOM file to the left panel."""
        study_uid = dataset.StudyInstanceUID if hasattr(dataset, "StudyInstanceUID") else "Unknown"

        # Group datasets by StudyInstanceUID
        if study_uid not in self.study_groups:
            self.study_groups[study_uid] = []

        self.study_groups[study_uid].append((file_path, dataset))

        if rebuild:
            self.thumbnail_manager.rebuild_thumbnail_layout()

    def save_file(self):
        """Save the currently selected DICOM file."""
        if (
            not hasattr(self, "current_file")
            or not hasattr(self, "datasets")
            or self.current_file not in self.datasets
        ):
            self.status_bar.showMessage("No DICOM file loaded")
            return

        # Use FileBrowserManager to handle the save dialog
        saved = self.file_browser_manager.save_file(
            self.datasets[self.current_file], self.current_file
        )
        if saved:
            self.modified_files.discard(self.current_file)
            self._update_window_title()

    def save_all_files(self):
        """Save all modified files - in place or as copies into a folder."""
        modified = sorted(self.modified_files)
        if not modified:
            self.status_bar.showMessage("No unsaved changes")
            return

        box = QMessageBox(self)
        box.setWindowTitle("Save All")
        box.setText(f"Save {len(modified)} modified file(s)?")
        overwrite_button = box.addButton("Overwrite Originals", QMessageBox.AcceptRole)
        folder_button = box.addButton("Save To Folder...", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()

        if clicked is overwrite_button:
            target_dir = None
        elif clicked is folder_button:
            target_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Target Folder",
                self.file_browser_manager.last_used_directory,
            )
            if not target_dir:
                return
        else:
            return

        saved, errors = 0, []
        for path in modified:
            try:
                target = Path(target_dir) / Path(path).name if target_dir else Path(path)
                self.datasets[path].save_as(str(target))
                self.modified_files.discard(path)
                saved += 1
            except Exception as e:
                errors.append(f"{Path(path).name}: {e}")

        self._update_window_title()
        destination = f" to {target_dir}" if target_dir else ""
        self.status_bar.showMessage(f"Saved {saved} file(s){destination}", 5000)
        if errors:
            self.show_error_message("Some files could not be saved:\n" + "\n".join(errors[:10]))

    def export_metadata(self):
        """Export metadata of the currently selected DICOM file."""
        if not self.current_file or self.current_file not in self.datasets:
            self.status_bar.showMessage("No DICOM file loaded")
            return

        self.file_browser_manager.export_metadata(
            self.datasets[self.current_file], self.current_file
        )

    def anonymize_current_file(self):
        """Anonymize identifying tags in the current file or all loaded files."""
        if not self.current_file or self.current_file not in self.datasets:
            self.status_bar.showMessage("No DICOM file loaded")
            return

        targets = self._ask_anonymization_targets()
        if not targets:
            return

        try:
            changed = sum(anonymize_dataset(self.datasets[path]) for path in targets)
            self.modified_files.update(targets)
            self.update_display(self.datasets[self.current_file])
            self.thumbnail_manager.rebuild_thumbnail_layout()
            self.status_bar.showMessage(
                f"Anonymized {changed} tags in {len(targets)} file(s) (private tags removed)",
                5000,
            )
        except Exception as e:
            self.show_error_message(f"Failed to anonymize: {e!s}")

    def _ask_anonymization_targets(self):
        """Ask which files to anonymize; return a list of datasets (empty = cancel)."""
        description = (
            "Person names and identifying tags will be replaced and private "
            "tags removed. Changes apply to the loaded data and take effect "
            "on disk after saving."
        )

        if len(self.datasets) == 1:
            reply = QMessageBox.question(
                self,
                "Confirm Anonymization",
                f"Anonymize {Path(self.current_file).name}?\n\n{description}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return [self.current_file] if reply == QMessageBox.Yes else []

        box = QMessageBox(self)
        box.setWindowTitle("Confirm Anonymization")
        box.setText(f"Anonymize the current file or all loaded files?\n\n{description}")
        current_button = box.addButton(
            f"Current ({Path(self.current_file).name})", QMessageBox.AcceptRole
        )
        all_button = box.addButton(f"All Files ({len(self.datasets)})", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked is current_button:
            return [self.current_file]
        if clicked is all_button:
            return list(self.datasets)
        return []

    def compare_files(self):
        """Open a dialog comparing metadata of two loaded files."""
        if len(self.datasets) < 2:
            self.status_bar.showMessage("Load at least two DICOM files to compare")
            return

        dialog = CompareMetadataDialog(self.datasets, self.current_file, self)
        dialog.exec()

    def show_error_message(self, message):
        """Show an error message in the status bar and a message box."""
        self.status_bar.showMessage(ERROR_MESSAGE_TEMPLATE.format(message))
        QMessageBox.warning(self, "Error", message)

    def closeEvent(self, event):
        """Warn about unsaved changes before quitting."""
        if self.modified_files:
            names = "\n".join(Path(p).name for p in sorted(self.modified_files)[:10])
            if len(self.modified_files) > 10:
                names += f"\n... and {len(self.modified_files) - 10} more"
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"The following files have unsaved changes:\n{names}\n\nQuit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
