"""Behavior tests of the real search-first Qt panel; network is explicit fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import threading
from unittest.mock import patch
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget, QListView
from grangerpet.config import Settings
from grangerpet.engine import Result, SearchQuery, SearchSummary, SourceStatus
from grangerpet.panel import OsintPanel

@pytest.fixture(scope='module')
def app():
    value=QApplication.instance() or QApplication([])
    value.setQuitOnLastWindowClosed(False)
    value.setStyle('Fusion')
    for font in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
    value.setFont(QFont('Segoe UI',10))
    return value

@pytest.fixture
def panel(app, monkeypatch):
    monkeypatch.setattr('grangerpet.panel.get_secret',lambda name:'')
    monkeypatch.setattr('grangerpet.connections.get_secret',lambda name:'')
    monkeypatch.setattr('grangerpet.ai_keys.get_secret',lambda name:'')
    widget=OsintPanel(Settings())
    yield widget
    widget.shutdown();widget.deleteLater();app.processEvents()

def wait(app,predicate,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(10)
    pytest.fail('Qt task did not finish')

def test_canvas_uses_the_selected_profile_directory(panel, tmp_path):
    from grangerpet.config import SettingsStore
    panel.store = SettingsStore(tmp_path/'isolated'/'settings.json')
    panel.open_canvas('# Profile report\n\nStored beside this profile.')
    assert panel.canvas.directory == tmp_path/'isolated'/'canvas'
    panel.canvas.save_document()
    assert list((tmp_path/'isolated'/'canvas').glob('*.md'))


def test_main_window_is_search_first_resizable_and_settings_are_separate(panel,app,monkeypatch):
    panel.show();app.processEvents()
    assert panel.size().width()==760 and panel.size().height()==690
    assert (panel.minimumWidth(),panel.minimumHeight())==(460,420)
    assert panel.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert panel.windowType()==Qt.WindowType.Window
    assert panel.header.close_button.isVisible()
    assert isinstance(panel.results_view,QListView)
    assert panel.find.text()=='Найти'
    assert panel.text.isVisible() and panel.results_stack.height()>300
    assert not panel.settings_dialog.isVisible()
    assert not any(field.isVisibleTo(panel) for field in panel.connections.secret_fields.values())
    # Settings open as a separate native dialog; showing them does not reparent
    # their credential forms into the evidence viewport or change its geometry.
    monkeypatch.setattr(panel.settings_dialog,'refresh_readiness',lambda:None)
    before=panel.results_stack.geometry()
    panel.open_settings();app.processEvents()
    assert panel.settings_dialog.isVisible()
    assert panel.results_stack.geometry()==before
    assert panel.connections.tabs.count()==4
    panel.settings_dialog.close();app.processEvents()
    assert not panel.settings_dialog.isVisible()
    panel.resize(460,420);app.processEvents()
    assert panel.find.mapTo(panel,panel.find.rect().bottomRight()).y()<panel.height()
    assert panel.results_stack.height()>100

def test_solvnox_requires_current_query_clarification_before_any_source(panel,app,monkeypatch):
    called=[]
    monkeypatch.setattr(panel.controller,'start',lambda *args:called.append(args))
    panel.text.setText('solvnox');panel.start_search()
    assert panel.phase=='needs_clarification' and not called
    panel.choose_kind('username')
    assert panel._resolution().kind=='username'
    assert not panel._resolution().requires_clarification
    panel.text.setText('another-query')
    assert panel._resolution().requires_clarification
    assert panel.phase=='needs_clarification'
    panel.set_query_kind('username')
    panel.text.setText('third-query')
    assert panel._resolution().requires_clarification
    # IPC repeats the same chosen kind after a different query; the hidden
    # compatibility combo index may be unchanged but clarification must resolve.
    panel.set_query_kind('username')
    assert panel._resolution().kind=='username'
    assert not panel._resolution().requires_clarification

def test_execution_rows_are_not_findings_and_counter_matches_unique_evidence(panel,app):
    for source,state in (('maigret','complete'),('blackbird','empty'),('social_analyzer','complete')):
        panel._source_status(SourceStatus(source,state,label='Публичные профили'))
        panel._engine_result({'source':source,'state':state,'message':'Task finished'})
    assert panel.result_model.rowCount()==0 and panel.count_label.text()=='Найдено: 0'
    assert panel.results_stack.currentIndex()==0
    panel._engine_result(Result('alice','Alice','profile','GitHub','https://github.com/alice/',status='verified',sources=['maigret']))
    panel._engine_result(Result('alice','Alice','profile','GitHub','https://github.com/alice?utm_source=x',status='verified',sources=['blackbird']))
    assert panel.result_model.rowCount()==1
    assert len(next(iter(panel._records.values()))['sources'])==2
    assert panel.count_label.text()=='Найдено: 1'
    assert panel.diagnostics.isHidden()
    panel._engine_result(Result('uncertain','Possible fixture','profile','Example','https://example.org/possible',status='heuristic'))
    assert panel.result_model.rowCount()==2
    assert panel.count_label.text()=='Найдено: 1 · требуют проверки: 1'

def test_fixture_results_use_virtual_model_without_result_widgets(panel,app,monkeypatch):
    panel.show();app.processEvents()
    delegate=panel.results_view.itemDelegate()
    paint=delegate.paint
    painted=[]
    def record_paint(painter,option,index):
        painted.append(index.row())
        return paint(painter,option,index)
    monkeypatch.setattr(delegate,'paint',record_paint)
    before=len(panel.results_view.findChildren(QWidget))
    for index in range(1000):
        panel._engine_result(Result(str(index),f'Fixture {index}','profile','Example',f'https://example.org/profile/{index}',status='verified'))
    app.processEvents()
    assert panel.result_model.rowCount()==1000
    assert len(panel.results_view.findChildren(QWidget))-before<10
    assert panel.count_label.text()=='Найдено: 1000'
    assert '<' not in panel.result_model.data(panel.result_model.index(0,0))
    # Model size alone cannot catch an empty viewport captured before deferred
    # QListView batches finish. Verify the visible evidence actually paints.
    wait(app,lambda:0 in painted and panel.results_view.indexAt(QPoint(16,16)).isValid())
    image=panel.results_view.viewport().grab().toImage()
    assert sum(min(image.pixelColor(x,y).getRgb()[:3])>95
               for y in range(6,min(150,image.height()),2)
               for x in range(8,image.width()-8,2))>25


@pytest.mark.parametrize('width',[460,620])
def test_summary_captions_fit_with_uncertain_results_and_long_status(panel,app,width):
    panel.resize(width,420 if width==460 else 610)
    panel.show()
    panel.count_label.setText('Найдено: 123456 · требуют проверки: 123456')
    panel.status.setText('Часть источников недоступна · проверка неполная. Полученные сведения требуют проверки по исходным публичным страницам.')
    panel.status.show()
    panel._progress(11,12)
    app.processEvents();QTest.qWait(40)
    checked=panel.checked_label
    assert checked.fontMetrics().horizontalAdvance(checked.text())<=checked.contentsRect().width()
    assert checked.fontMetrics().height()<=checked.contentsRect().height()
    for label in (panel.count_label,panel.status):
        assert label.height()>=label.heightForWidth(label.width())
        assert panel.rect().contains(label.mapTo(panel,label.rect().bottomRight()))
    assert panel.results_stack.isVisible() and panel.results_stack.height()>0

def test_real_fixture_adapter_emits_records_asynchronously_and_finishes_without_status_rows(panel,app):
    threads=[]
    class Source:
        id,label,kinds='fixture','Explicit fixture source',('username',)
        def run(self,query,context):
            threads.append(threading.get_ident())
            value={'id':'profile','title':'<b>Fixture title</b>','type':'profile','platform':'Example',
                   'url':'https://example.org/alice','description':'<script>not markup</script>','status':'verified'}
            context.event({'event':'result','result':value})
            return {'status':'complete','results':[value]}
    panel.controller.adapters=[Source()]
    states=[];panel.search_state.connect(states.append)
    panel.text.setText('alice');panel.choose_kind('username');panel.start_search()
    assert panel.find.text()=='Остановить'
    wait(app,lambda:not panel._busy)
    assert panel.result_model.rowCount()==1
    assert panel.result_model.record(0)['title']=='<b>Fixture title</b>'
    assert threads and threads[0]!=threading.get_ident()
    assert panel.phase=='completed' and panel.find.text()=='Найти'
    assert panel.count_label.text()=='Найдено: 1'
    assert states.count('thinking')==states.count('working')==states.count('happy')==1

def test_google_browser_fallback_is_explicit_and_has_no_embedded_results(panel,app,monkeypatch):
    opened=[]
    monkeypatch.setattr('grangerpet.panel.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    states=[];panel.search_state.connect(states.append)
    panel.text.setText('site:example.org "public report"');panel.start_search()
    assert len(opened)==1 and opened[0].startswith('https://www.google.com/search?')
    assert states==['thinking','working','idle']
    assert panel.result_model.rowCount()==0
    assert 'фактическая выдача здесь недоступна' in panel.status.text()

def test_cancel_drops_late_old_generation_results_and_new_search_can_start(panel,app):
    class Source:
        id,label,kinds='waiting','Explicit fixture source',('username',)
        def run(self,query,context):
            if query.text=='first':
                context.cancelled.wait(2)
                return {'status':'complete','results':[{'id':'stale','title':'Old fixture','type':'profile','platform':'Example','url':'https://example.org/stale','status':'verified'}]}
            return {'status':'complete','results':[{'id':'fresh','title':'New fixture','type':'profile','platform':'Example','url':'https://example.org/fresh','status':'verified'}]}
    panel.controller.adapters=[Source()]
    panel.text.setText('first');panel.choose_kind('username');panel.start_search()
    old=panel._generation
    panel.cancel_search()
    panel.text.setText('second');panel.choose_kind('username');panel.start_search()
    wait(app,lambda:not panel._busy)
    # Even a queued event delivered after the new query must be ignored.
    panel._controller_event(old,'result',Result('stale','Old','profile','Example','https://example.org/stale'))
    assert [value['id']for value in panel._records.values()]==['fresh']
    assert panel.find.text()=='Найти'

def test_link_open_and_full_url_copy_do_not_interpret_html(panel,app,monkeypatch):
    address='https://example.org/'+('long-segment-'*30)+'?verified=yes'
    panel._engine_result(Result('long','<img onerror=alert(1)>','web','Example',address,'Fixture description',status='verified'))
    panel.results_view.setCurrentIndex(panel.result_model.index(0,0))
    opened=[];monkeypatch.setattr('grangerpet.panel.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    panel.open_selected();panel.copy_selected()
    assert opened==[address]
    assert QApplication.clipboard().text()==address


def test_three_email_services_fit_compactly_and_show_one_shared_caveat(panel,app):
    from grangerpet.result_view import compact_content
    panel.text.setText('fixture@example.invalid')
    panel.show();app.processEvents()
    for name in ('duolingo','diigo','gravatar'):
        panel._engine_result(Result(name+':fixture@example.invalid',name+' · fixture@example.invalid','email_check',name,
            description='Service registration fixture. Does not establish identity.',
            details={'email':'fixture@example.invalid'},status='registration_detected',sources=['holehe']))
    wait(app,lambda:panel.results_view.visualRect(panel.result_model.index(2,0)).height()>0)
    rect=panel.results_view.visualRect(panel.result_model.index(2,0))
    assert rect.bottom()<panel.results_view.viewport().height()
    assert panel.email_notice.isVisible()
    assert panel.email_notice.text()=='Регистрация не подтверждает личность владельца email.'
    for value in panel._records.values():
        lines=compact_content(value)
        assert len(lines)==2
        assert 'fixture@example.invalid'not in '\n'.join(text for text,role in lines)
    assert not panel.open_button.isVisible() and not panel.copy_button.isVisible() and not panel.details_button.isVisible()


def test_inline_source_arrow_opens_only_that_real_url_body_opens_details(panel,app,monkeypatch):
    opened=[]
    monkeypatch.setattr('grangerpet.panel.QDesktopServices.openUrl',lambda url:opened.append(url.toString())or True)
    panel._engine_result(Result('fixture','GitHub · fixture','profile','GitHub','https://github.com/fixture',status='detected'))
    panel.show();wait(app,lambda:panel.results_view.visualRect(panel.result_model.index(0,0)).height()>0)
    rect=panel.results_view.visualRect(panel.result_model.index(0,0))
    QTest.mouseClick(panel.results_view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(rect.right()-23,rect.center().y()))
    app.processEvents()
    assert opened==['https://github.com/fixture']
    assert not hasattr(panel,'details_dialog')
    QTest.qWait(170)
    QTest.mouseClick(panel.results_view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(30,rect.center().y()))
    app.processEvents()
    assert panel.details_dialog.isVisible()
    assert panel.details_dialog.fields['URL источника'].text()=='https://github.com/fixture'
    assert opened==['https://github.com/fixture']


def test_email_details_copy_full_field_without_inventing_a_profile_url(panel,app):
    from PySide6.QtWidgets import QToolButton
    email='fixture-long-name@example.invalid'
    panel._engine_result(Result('fixture:'+email,'Fixture · '+email,'email_check','Fixture',details={'email':email},status='registration_detected',sources=['holehe']))
    panel.results_view.setCurrentIndex(panel.result_model.index(0,0));panel.show_selected_details();app.processEvents()
    details=panel.details_dialog
    assert details.fields['Проверяемый email'].text()==email
    assert not details.open_button.isEnabled()
    assert 'URL источника'not in details.fields
    button=next(value for value in details.findChildren(QToolButton)if value.accessibleName()=='Копировать Проверяемый email')
    button.click();assert QApplication.clipboard().text()==email


def test_blockchain_summary_filters_real_fact_groups_without_mutating_results(panel,app):
    panel._query='0:'+('0'*64)
    for kind,status in (('transaction','verified'),('relationship','check'),('label','check')):
        panel._engine_result(Result(kind,'Fixture '+kind,kind,'Блокчейн · TON','https://tonviewer.com/'+panel._query,
            details={'direction':'in','amount':'0.1'}if kind=='transaction'else{},status=status))
    before=dict(panel._records)
    panel.show();app.processEvents()
    assert panel.blockchain_overview.isVisible()
    assert 'TON'in panel.blockchain_summary.text()and'3'in panel.blockchain_summary.text()
    assert 'требует проверки'in panel.attribution_summary.text()
    assert panel.fact_group.fontMetrics().horizontalAdvance(panel.fact_group.currentText())<panel.fact_group.width()-32
    panel.fact_group.setCurrentIndex(panel.fact_group.findData('transaction'));app.processEvents()
    assert not panel.results_view.isRowHidden(0)
    assert panel.results_view.isRowHidden(1)and panel.results_view.isRowHidden(2)
    assert panel._records==before
    panel.resize(460,420);app.processEvents()
    assert not panel.blockchain_address.isVisible()
    assert panel.results_stack.height()>50
    panel.show_chat();app.processEvents();panel.show_search();app.processEvents()
    assert panel._records==before


def test_custom_header_uses_native_qt_move_and_resize_apis(panel,app,monkeypatch):
    calls=[]
    class Handle:
        def startSystemMove(self):calls.append('move');return True
        def startSystemResize(self,edges):calls.append(edges);return True
    monkeypatch.setattr(panel,'windowHandle',lambda:Handle())
    panel.show();app.processEvents()
    QTest.mouseClick(panel.header,Qt.MouseButton.LeftButton,pos=QPoint(85,20))
    QTest.mouseClick(panel,Qt.MouseButton.LeftButton,pos=QPoint(2,2))
    assert calls[0]=='move'
    assert calls[1]&Qt.Edge.LeftEdge and calls[1]&Qt.Edge.TopEdge


def test_chat_terminal_state_and_search_priority_do_not_leave_thinking_stuck(panel,app,monkeypatch):
    monkeypatch.setattr('grangerpet.ai_keys.get_secret',lambda name:'fixture-key')
    class Client:
        def chat(self,*args,**kwargs):return 'Explicit fixture model response'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient',lambda:Client())
    panel.set_settings(Settings(ai_provider='deepseek',deepseek_model='deepseek-v4-flash'))
    states=[];panel.search_state.connect(states.append)
    panel.chat_widget.input.setPlainText('Fixture question');panel.chat_widget.send_message()
    wait(app,lambda:not panel.chat_widget._busy)
    assert states[0]=='thinking'and states[-1]=='happy'
    panel._busy=True
    panel.chat_widget.input.setPlainText('Second fixture question');panel.chat_widget.send_message()
    wait(app,lambda:not panel.chat_widget._busy)
    assert states[-1]=='working'
    panel._busy=False;panel._emit_activity('idle')
    assert states[-1]=='idle'


def test_full_long_values_remain_copyable_without_horizontal_details_overflow(panel,app):
    from PySide6.QtWidgets import QScrollArea
    title='ТЕСТОВОЕ ИМЯ '+('оченьдлинноеназвание'*50)
    url='https://example.invalid/'+('a'*700)
    panel._engine_result(Result('fixture',title,'profile','Fixture',url,status='verified'))
    panel.results_view.setCurrentIndex(panel.result_model.index(0,0));panel.show_selected_details()
    dialog=panel.details_dialog;dialog.resize(400,300);app.processEvents()
    area=dialog.findChild(QScrollArea)
    assert dialog.fields['Название'].text()==panel.result_model.record(0)['title']
    assert dialog.fields['URL источника'].text()==url
    assert area.horizontalScrollBar().maximum()==0


def test_hidden_chat_height_for_width_does_not_force_native_search_height(panel,app):
    panel.show();app.processEvents()
    panel.show_chat();app.processEvents();panel.show_search();app.processEvents()
    assert not panel.mode_tabs.hasHeightForWidth()
    assert panel.mode_tabs.heightForWidth(460) == -1
    panel.resize(460,420);app.processEvents()
    assert (panel.width(),panel.height()) == (460,420)


def test_blockchain_row_shows_source_transaction_hash_instead_of_internal_index_id():
    from grangerpet.result_view import compact_content
    record = {'id':'transaction:ton:internal-event-id', 'title':'actual-source-hash',
              'type':'transaction', 'platform':'TON', 'status':'verified',
              'details':{'tx_hash':'a'*64, 'amount':'1', 'asset':'TON', 'direction':'in'}}
    lines = compact_content(record)
    assert lines[-1][0] == 'a'*64
    assert 'internal-event-id' not in str(lines)


def test_compact_header_short_modes_and_single_query_action_row(panel,app):
    panel.show();app.processEvents()
    assert panel.header.height()==54
    assert [panel.mode_tabs.tabText(i) for i in range(panel.mode_tabs.count())]==['Поиск','Гермиона']
    query_y=panel.text.mapTo(panel,panel.text.rect().center()).y()
    button_y=panel.find.mapTo(panel,panel.find.rect().center()).y()
    assert abs(query_y-button_y)<=1
    assert panel.detection.mapTo(panel,panel.detection.rect().topLeft()).y()>query_y


def test_tab_indicator_and_result_transitions_are_bounded_and_reduce_motion(panel,app,monkeypatch):
    from grangerpet.panel import NavigationTabBar
    panel.show();app.processEvents()
    bar=panel.mode_tabs.tabBar()
    assert isinstance(bar,NavigationTabBar)
    assert bar._animation.duration()==160
    monkeypatch.setattr('grangerpet.panel.reduced_motion',lambda:True)
    panel.show_chat();app.processEvents()
    assert bar._indicator==bar._target()
    panel.show_search()
    for row in range(10):
        panel._engine_result(Result(str(row),'Fixture','profile','GitHub',f'https://example.invalid/{row}'))
    delegate=panel.results_view.itemDelegate()
    monkeypatch.setattr('grangerpet.result_view.reduced_motion',lambda:True)
    delegate._transition('hover',2)
    delegate._transition('selection',3)
    assert delegate._hover_values=={2:1.0}
    assert delegate._selection_values=={3:1.0}
    assert delegate._hover_animation.duration()==120
