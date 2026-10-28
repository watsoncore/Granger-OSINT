"""Native Markdown rendering and streaming tests; no network or live model."""
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.markdown_view import MarkdownView, code_blocks, headings, public_link
from grangerpet.message_view import MessageHistory
from grangerpet.theme import STYLE
from grangerpet.typography import apply_app_font


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    for name in ('segoeui.ttf','segoeuib.ttf','SegUIVar.ttf'):
        path=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name
        if path.is_file():QFontDatabase.addApplicationFont(str(path))
    apply_app_font(app)
    yield app
    app.processEvents()


def test_markdown_renders_headings_emphasis_lists_quote_hr_and_inert_html(app):
    source='# Heading\n\n**Bold** and *italic* and `inline`\n\n- Item\n  - Nested\n\n1. Number\n\n> Quote\n\n---\n\n<b>Literal HTML</b>'
    view=MarkdownView(source)
    text=view.toPlainText()
    assert '**Bold**' not in text and 'Bold' in text and 'Quote' in text and '<b>Literal HTML</b>' in text
    assert view.document().begin().blockFormat().headingLevel()==1
    cursor=view.document().find('Bold')
    assert cursor.charFormat().fontWeight()>=600
    assert view.document().find('italic').charFormat().fontItalic()
    assert sum(block.textList() is not None for block in _blocks(view))>=3
    view.close()


def _blocks(view):
    block=view.document().begin()
    while block.isValid():yield block;block=block.next()


def test_markdown_links_require_public_http_action_and_never_load_resources(app,monkeypatch):
    opened=[];rejected=[]
    monkeypatch.setattr('grangerpet.markdown_view.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    view=MarkdownView('[public](https://example.org/) [bad](javascript:alert) ![image](file:///private.png)')
    view.link_rejected.connect(rejected.append)
    assert view.loadResource(2,QUrl('file:///private.png')) is None
    assert not opened
    view._open_anchor(QUrl('https://example.org/'))
    for url in ('javascript:alert(1)','file:///private.png','data:text/plain,unsafe','http://127.0.0.1/'):
        view._open_anchor(QUrl(url))
    assert opened==['https://example.org/'] and len(rejected)==4
    view.close()


@pytest.mark.parametrize('url',['http://localhost/','http://169.254.169.254/','http://[::1]/','https://user:password@example.org/','https://example.org:444/'])
def test_unsafe_link_schemes_credentials_and_local_addresses_rejected(url):
    assert not public_link(url)


def test_native_tables_keep_columns_and_offer_horizontal_scroll(app):
    header='|'+ '|'.join('Column'+str(n) for n in range(9))+'|\n'
    source=header+'|'+'|'.join('---' for _ in range(9))+'|\n'+'|'+'|'.join('value'+str(n) for n in range(9))+'|'
    view=MarkdownView(source,auto_height=True);view.resize(380,300);view.show();app.processEvents();view.fit_height();app.processEvents()
    assert [table.columns() for table in view._tables()]==[9]
    assert view.horizontalScrollBar().maximum()>0
    assert view.document().size().height()<=view.height()
    view.close()


def test_fenced_code_copy_and_incomplete_stream_blocks():
    assert code_blocks('```python\nprint(1)\n```\n\n~~~json\n{}')==[('python','print(1)'),('json','{}')]
    assert [h['title'] for h in headings('# Report\n```\n# not-heading\n```\n## Sources')]==['Report','Sources']


def test_streaming_updates_one_bubble_without_duplicate_markdown(app):
    history=MessageHistory();history.resize(620,480);history.show()
    bubble=history.append_message('model','# Re')
    for source in ('# Report\n\n**unfin','# Report\n\n**finished**\n\n```python\nprint(1)', '# Report\n\n**finished**\n\n```python\nprint(1)\n```'):
        history.update_message(bubble,source)
    history.flush_updates();app.processEvents()
    assert len(history.bubbles)==1 and len(history._records)==1
    assert 'finished' in bubble.text_view.toPlainText() and '**finished**' not in bubble.text_view.toPlainText()
    assert bubble.text_view.toPlainText().count('print(1)')==1
    history.close()


def test_reading_old_messages_does_not_jump_on_stream_update(app):
    history=MessageHistory();history.resize(620,400);history.show()
    for index in range(25):history.append_message('model',f'Message {index}\n\n'+ 'Some text '*15)
    app.processEvents();QTest.qWait(180);app.processEvents()
    bar=history.verticalScrollBar();bar.setValue(max(0,bar.maximum()//3));before=bar.value()
    history.update_message(history.bubbles[-1],'# Streaming report\n\n'+('More details\n\n'*100))
    history.flush_updates();QTest.qWait(80);app.processEvents()
    assert abs(bar.value()-before)<=5 and not history._follow_bottom
    history.close()


def test_large_window_bubble_uses_readable_cap_and_canvas_has_real_content(app):
    history=MessageHistory();history.resize(1800,900);history.show();app.processEvents()
    source='# Report\n\n'+'long report '*200
    bubble=history.append_message('model',source);received=[];history.report_requested.connect(received.append)
    app.processEvents();bubble.canvas_button.click()
    assert bubble.width()<=900 and bubble.width()>600 and received==[source]
    history.close()
