"""End-to-end tests of the main window (offscreen Qt)."""

import time
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.tag import Tag
from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox

from dicom_explorer.app.commands import AnonymizeCommand, SetValuesCommand
from dicom_explorer.app.document import Document
from dicom_explorer.core.anonymizer import AnonymizationOptions
from dicom_explorer.core.elements import ElementPath
from dicom_explorer.main import configure_pydicom
from dicom_explorer.ui.dialogs import AddElementDialog, EditValueDialog, StudyTagsDialog
from dicom_explorer.ui.main_window import DicomExplorer
from factories import code, make_image, make_sr, save

VIEW_CODE = ElementPath.top("ViewCodeSequence")
REGION = ElementPath.top("AnatomicRegionSequence")
CODE_VALUE = Tag("CodeValue")


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, str(tmp_path / "settings"))
    configure_pydicom()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    win = DicomExplorer()
    win.resize(1200, 800)
    win.show()
    yield win
    for document in win.workspace.documents():
        document.undo_stack.setClean()
    win.close()


def wait_for_loading(win, timeout=10):
    deadline = time.time() + timeout
    while win._jobs and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()
    assert not win._jobs, "loading did not finish"


def open_files(win, *paths):
    win.open_paths([str(p) for p in paths])
    wait_for_loading(win)


def nested(**attrs):
    ds = make_image(**attrs)
    ds.ImageType = ["ORIGINAL", "PRIMARY"]
    ds.AnatomicRegionSequence = [code("T-D3000", "SRT", "Chest")]
    ds.ViewCodeSequence = [code("R-10206", "SRT", "PA")]
    ds.CodeValue = "TOP-LEVEL"
    return ds


def test_batch_with_truncated_file_loads_everything(window, tmp_path):
    good = save(make_image(), tmp_path / "good.dcm")
    broken = make_image()
    broken.PixelData = broken.PixelData[:100]
    bad = save(broken, tmp_path / "bad.dcm")
    (tmp_path / "notes.txt").write_text("not dicom")

    open_files(window, tmp_path)
    names = sorted(d.name for d in window.workspace.documents())
    assert names == ["bad.dcm", "good.dcm"]

    bad_doc = window.workspace.get(Path(bad).resolve())
    assert bad_doc.thumbnail is None and bad_doc.thumbnail_error
    window.workspace.set_current(bad_doc)
    window.tabs.setCurrentWidget(window.content_view)
    assert window.content_view.stack.currentWidget() is window.content_view.message
    assert "cannot be decoded" in window.content_view.message.text()
    assert any(issue.severity.value == "error" for issue in window.overview_view.issues)

    window.workspace.set_current(window.workspace.get(Path(good).resolve()))
    assert window.content_view.showing_image


def test_unchanged_edit_keeps_multi_values_and_binary_safe(window, tmp_path):
    open_files(window, save(nested(), tmp_path / "x.dcm"))
    ds = window.workspace.current.dataset
    dialog = EditValueDialog(ds["ImageType"])
    assert dialog.value == ["ORIGINAL", "PRIMARY"]

    ds.add_new(0x00090010, "LO", "VENDOR")
    ds.add_new(0x00091001, "OB", b"\x01\x02")
    window.metadata_view.refresh()
    window.metadata_view.select(ElementPath.top(0x00091001))
    window.metadata_view.edit_element()  # binary: refused without opening a dialog
    assert ds[0x00091001].value == b"\x01\x02"


def test_editing_and_deleting_target_only_the_selected_nested_element(window, tmp_path):
    open_files(window, save(nested(), tmp_path / "x.dcm"))
    document = window.workspace.current
    ds = document.dataset

    path = VIEW_CODE.child(0).child(CODE_VALUE)
    document.push(SetValuesCommand(document, {path: "CHANGED"}))
    assert ds.ViewCodeSequence[0].CodeValue == "CHANGED"
    assert ds.AnatomicRegionSequence[0].CodeValue == "T-D3000"
    assert ds.CodeValue == "TOP-LEVEL"

    view = window.metadata_view
    assert view.select(REGION.child(0).child(CODE_VALUE))
    view_question = QMessageBox.question
    try:
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        view.delete_element()
    finally:
        QMessageBox.question = view_question
    assert "CodeValue" not in ds.AnatomicRegionSequence[0]
    assert ds.CodeValue == "TOP-LEVEL"
    assert ds.ViewCodeSequence[0].CodeValue == "CHANGED"

    document.undo_stack.undo()
    document.undo_stack.undo()
    assert ds.AnatomicRegionSequence[0].CodeValue == "T-D3000"
    assert ds.ViewCodeSequence[0].CodeValue == "R-10206"
    assert not document.is_modified


def test_undo_is_per_document(window, tmp_path):
    open_files(
        window, save(make_image(), tmp_path / "a.dcm"), save(make_image(), tmp_path / "b.dcm")
    )
    doc_a = window.workspace.get((tmp_path / "a.dcm").resolve())
    doc_b = window.workspace.get((tmp_path / "b.dcm").resolve())

    window.workspace.set_current(doc_a)
    doc_a.push(SetValuesCommand(doc_a, {ElementPath.top("PatientID"): "EDITED"}))
    window.workspace.set_current(doc_b)
    assert not window.undo_action.isEnabled()  # B has nothing to undo
    window.undo_action.trigger()
    assert doc_a.dataset.PatientID == "EDITED"
    assert doc_a.is_modified and not doc_b.is_modified


def test_add_element_to_sequence_item(window, tmp_path):
    open_files(window, save(nested(), tmp_path / "x.dcm"))
    view = window.metadata_view
    view.select(VIEW_CODE.child(0))  # the item node
    original_exec = AddElementDialog.exec

    def fake_exec(dialog):
        dialog.tag_edit.setText("CodeMeaning")
        dialog.value_edit.setText("Posteroanterior")
        return AddElementDialog.Accepted

    ds = window.workspace.current.dataset
    del ds.ViewCodeSequence[0].CodeMeaning
    view.refresh()
    AddElementDialog.exec = fake_exec
    try:
        view.add_element()
    finally:
        AddElementDialog.exec = original_exec
    assert ds.ViewCodeSequence[0].CodeMeaning == "Posteroanterior"
    assert "CodeMeaning" not in ds


def test_save_as_updates_path_and_clean_state(window, tmp_path, monkeypatch):
    open_files(window, save(make_image(), tmp_path / "a.dcm"))
    document = window.workspace.current
    document.push(SetValuesCommand(document, {ElementPath.top("PatientID"): "NEW"}))
    target = tmp_path / "copy.dcm"
    monkeypatch.setattr(window.file_dialogs, "save_as", lambda _doc: target)
    window.save_current_as()
    assert document.path == target.resolve()
    assert not document.is_modified
    assert window.workspace.get(target.resolve()) is document
    assert pydicom.dcmread(target).PatientID == "NEW"
    assert window.path_field.text() == str(target.resolve())


def test_save_all_to_folder_keeps_colliding_names_apart(window, tmp_path, monkeypatch):
    for series in ("s1", "s2"):
        (tmp_path / "in" / series).mkdir(parents=True)
        save(make_image(), tmp_path / "in" / series / "IM0001")
    open_files(window, tmp_path / "in")
    for document in window.workspace.documents():
        document.push(SetValuesCommand(document, {ElementPath.top("PatientID"): "BATCH"}))

    out = tmp_path / "out"
    monkeypatch.setattr(window.file_dialogs, "choose_folder", lambda _title: out)

    def click_folder_button(box):
        box.clicked_button = next(b for b in box.buttons() if "Folder" in b.text())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", click_folder_button)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.clicked_button)
    window.save_all()

    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("IM0001"))
    assert written == ["s1/IM0001", "s2/IM0001"]
    assert not window.workspace.modified_documents()


def test_close_study_after_study_uid_edit(window, tmp_path, monkeypatch):
    first = make_image()
    second = make_image(study_uid=first.StudyInstanceUID)
    open_files(window, save(first, tmp_path / "a.dcm"), save(second, tmp_path / "b.dcm"))
    doc_a = window.workspace.get((tmp_path / "a.dcm").resolve())
    doc_a.push(SetValuesCommand(doc_a, {ElementPath.top("StudyInstanceUID"): "1.2.3.4"}))
    assert window.thumbnails.model.rowCount() == 2  # regrouped into its own study

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard))
    window.close_study(doc_a)
    assert [d.name for d in window.workspace.documents()] == ["b.dcm"]


def test_search_filter_survives_switching_files(window, tmp_path):
    open_files(window, save(nested(), tmp_path / "a.dcm"), save(nested(), tmp_path / "b.dcm"))
    view = window.metadata_view
    view.search_input.setText("CodeValue")
    visible_before = view.proxy.rowCount()
    other = next(d for d in window.workspace.documents() if d is not window.workspace.current)
    window.workspace.set_current(other)
    assert view.search_input.text() == "CodeValue"
    assert view.proxy.rowCount() == visible_before < view.model.rowCount()


def test_anonymize_command_undo_redo(window, tmp_path):
    open_files(window, save(make_image(PatientName="Doe^John"), tmp_path / "a.dcm"))
    document = window.workspace.current
    document.push(AnonymizeCommand(document, AnonymizationOptions()))
    assert "Doe" not in str(document.dataset.PatientName)
    document.undo_stack.undo()
    assert str(document.dataset.PatientName) == "Doe^John"
    document.undo_stack.redo()
    assert document.dataset.PatientIdentityRemoved == "YES"


def test_sr_document_shows_report(window, tmp_path):
    open_files(window, save(make_sr(), tmp_path / "report.dcm"))
    assert window.content_view.stack.currentWidget() is window.content_view.report_view
    assert "No acute findings" in window.content_view.report_view.toPlainText()


def test_viewer_monochrome1_and_zoom_survives_resize(window, tmp_path):
    pixels = np.tile(np.arange(0, 4096, 16, dtype=np.uint16), (256, 1))
    ds = make_image(pixels, photometric="MONOCHROME1", WindowCenter=[1000, 3000])
    ds.WindowWidth = [500, 1000]
    open_files(window, save(ds, tmp_path / "m1.dcm"))
    window.tabs.setCurrentWidget(window.content_view)
    viewer = window.content_view.viewer
    assert window.wl_label.text() == "W: 500  L: 1000"

    rendered = viewer.frame.render(viewer.voi)
    assert rendered[0, 0] == 255 and rendered[0, -1] == 0  # low values bright

    viewer.zoom_by(2.0)
    zoom = viewer.current_zoom
    window.resize(1000, 700)
    QApplication.processEvents()
    assert viewer.current_zoom == pytest.approx(zoom)
    viewer.fit_to_window()
    assert viewer.fit_mode


def test_wheel_scrolls_frames_in_multiframe(window, tmp_path):
    open_files(window, save(make_image(frames=3), tmp_path / "mf.dcm"))
    window.tabs.setCurrentWidget(window.content_view)
    viewer = window.content_view.viewer
    event = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    viewer.wheelEvent(event)
    assert viewer.frame_index == 1
    assert window.content_view.frame_label.text() == "2 / 3"


def test_open_dialog_is_not_native(window, monkeypatch):
    seen = {}

    def fake_exec(dialog):
        seen["native_disabled"] = dialog.testOption(QFileDialog.DontUseNativeDialog)
        seen["layout"] = dialog.layout() is not None
        return 0

    monkeypatch.setattr(QFileDialog, "exec", fake_exec)
    assert window.file_dialogs.open_files() == []
    assert seen == {"native_disabled": True, "layout": True}


def rows_by_name(dialog):
    tree = dialog.tree
    return {
        tree.topLevelItem(i).text(1): tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
    }


def test_edit_study_tags_applies_to_all_files(window, tmp_path, monkeypatch):
    first = make_image(InstitutionName="Old Hospital", InstanceNumber=1)
    second = make_image(
        study_uid=first.StudyInstanceUID, InstitutionName="Old Hospital", InstanceNumber=2
    )
    open_files(window, save(first, tmp_path / "a.dcm"), save(second, tmp_path / "b.dcm"))
    documents = window.workspace.documents()

    def edit(dialog):
        rows = rows_by_name(dialog)
        assert "Instance Number" not in rows and "SOP Instance UID" not in rows
        rows["Institution Name"].setText(3, "New Hospital")
        rows["Study Instance UID"].setText(3, "1.2.3.4")
        assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
        return StudyTagsDialog.Accepted

    monkeypatch.setattr(StudyTagsDialog, "exec", edit)
    window.edit_study(documents[0])
    assert [d.dataset.InstitutionName for d in documents] == ["New Hospital"] * 2
    assert [d.dataset.StudyInstanceUID for d in documents] == ["1.2.3.4"] * 2
    assert window.thumbnails.model.rowCount() == 1  # the study stays together
    documents[0].undo_stack.undo()
    assert documents[0].dataset.InstitutionName == "Old Hospital"
    assert documents[1].dataset.InstitutionName == "New Hospital"


def test_study_tags_dialog_validates_values(qapp):
    documents = [Document(Path(name), make_image()) for name in ("a.dcm", "b.dcm")]
    dialog = StudyTagsDialog(documents)
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    study_date = rows_by_name(dialog)["Study Date"]
    assert not ok.isEnabled()

    study_date.setText(3, "2024-01-01")
    assert not ok.isEnabled() and "Invalid value for VR DA" in dialog.error_label.text()
    study_date.setText(3, "20240115")  # original value
    assert not ok.isEnabled() and not dialog.changes
    study_date.setText(3, "20240202")
    assert ok.isEnabled()
    assert dialog.changes == {0x00080020: "20240202"}
