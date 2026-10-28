"""Canvas exercises real document data, atomic local save and Markdown export."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from grangerpet.canvas import CanvasWorkspace


def test_canvas_opens_edits_saves_reopens_and_exports_without_changing_evidence(tmp_path):
    app=QApplication.instance() or QApplication([])
    source='# Report\n\nOriginal source [ev_0123456789abcdef0123](https://example.org/)\n\n## Facts\n\nText'
    original=tmp_path/'evidence.json';original.write_text('{"immutable":true}',encoding='utf-8')
    canvas=CanvasWorkspace(directory=tmp_path/'canvas');canvas.resize(800,600);canvas.open_document(source)
    canvas.show();app.processEvents()
    assert canvas.preview.document().begin().blockFormat().headingLevel()==1
    assert canvas.heading_list.count()==2
    canvas.edit_button.setChecked(True)
    edited=source+'\n\nUser-edited conclusion'
    canvas.editor.setPlainText(edited)
    destination=canvas.save_document()
    assert destination.read_text(encoding='utf-8')==edited
    exported=canvas.export_document(tmp_path/'report.md')
    assert exported.read_text(encoding='utf-8')==edited
    assert original.read_text(encoding='utf-8')=='{"immutable":true}' and canvas._original_source==source
    second=CanvasWorkspace(directory=tmp_path/'canvas');second.open_document(source)
    assert second.editor.toPlainText()==edited
    second.shutdown();second.close();canvas.shutdown();canvas.close()


def test_back_keeps_document_and_heading_navigation_selects_real_section(tmp_path):
    app=QApplication.instance() or QApplication([])
    canvas=CanvasWorkspace(directory=tmp_path);canvas.resize(800,600);canvas.open_document('# First\n\n'+('text\n\n'*50)+'## Second\n\nEnd')
    canvas.show();app.processEvents();closed=[];canvas.close_requested.connect(lambda:closed.append(True))
    canvas._go_heading(canvas.heading_list.item(1))
    assert canvas.preview.textCursor().block().text()=='Second'
    canvas.editor.appendPlainText('\nNew note');canvas.back.click()
    assert closed and canvas.editor.toPlainText().endswith('New note')
    assert list(tmp_path.glob('*.md'))
    canvas.shutdown();canvas.close()


def test_canvas_rejects_path_like_document_identifier(tmp_path):
    import pytest
    app=QApplication.instance() or QApplication([])
    canvas=CanvasWorkspace(directory=tmp_path)
    with pytest.raises(ValueError):canvas.open_document('Report','../outside')
    assert not list(tmp_path.iterdir())
    canvas.close()
