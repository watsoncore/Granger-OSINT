"""Real Qt controllers behind the finite renderer protocol; no live API claims."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import pytest
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest

from grangerpet.config import Settings, SettingsStore
from grangerpet.panel import OsintPanel
from grangerpet.desktop_bridge import DesktopBridge
from grangerpet.desktop_surface import bundled_url
from grangerpet.chat_archive import ChatArchive
from grangerpet.conversations import ConversationLibrary


@pytest.fixture
def bridge(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    for module in ('grangerpet.panel','grangerpet.connections','grangerpet.ai_keys'):
        monkeypatch.setattr(module+'.get_secret',lambda name:'')
    monkeypatch.setattr('grangerpet.desktop_bridge.resolve_deepseek_key',lambda:'')
    host=OsintPanel(Settings(),SettingsStore(tmp_path/'settings.json'))
    value=DesktopBridge(host)
    yield value
    value.shutdown();host.shutdown();host.deleteLater();app.processEvents()


def test_bridge_reports_only_actual_sources_and_no_secret_settings(bridge):
    bridge.host.chat_widget._append('model','# Actual stored fixture')
    bridge.host._agent_evidence([{'evidence_id':'ev_'+'a'*20,'id':'fixture','title':'Known fixture page','url':'https://example.org/',
        'type':'web','platform':'Example','description':'Fixture body','details':{'reading_method':'direct_http'},'status':'verified'}])
    snapshot=ready_sources(bridge)
    assert snapshot['messages'][-1]['text']=='# Actual stored fixture'
    assert snapshot['evidence'][0]['kind']=='page'
    assert 'api_key' not in snapshot['settings'] and snapshot['connection']['balance'] is None
    assert snapshot['usage']['balance']['status']=='not_supported'


def test_catalog_candidates_are_not_exposed_as_working_tools(bridge):
    bridge._tools=[{'id':'web_read','available':True,'implemented':True,'state':'ready_local'}]
    first=bridge.snapshot()
    for _ in range(5): assert bridge.snapshot()['tools']==first['tools'] and len(first['tools'])==1
    assert len(bridge._tools)==1
    from grangerpet.agent_tools import _SPECS
    assert first['tool_counts']=={'candidates':0,'implemented':len(_SPECS),'ready_local':1,'verified_execution':0}
    assert all(row.get('implemented') is not False for row in first['tools'])


def test_attachment_snapshots_are_not_aliased_to_later_imports(bridge):
    before=bridge.snapshot()
    bridge._attachments.append({'id':'img_'+'a'*64,'name':'Тест.png'})
    after=bridge.snapshot()
    assert before['attachments']==[] and len(after['attachments'])==1


def test_model_settings_distinguish_download_extract_probe_and_remove(bridge):
    bridge._visual_job=object()
    try:
        bridge._visual_operation='visual_install';bridge._visual_progress={'artifact':'weights','bytes':10,'total_bytes':100}
        assert bridge.snapshot()['visual_models']['state']=='downloading'
        bridge._visual_progress={'phase':'extracting'}
        assert bridge.snapshot()['visual_models']['state']=='installing'
        bridge._visual_operation='visual_probe'
        assert bridge.snapshot()['visual_models']['state']=='loading'
        bridge._visual_operation='visual_remove'
        assert bridge.snapshot()['visual_models']['state']=='removing'
    finally:bridge._visual_job=None


def test_finite_actions_reject_arbitrary_paths_commands_and_secret_fields(bridge,tmp_path):
    for action,payload in [('shell',{'command':'whoami'}),('settings_save',{'values':{'api_key':'forbidden'}}),
        ('open_url',{'url':'file:///C:/Windows/win.ini'}),('open_url',{'url':'javascript:alert(1)'}),
        ('history_load',{'id':'../../outside'}),('tool_run',{'tool':'cmd','query':'whoami'})]:
        with pytest.raises((ValueError,KeyError)):bridge.dispatch(action,payload)
    assert not list(tmp_path.glob('outside*'))


def test_canvas_edit_rejects_stale_document_and_keeps_evidence(bridge):
    row=bridge.host.chat_widget._append('model','# Current report\n\nOriginal')
    identifier=bridge.host.chat_widget.messages[-1]['id']
    bridge.dispatch('canvas_open',{'message_id':identifier})
    canvas=bridge.host.canvas
    with pytest.raises(ValueError):bridge.dispatch('canvas_edit',{'document_id':'wrong','text':'Overwrite'})
    assert 'Original' in canvas.editor.toPlainText()
    bridge.dispatch('canvas_edit',{'document_id':canvas.document_id,'text':'# Edited report'})
    bridge.dispatch('canvas_save',{})
    assert canvas.editor.toPlainText()=='# Edited report'
    assert bridge.host.chat_widget.messages[-1]['text']=='# Current report\n\nOriginal'


def test_stream_delta_transmits_one_changed_message(bridge):
    chat=bridge.host.chat_widget
    chat._append('user','Question');chat._append('model','Initial')
    values=[];bridge.stateChanged.connect(values.append)
    bridge.publish(force=True);chat.messages[-1]['text']='Initial streaming extension';bridge.publish()
    update=json.loads(values[-1])
    assert 'messages' not in update
    assert update['message_updates']==[{'index':1,'message':{**chat.messages[-1],'streaming':False,'sources':[]}}]


def test_completed_manual_tool_is_published_after_running_snapshot(bridge):
    bridge._manual_activity=[{'id':'web_read','tool':'Чтение страниц','status':'running','summary':'Запрос пользователя'}]
    patches=[]
    bridge.stateChanged.connect(lambda raw:patches.append(json.loads(raw)))
    bridge.publish(force=True)
    bridge._manual_activity[0].update(status='partial',summary='Источник ограничил доступ',resultCount=0)
    bridge.publish()
    assert patches[0]['activity'][0]['status']=='running'
    assert patches[-1]['patch'] is True
    assert patches[-1]['activity'][0]['status']=='partial'
    assert patches[-1]['activity'][0]['resultCount']==0


def test_idle_bridge_does_not_rebuild_snapshots_on_a_poll_timer(bridge,monkeypatch):
    snapshots=[]
    original=bridge.snapshot
    monkeypatch.setattr(bridge,'snapshot',lambda:(snapshots.append(True),original())[1])
    bridge._flush.stop()
    QTest.qWait(1450)
    assert snapshots==[]


def test_hidden_renderer_defers_updates_but_keeps_chat_and_archive_timer_running(bridge):
    packets=[]
    bridge.stateChanged.connect(lambda value:packets.append(json.loads(value)))
    bridge.publish(force=True)
    packets.clear()
    bridge.set_publication_visible(False)
    bridge.host.chat_widget._append('model','Finished while the renderer is hidden')
    QTest.qWait(150)
    assert packets==[] and not bridge._flush.isActive()
    assert bridge.host.chat_widget._archive_timer.isActive()
    assert bridge.host.chat_widget.messages[-1]['text']=='Finished while the renderer is hidden'
    bridge.set_publication_visible(True)
    QTest.qWait(150)
    assert len(packets)==1 and packets[0]['patch'] is False
    assert packets[0]['messages'][-1]['text']=='Finished while the renderer is hidden'


def test_usage_read_cache_invalidates_after_a_real_committed_request(bridge,monkeypatch):
    chat=bridge.host.chat_widget
    calls=[]
    ledger=chat._usage_ledger
    original=ledger.snapshot
    monkeypatch.setattr(ledger,'snapshot',lambda **values:(calls.append(values),original(**values))[1])
    first=bridge.snapshot()['usage']['conversation']
    for _ in range(3):assert bridge.snapshot()['usage']['conversation']==first
    assert len(calls)==1
    ledger.record_response({'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13}},conversation_id=chat.conversation_id)
    assert bridge.snapshot()['usage']['conversation']['total_tokens']==13
    assert len(calls)==2


def test_saved_history_title_is_published_without_periodic_polling(bridge):
    packets=[]
    bridge.stateChanged.connect(lambda value:packets.append(json.loads(value)))
    assert bridge.snapshot()['history']==[]
    bridge.host.chat_widget._append('user','Новый сохранённый разговор')
    QTest.qWait(1000)
    assert bridge.snapshot()['history'][0]['title']=='Новый сохранённый разговор'
    assert any(row.get('history',[{}])[0].get('title')=='Новый сохранённый разговор' for row in packets if row.get('history'))


def test_controller_progress_and_window_activation_are_event_driven(bridge):
    bridge._flush.stop()
    bridge.host.controller.search_event.emit(1,'progress',(1,3))
    assert bridge._flush.isActive()
    bridge._flush.stop()
    bridge.host.show()
    QApplication.instance().processEvents()
    assert bridge._publication_enabled and bridge._flush.isActive()
    bridge.host.showMinimized()
    QApplication.instance().processEvents()
    assert not bridge._publication_enabled and not bridge._flush.isActive()
    bridge.host.showNormal()
    QApplication.instance().processEvents()
    assert bridge._publication_enabled


def test_asset_origin_cannot_escape_bundle_or_load_remote_content(tmp_path):
    (tmp_path/'index.html').write_text('<html/>')
    assert bundled_url(QUrl('granger://app/index.html'),tmp_path)
    assert bundled_url(QUrl('qrc:///qtwebchannel/qwebchannel.js'),tmp_path)
    for url in ('file:///C:/Windows/win.ini','https://example.org/','granger://attacker/index.html',
                'granger://app/../../Windows/win.ini','qrc:///unrelated/script.js'):
        assert not bundled_url(QUrl(url),tmp_path)


def test_legacy_archive_is_preserved_when_starting_and_switching_conversations(tmp_path):
    archive=ChatArchive(tmp_path/'chat-history.dpapi')
    archive.save([{'role':'user','text':'Первый разговор'},{'role':'model','text':'Первый ответ'}],[])
    original=archive.path.read_bytes();library=ConversationLibrary(archive);first=library.current_id
    second=library.new()
    assert first!=second and (tmp_path/'conversations'/f'{first}.dpapi').read_bytes()==original
    archive.save([{'role':'user','text':'Второй разговор'}],[]);library.seal()
    assert library.load(first)['messages'][0]['text']=='Первый разговор'
    assert library.load(second)['messages'][0]['text']=='Второй разговор'
    assert len(library.list())==2
    assert b'conversation' not in original and 'Первый разговор'.encode() not in original


def test_search_preserves_browser_fallback_errors_and_numeric_progress(bridge):
    host=bridge.host
    host.phase='completed_empty'
    host.status.setText('Поиск открыт в браузере. Фактическая выдача здесь недоступна.')
    host.checked_label.setText('Проверено: 3/12')
    state=bridge.snapshot()['search']
    assert state['status']==host.status.text() and state['error']==''
    assert state['checked']==3 and state['checkedLabel']=='Проверено: 3/12'
    for phase in ('failed','completed_with_errors'):
        host.phase=phase;host.status.setText('Источник недоступен')
        assert bridge.snapshot()['search']['error']=='Источник недоступен'


def test_existing_dork_builder_stays_connected_to_search(bridge):
    bridge.dispatch('search_dorks',{'query':'открытые источники'})
    dialog=bridge.host.dork_dialog
    assert dialog.isVisible() and dialog.text.text()=='открытые источники'
    dialog.query_selected.emit('site:example.org "источники"')
    assert bridge.snapshot()['search']['query']=='site:example.org "источники"'
    assert bridge.host._chosen_kind=='dork'
    dialog.hide()


def test_new_search_does_not_relabel_old_chat_evidence_as_its_results(bridge):
    from grangerpet.agent_evidence import normalize_evidence
    record=normalize_evidence({'id':'saved','title':'Earlier investigation page',
        'url':'https://example.org/old','type':'web','platform':'Example','description':'Earlier evidence',
        'details':{'reading_method':'direct_http'},'status':'verified'}, 'web_read', 'https://example.org/old')
    bridge.host.chat_widget._last_investigation={'id':'c'*32,'evidence':[record]}
    bridge.host._agent_evidence([record])
    assert ready_sources(bridge)['search']['results']
    bridge.host.result_model.clear()
    bridge.host.text.setText('site:example.net new query')
    bridge.host.phase='completed_empty'
    snapshot=ready_sources(bridge)
    assert snapshot['search']['results']==[]
    assert snapshot['evidence'][0]['evidence_id']==record['evidence_id']


def wait_until(predicate,timeout=3000):
    deadline=time.monotonic()+timeout/1000
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents();QTest.qWait(10)
    assert predicate()


def test_readiness_starts_automatically_and_keeps_progress_diagnostics(bridge,monkeypatch):
    calls=[]
    def catalog(**kwargs):
        calls.append(kwargs['force_refresh'])
        row={'name':'web_read','kind':'web','description':'Reader','available':True,'state':'ready',
            'reason':'Локальный транспорт проверен','diagnostic':{'code':'local_ready','remedy':'','execution_verified':False}}
        kwargs['on_update'](row)
        return [row]
    monkeypatch.setattr(bridge._registry(),'catalog',catalog)
    bridge.dispatch('ui_ready',{'surface':'main'})
    wait_until(lambda:bool(bridge._tools) and bridge._tools_job is None)
    assert calls==[False]
    row=bridge.snapshot()['tools'][0]
    assert row['available'] and row['diagnostic']['execution_verified'] is False
    assert bridge.snapshot()['toolsChecking'] is False


def test_modern_settings_keep_non_secret_values_and_reject_key_fields(bridge):
    bridge.dispatch('settings_save',{'values':{'ai_provider':'none','request_limit':12,'source_root':'C:/fixture','enable_snoop':True}})
    state=bridge.snapshot()
    assert state['settings']['request_limit']==12 and state['settings']['enable_snoop']
    assert isinstance(state['credentials']['vk'],bool)
    for key in ('vk_token','deepseek_api_key','telegram_session'):
        with pytest.raises(ValueError): bridge.dispatch('settings_save',{'values':{key:'secret'}})
    bridge.dispatch('settings_native',{'category':'tools'})
    assert bridge.route=='settings' and bridge.settingsCategory=='tools'
    assert not bridge.host.settings_dialog.isVisible()


def test_all_vault_secrets_are_redacted_from_json_not_only_ai_key(bridge):
    bridge._secret_redactions={'vk-secret','line\nsecret'}
    result=json.loads(bridge._json({'a':'vk-secret','b':'line\nsecret'}))
    assert result=={'a':'[скрытый ключ]','b':'[скрытый ключ]'}


def test_balance_refresh_is_separate_from_chat_connection_and_usage(bridge,monkeypatch):
    monkeypatch.setattr('grangerpet.desktop_bridge.fetch_balance',lambda key:{'status':'available','amount':'7',
        'unit':'gateway_units','label':'Единицы шлюза','updated_at':'time'})
    bridge.host.settings.ai_provider='deepseek'
    before=bridge.host.ai_state.committed_snapshot()
    bridge.dispatch('balance_refresh',{})
    wait_until(lambda:bridge._balance_job is None)
    assert bridge.snapshot()['usage']['balance']['amount']=='7'
    assert bridge.host.ai_state.committed_snapshot()==before


def test_avito_opens_only_explicit_search_and_never_claims_machine_results(bridge,monkeypatch):
    opened=[]
    monkeypatch.setattr('grangerpet.desktop_bridge.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    result=bridge.dispatch('public_search_open',{'source':'avito','query':'тест и пробел'})
    assert result['opened'] and result['machine_results'] is False
    assert 'q=' in opened[0] and 'api.' not in opened[0]
    with pytest.raises(ValueError): bridge.dispatch('public_search_open',{'source':'comb','query':'anything'})


def test_model_metadata_list_is_async_local_only_and_does_not_verify_chat(bridge,monkeypatch):
    with pytest.raises(ValueError):bridge.dispatch('connection_models',{})
    bridge.host.settings.ai_provider='ollama'
    before=bridge.host.ai_state.committed_snapshot()
    monkeypatch.setattr('grangerpet.ai.OllamaClient.list_models',lambda self:['fixture-local-model'])
    bridge.dispatch('connection_models',{})
    wait_until(lambda:bridge._models_job is None)
    assert bridge.snapshot()['connection']['models']==[{'id':'fixture-local-model'}]
    assert bridge.host.ai_state.committed_snapshot()==before


@pytest.mark.parametrize(('tool','query','expected'),[('web_read','https://example.org/',20),('web_search','fixture query',10)])
def test_catalog_run_clamps_default_from_legitimate_search_setting(bridge,monkeypatch,tool,query,expected):
    bridge.host.settings.request_limit=50
    received=[]
    registry=bridge._registry()
    monkeypatch.setattr(registry,'execute',lambda name,args,**kw:received.append(args['limit']) or {'status':'empty','results':[]})
    monkeypatch.setattr(bridge,'_refresh_tools',lambda **kw:None)
    bridge.dispatch('tool_run',{'tool':tool,'query':query})
    wait_until(lambda:bridge._manual_job is None)
    assert received==[expected]


def test_queued_cancelled_tool_result_cannot_overwrite_next_job(bridge,monkeypatch):
    monkeypatch.setattr('grangerpet.desktop_bridge.UiJob.start',lambda self:None)
    bridge.dispatch('tool_run',{'tool':'web_read','query':'https://example.org/'})
    old=bridge._manual_job
    bridge.dispatch('search_stop',{})
    bridge.dispatch('tool_run',{'tool':'web_read','query':'https://example.net/'})
    new=bridge._manual_job
    old.done.emit({'status':'complete','results':[]},'')
    assert bridge._manual_job is new
    assert bridge._manual_activity[0]['status']=='running'


def test_manual_timeout_keeps_streamed_observations_and_truthful_incomplete_status(bridge,monkeypatch):
    from grangerpet.agent_evidence import normalize_evidence
    row=normalize_evidence({'id':'partial','type':'web','title':'Observed before timeout',
        'url':'https://example.org/','platform':'Fixture','details':{},'description':'Actual retained fixture observation'},
        'web_read','https://example.org/')
    registry=bridge._registry()
    monkeypatch.setattr(registry,'execute',lambda *a,**kw:{'tool':'web_read','status':'timeout','query':'https://example.org/',
        'results':[row],'limitations':['Source timed out after the observed row.']})
    monkeypatch.setattr(bridge,'_refresh_tools',lambda **kw:None)
    bridge.dispatch('tool_run',{'tool':'web_read','query':'https://example.org/'})
    wait_until(lambda:bridge._manual_job is None)
    state=ready_sources(bridge)
    assert state['search']['phase']=='completed_with_errors'
    assert state['search']['results'][0]['evidence_id']==row['evidence_id']
    assert state['activity'][-1]['status']=='timeout'
    assert state['search']['investigation_id']


def test_real_manual_result_keeps_evidence_identity_through_qt_model_and_renderer(bridge,monkeypatch):
    from grangerpet.agent_evidence import normalize_evidence
    record=normalize_evidence({'id':'https://example.org/','title':'Example','type':'web','platform':'example.org',
        'url':'https://example.org/','description':'Primary text','status':'verified','details':{'reading_method':'direct_http'}},
        'web_read','https://example.org/')
    bridge.host._agent_evidence([record])
    source=ready_sources(bridge)['search']['results'][0]
    assert source['evidence_id']==record['evidence_id']
    assert bridge.dispatch('source_open',{'evidence_id':source['evidence_id']})['evidence_id']==record['evidence_id']
    bridge._manual_registry=None
    registry=bridge._registry()
    monkeypatch.setattr(bridge,'_refresh_tools',lambda **kw:None)
    bridge.dispatch('tool_run',{'tool':'evidence_get','query':source['evidence_id'],'limit':1})
    wait_until(lambda:bridge._manual_job is None)
    assert bridge._manual_activity[-1]['status']=='complete'
    assert ready_sources(bridge)['search']['results'][0]['evidence_id']==record['evidence_id']
    assert registry.evidence.get(record['evidence_id'])['provenance']['tool']=='web_read'


def test_flattened_conflict_is_never_promoted_when_sources_are_reconstructed(bridge):
    from grangerpet.agent_evidence import normalize_evidence
    row=normalize_evidence({'id':'https://example.org/','title':'Conflict fixture','url':'https://example.org/',
        'type':'web','platform':'example.org','status':'verified'},'web_read','https://example.org/')
    row['verification']='contradictory'
    bridge.host._agent_evidence([row])
    assert ready_sources(bridge)['search']['results'][0]['verification']=='contradictory'


def ready_sources(bridge):
    bridge.snapshot()
    wait_until(lambda:bridge._source_job is None)
    return bridge.snapshot()
