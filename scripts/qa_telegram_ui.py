"""Actual Qt screenshots with explicit local fixtures, isolated vault and no API.

Native mode uses the current Windows DPI. Offscreen scale factors simulate Qt
layout at 100/125/150%; they do not alter the Windows display setting.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/agent-qa'
FAKE_KEY = 'EXPLICIT-LOCAL-UI-FIXTURE-NOT-AN-API-KEY'
TON = 'EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c'


def hashes():
    paths = list((ROOT/'grangerpet/assets').glob('*')) + list((ROOT/'grangerpet/engine').rglob('*.py'))
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file() and '__pycache__' not in path.parts}


def child(native, factor, label):
    if native:
        os.environ.pop('QT_QPA_PLATFORM', None)
    else:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    if factor == 1:
        os.environ.pop('QT_SCALE_FACTOR', None)
    else:
        os.environ['QT_SCALE_FACTOR'] = str(factor)
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QFontDatabase, QFontInfo, QFontMetrics, QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QWidget
    from grangerpet.ai import AIError
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.engine import Result, SourceExecution
    from grangerpet.panel import OsintPanel
    from grangerpet.theme import STYLE
    from grangerpet.typography import apply_app_font
    folder = OUT/label
    if folder.exists():
        folder = OUT/(label+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    folder.mkdir(parents=True)
    before = hashes()
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
              'mode': 'native Windows Qt' if native else 'offscreen Qt',
              'qt_scale_factor': factor, 'fixture_content': 'ТЕСТОВЫЕ ДАННЫЕ · isolated local UI/source/AI responses; not real gateway/account findings',
              'real_api_called': False, 'real_credentials_read_or_written': False,
              'checks': [], 'captures': [], 'protected_before': before}
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    if not native:
        for name in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf','SegUIVar.ttf'):
            font = Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
    apply_app_font(app)
    app.setStyleSheet(STYLE)
    original_clipboard = app.clipboard().text()
    panel, reopened = None, None
    vault, calls, opened = {}, [], []
    waiting, release = threading.Event(), threading.Event()

    def check(name, condition, detail=None):
        report['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError(name + (': '+str(detail) if detail is not None else ''))

    def wait(predicate, timeout=4):
        end = time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(12)
        return False

    def settle():
        app.processEvents()
        QTest.qWait(190)
        app.processEvents()

    def capture(name, widget=None):
        widget = widget or panel
        settle()
        if widget is panel and panel.results_view.isVisible() and panel.result_model.rowCount():
            check('visible_rows_'+name, wait(lambda: panel.results_view.indexAt(QPoint(16,16)).isValid()))
        check('capture_'+name, widget.grab().save(str(folder/(name+'.png'))))
        report['captures'].append(name+'.png')

    def fake_key(override=None, **kwargs):
        return override.strip() if isinstance(override,str) and override.strip() else vault.get('deepseek_api_key','')

    class FakeDeepSeek:
        mode = 'success'
        def __init__(self, *args, **kwargs):
            self.last_response_metadata = {'model': 'deepseek-v4-flash', 'model_version': 'EXPLICIT-UI-FIXTURE'}
        def test_connection(self, model, *, cancel_event=None):
            calls.append({'kind':'explicit-local-check-fixture','model':model})
            return {'connected':True,'model':model,'text':'ТЕСТОВЫЕ ДАННЫЕ · API не вызывался'}
        def chat(self, model, messages, *, cancel_event=None):
            mode = self.mode
            calls.append({'kind':'explicit-local-chat-fixture','model':model,'message_count':len(messages),'mode':mode})
            if mode == 'waiting':
                waiting.set()
                while not release.wait(.02):
                    if cancel_event is not None and cancel_event.is_set():
                        raise AIError('Cancelled local fixture',code='cancelled')
            if mode == 'quota':
                raise AIError('Explicit quota fixture',code='quota',http_status=429,retry_after=.3)
            if mode == 'auth':
                raise AIError('Explicit authentication fixture',code='auth',http_status=401)
            return ('ТЕСТОВЫЙ ОТВЕТ · это локальная подстановка для проверки интерфейса. '
                    'Настоящий DeepSeek API здесь не вызывался.\n\n'
                    'Совпадение никнеймов не подтверждает общего владельца.\n'
                    '1. Проверьте исходный публичный URL.\n2. Отдельно оцените неопределённость.')

    try:
        with tempfile.TemporaryDirectory(prefix='GrangerPet-Telegram-UI-fixtures-') as temporary, ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'DEEPSEEK_API_KEY':'','DEEPSEEK_MODEL':''}))
            for module in ('grangerpet.credentials','grangerpet.connections','grangerpet.panel','grangerpet.ai_keys'):
                stack.enter_context(patch(module+'.get_secret',side_effect=lambda name:vault.get(name,'')))
            for module in ('grangerpet.credentials','grangerpet.connections'):
                stack.enter_context(patch(module+'.set_secret',side_effect=lambda name,value:vault.__setitem__(name,value)))
                stack.enter_context(patch(module+'.delete_secret',side_effect=lambda name:vault.pop(name,None)))
            for module in ('grangerpet.ai_keys','grangerpet.ai_state','grangerpet.connections','grangerpet.chat'):
                stack.enter_context(patch(module+'.resolve_deepseek_key',side_effect=fake_key))
            stack.enter_context(patch('grangerpet.connections.deepseek_key_source',side_effect=lambda:'windows' if vault.get('deepseek_api_key') else 'missing'))
            stack.enter_context(patch('grangerpet.connections.DeepSeekClient',FakeDeepSeek))
            stack.enter_context(patch('grangerpet.chat.DeepSeekClient',FakeDeepSeek))
            stack.enter_context(patch('grangerpet.settings_dialog.SettingsDialog.refresh_readiness',return_value=None))
            stack.enter_context(patch('grangerpet.engine.controller.SearchController.start',side_effect=AssertionError('Fixture harness cannot start network sources')))
            stack.enter_context(patch('grangerpet.panel.QDesktopServices.openUrl',side_effect=lambda url:opened.append(url.toString()) or True))
            stack.enter_context(patch('grangerpet.settings_dialog.SettingsDialog.ask_unsaved_changes',return_value=QMessageBox.StandardButton.Discard))
            store = SettingsStore(Path(temporary)/'settings.json')
            store.save(Settings())
            panel = OsintPanel(store.load(),store)
            panel.show();panel.show_chat();settle()
            chat = panel.chat_widget
            report['qt_platform'] = app.platformName()
            report['actual_device_pixel_ratio'] = panel.devicePixelRatioF()
            info = QFontInfo(chat.input.font())
            report['typography'] = {'family':info.family(),'pixel_size':info.pixelSize(),
                                    'cyrillic_supported':QFontMetrics(chat.input.font()).inFontUcs4(ord('Ж'))}
            check('font_size_14',info.pixelSize()==14,report['typography'])
            check('cyrillic_supported',report['typography']['cyrillic_supported'])
            check('native_compact_header',panel.header.height()==54)
            check('initial_620x610',(panel.width(),panel.height())==(620,610))
            check('minimum_460x420',(panel.minimumWidth(),panel.minimumHeight())==(460,420))
            check('one_shared_state',panel.ai_state is chat.ai_state is panel.connections.ai_state)
            check('new_user_not_configured',panel.ai_state.snapshot()['connection_status']=='not_configured')
            check('no_automatic_api_call',not calls)
            check('empty_chat_not_textedit',chat.history.__class__.__name__=='MessageHistory' and not chat.messages)
            check('composer_initial_46',chat.input.height()==46,chat.input.height())
            capture('A-empty-chat')
            chat.input.setPlainText('Черновик сохранится после настройки')
            panel.open_settings('ИИ')
            pane = panel.connections
            pane.provider.setCurrentIndex(pane.provider.findData('deepseek'))
            pane.deepseek_key.setText(FAKE_KEY)
            check('key_masked',pane.deepseek_key.echoMode()==QLineEdit.EchoMode.Password)
            pane.check.click()
            check('check_finished',wait(lambda:not pane._jobs))
            check('verified_unsaved_is_truthful',panel.ai_state.snapshot()['connection_status']=='verified_unsaved')
            check('unsaved_chat_still_disabled',not chat.send.isEnabled())
            check('shared_unsaved_status',chat.provider_status.text()==pane.ai_status.text() and 'Сохраните' in chat.provider_status.text())
            pane.status.setText('ТЕСТОВЫЕ ДАННЫЕ · локальная подстановка API')
            capture('B-settings-verified-unsaved',panel.settings_dialog)
            pane.save_button.click();app.processEvents()
            check('save_commits_connected',panel.ai_state.snapshot()['connection_status']=='connected')
            check('open_chat_immediately_enabled',chat.send.isEnabled())
            check('shared_connected_status',chat.provider_status.text()==pane.ai_status.text())
            check('exact_model_id',pane.selected_model()=='deepseek-v4-flash')
            check('saved_key_not_json',FAKE_KEY not in store.path.read_text(encoding='utf-8'))
            check('key_cleared_after_save',not pane.deepseek_key.text())
            pane.status.setText('ТЕСТОВЫЕ ДАННЫЕ · успешный ответ подстановки, не настоящий API')
            capture('B-settings-connected-fixture',panel.settings_dialog)
            panel.settings_dialog.done_button.click();app.processEvents()
            check('settings_closed_without_reset',not panel.settings_dialog.isVisible() and chat.input.toPlainText()=='Черновик сохранится после настройки')

            # Real application send callbacks and workers, with explicitly fake SDK.
            chat.input.setPlainText('ТЕСТОВЫЙ ДИАЛОГ · Привет, Гермиона!')
            chat.send.click();check('chat_reply_delivered',wait(lambda:not chat.busy and len(chat.messages)>=2))
            check('two_bubbles_created',len(chat.history.bubbles)==2)
            user, model = chat.history.bubbles[:2]
            check('short_user_bubble_right',user.parentWidget().layout().indexOf(user)==1)
            check('hermione_bubble_left',model.parentWidget().layout().indexOf(model)==0)
            check('bubbles_bounded_width',all(b.width()<=chat.history.viewport().width()*.82 for b in (user,model)))
            check('fixture_label_visible','ТЕСТОВЫЙ ОТВЕТ' in chat.history.toPlainText())
            capture('C-chat-fixture-bubbles')
            old_records=deepcopy(panel._records)
            panel.show_search();panel.show_chat();check('tab_preserves_history',len(chat.messages)==2 and panel._records==old_records)

            FakeDeepSeek.mode='waiting';waiting.clear();release.clear()
            chat.input.setPlainText('ТЕСТОВОЕ ожидание · ответ ещё не пришёл')
            chat.send.click();check('actual_worker_waiting',wait(waiting.is_set))
            check('typing_indicator_while_busy',chat.busy and chat.status.isVisible() and 'Печатает' in chat.status.text())
            capture('D-chat-waiting-fixture')
            chat.input.setPlainText('Черновик во время ожидания')
            chat.cancel();release.set();FakeDeepSeek.mode='success';settle()
            check('cancel_keeps_draft',chat.input.toPlainText()=='Черновик во время ожидания' and not chat.busy)
            check('cancel_preserves_history',len(chat.messages)>=4)

            FakeDeepSeek.mode='quota';chat.input.setPlainText('ТЕСТОВАЯ ошибка квоты 429');chat.send.click()
            check('quota_fixture_delivered',wait(lambda:not chat.busy))
            check('quota_state_shared',panel.ai_state.snapshot()['connection_status']=='quota_exceeded' and pane.ai_status.text()==chat.provider_status.text())
            check('retry_does_not_auto_send',calls[-1]['mode']=='quota')
            capture('E-chat-quota-fixture')
            retry=chat.history.bubbles[-1].retry
            check('manual_retry_available',wait(retry.isEnabled))
            count=len(calls);FakeDeepSeek.mode='success';retry.click()
            check('manual_retry_once',wait(lambda:not chat.busy) and len(calls)==count+1)
            FakeDeepSeek.mode='auth';chat.input.setPlainText('ТЕСТОВАЯ ошибка ключа 401');chat.send.click()
            check('auth_fixture_delivered',wait(lambda:not chat.busy))
            check('auth_state_shared',panel.ai_state.snapshot()['connection_status']=='authentication_failed' and 'подтвердить API-ключ' in chat.provider_status.text())
            capture('E-chat-auth-fixture')
            check('error_does_not_delete_saved_key',bool(vault.get('deepseek_api_key')))
            check('error_does_not_delete_history',len(chat.messages)>6)
            FakeDeepSeek.mode='success'

            # Long actual native text editors: paragraphs/code/selection/copy/scroll.
            chat.clear_history()
            mixed='ТЕСТОВЫЙ ТЕКСТ · Русский и English\n\nНесколько абзацев.\n1. Первая строка\n2. Second item\n\n```python\nprint("hello")\n```\n\nhttps://example.invalid/'+('long-segment-'*45)
            bubble=chat._append('model',mixed);chat._append('user','ТЕСТОВЫЙ короткий ответ')
            settle()
            check('long_bubble_no_horizontal_scroll',bubble.text_view.horizontalScrollBar().maximum()==0 and chat.history.horizontalScrollBar().maximum()==0)
            check('long_source_text_preserved',bubble.message_text==mixed)
            cursor=bubble.text_view.textCursor();cursor.select(QTextCursor.SelectionType.Document);bubble.text_view.setTextCursor(cursor);bubble.text_view.copy()
            check('bubble_text_selectable_copyable','Русский и English' in app.clipboard().text())
            cursor.clearSelection();bubble.text_view.setTextCursor(cursor)
            capture('F-long-paragraph-code-url')
            for number in range(12):
                chat._append('user' if number%2 else 'model',f'ТЕСТОВЫЕ ДАННЫЕ · сообщение {number}\nРусский и English · история прокручивается без прыжка.')
            settle();bar=chat.history.verticalScrollBar();bar.setValue(0);settle()
            previous=bar.value();chat._append('model','ТЕСТОВЫЙ новый ответ не переносит чтение к концу.');settle()
            check('old_history_does_not_jump',bar.value()==previous==0 and not chat.history._follow_bottom)
            capture('F-reading-old-messages')
            chat.input.setPlainText('\n'.join('Многострочный черновик '+str(i) for i in range(8)));settle()
            check('composer_bounded_growth',46<chat.input.height()<=122,chat.input.height())
            chat.input.clear();settle();check('composer_shrinks',chat.input.height()==46)

            # Existing search model: true returned shapes, explicit fixture content.
            panel.show_search();panel._clear_results();panel.text.setText('qa.fixture@example.invalid');panel._query=panel.text.text()
            for service,url in (('duolingo','https://www.duolingo.com/'),('diigo','https://www.diigo.com/'),('gravatar','https://gravatar.com/')):
                panel._engine_result(Result('qa-'+service,'qa.fixture@example.invalid','email_check',service,
                    description='ТЕСТОВЫЕ ДАННЫЕ · не реальная регистрация',details={'email':'qa.fixture@example.invalid','service_url':url},status='registration_detected'))
            panel._set_phase('completed');panel.status.setText('ТЕСТОВЫЕ ДАННЫЕ · три сервиса, не реальные регистрации');panel.checked_label.setText('Проверено: 1');settle()
            check('three_email_rows_fit',panel.results_view.visualRect(panel.result_model.index(2,0)).bottom()<panel.results_view.viewport().height())
            check('one_email_caveat',panel.email_notice.isVisible())
            count=panel.result_model.rowCount();panel._source_status(SourceExecution('qa-fixture','Explicit local fixture','empty','ТЕСТОВЫЙ статус'))
            check('execution_not_a_result',panel.result_model.rowCount()==count)
            capture('G-email-fixture-results')
            panel._clear_results();panel.text.setText('fixture-user');panel.set_query_kind('username')
            panel._engine_result(Result('qa-profile','ТЕСТОВЫЕ ДАННЫЕ · fixture-user','profile','github','https://example.invalid/fixture-user',status='verified'))
            long_url='https://example.invalid/'+('long-path-'*42)
            panel._engine_result(Result('qa-long','ТЕСТОВЫЕ ДАННЫЕ · '+('длинное имя '*20),'profile','Example fixture',long_url,status='verified'))
            panel._set_phase('completed');panel.status.setText('ТЕСТОВЫЕ ДАННЫЕ · профили, не реальные аккаунты');capture('G-profile-fixture-results')
            index=panel.result_model.index(0,0);rect=panel.results_view.visualRect(index);action=panel.results_view.itemDelegate().action_rect(rect)
            QTest.mouseClick(panel.results_view.viewport(),Qt.MouseButton.LeftButton,pos=action.center())
            check('inline_opens_exact_source',opened[-1:]==['https://example.invalid/fixture-user'])
            panel.results_view.setCurrentIndex(panel.result_model.index(1,0));panel.show_selected_details();settle()
            check('long_details_full_url',panel.details_dialog.fields['URL источника'].text()==long_url)
            capture('G-long-result-details',panel.details_dialog);panel.details_dialog.close();app.processEvents()
            saved_records=deepcopy(panel._records)
            for _ in range(8):panel.show_chat();panel.show_search()
            check('rapid_switch_preserves_results',panel._records==saved_records)

            panel._clear_results();panel.text.setText(TON);panel._query=TON
            raw='0:'+'0'*64
            for fact in (
                Result('qa-ton-tx','ТЕСТОВАЯ транзакция','transaction','TON','https://example.invalid/transaction/qa',
                       details={'tx_hash':'a'*64,'amount':'1.25','asset':'TON','direction':'in','normalized_address':raw},status='verified'),
                Result('qa-ton-relation','ТЕСТОВАЯ связь','relationship','TON','https://example.invalid/address/qa',
                       details={'address':'0:'+'1'*64,'normalized_address':raw},status='check'),
                Result('qa-ton-label','ТЕСТОВАЯ метка источника','label','TON','https://example.invalid/address/qa',
                       details={'label':'QA synthetic service label','normalized_address':raw},status='check')):
                panel._engine_result(fact)
            panel._set_phase('completed');panel.status.setText('ТЕСТОВЫЕ ДАННЫЕ · TON, не реальные транзакции')
            check('ton_overview_preserves_three_observations',panel.blockchain_overview.isVisible() and len(panel._records)==3)
            check('ton_uncertainty_separate',panel.result_model.confirmed_count==1)
            capture('G-ton-fixture-results')

            panel.resize(460,420);settle()
            report['minimum_actual_size']=[panel.width(),panel.height()]
            check('native_actual_minimum',(panel.width(),panel.height())==(460,420),report['minimum_actual_size'])
            check('minimum_search_action_visible',panel.rect().contains(panel.find.mapTo(panel,panel.find.rect().bottomRight())))
            capture('H-minimum-search')
            panel.show_chat();capture('H-minimum-chat')
            check('minimum_composer_visible',panel.rect().contains(chat.send.mapTo(panel,chat.send.rect().bottomRight())))
            panel.open_settings('ИИ');panel.connections.status.setText('ТЕСТОВЫЕ ДАННЫЕ · отдельное окно настроек')
            panel.settings_dialog.resize(460,420);settle();capture('H-minimum-settings',panel.settings_dialog)
            dialog=panel.settings_dialog
            report['minimum_settings_size']=[dialog.width(),dialog.height()]
            report['minimum_settings_hints']={'minimum_hint':[dialog.minimumSizeHint().width(),dialog.minimumSizeHint().height()],
                'layout_minimum':[dialog.layout().minimumSize().width(),dialog.layout().minimumSize().height()]}
            check('minimum_settings_size',(dialog.width(),dialog.height())==(460,420),report['minimum_settings_size'])
            panel.settings_dialog.close();app.processEvents()
            count=len(calls);reopened=OsintPanel(store.load(),store)
            check('restart_restores_credential_provider',reopened.ai_state.can_send and reopened.ai_state.snapshot()['provider']=='deepseek')
            check('restart_has_no_automatic_api_call',len(calls)==count)
            check('no_private_key_in_safe_state',FAKE_KEY not in json.dumps(panel.ai_state.snapshot()))
            report['mock_api_calls']=calls
            report['source_open_boundary']=opened
            report['passed']=True
    except Exception as error:
        report['passed']=False
        report['error']=f'{type(error).__name__}: {error}'
    finally:
        release.set()
        for widget in (reopened,panel):
            if widget is not None:
                widget.shutdown();widget.deleteLater()
        app.processEvents()
        app.clipboard().setText(original_clipboard)
        report['protected_after']=hashes()
        report['protected_files_unchanged']=before==report['protected_after']
        report['passed']=report.get('passed',False) and report['protected_files_unchanged']
        serialized=json.dumps(report,ensure_ascii=False,indent=2)
        if FAKE_KEY in serialized:
            raise AssertionError('Fixture secret must not appear in QA reports')
        (folder/'report.json').write_text(serialized+'\n',encoding='utf-8')
        print(json.dumps({'report':str(folder/'report.json'),'passed':report['passed'],'checks':len(report['checks']),
                          'dpr':report.get('actual_device_pixel_ratio'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--scales')
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--factor',type=float,default=1)
    parser.add_argument('--label')
    args=parser.parse_args()
    if args.child:
        label=args.label or ('fixtures-native-' if args.native else 'fixtures-offscreen-')+str(round(args.factor*100))
        return child(args.native,args.factor,label)
    outcomes=[]
    for factor in [float(value) for value in (args.scales or ('1' if args.native else '1,1.25,1.5')).split(',')]:
        label=args.label or ('fixtures-native-' if args.native else 'fixtures-offscreen-')+str(round(factor*100))
        command=[sys.executable,__file__,'--child','--factor',str(factor),'--label',label]
        if args.native:command.append('--native')
        outcomes.append(subprocess.run(command,cwd=ROOT,timeout=90).returncode==0)
    return 0 if all(outcomes) else 1


if __name__=='__main__':
    raise SystemExit(main())
