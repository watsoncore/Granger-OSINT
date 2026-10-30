"""Explicit fake model replies test UI delivery; no network or live API claim."""
import os
import threading
import time
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtGui import QFontDatabase, QFontInfo, QFontMetrics, QTextCursor

from grangerpet.ai import AIError
from grangerpet.chat import ChatWidget, EvidenceSelection
from grangerpet.config import Settings


@pytest.fixture
def chat(monkeypatch):
    app = QApplication.instance() or QApplication([])
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        for name in ('segoeui.ttf','segoeuib.ttf'):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
    monkeypatch.setattr('grangerpet.chat.resolve_deepseek_key', lambda: 'fake-ui-test-key')
    monkeypatch.setattr('grangerpet.ai_state.resolve_deepseek_key', lambda: 'fake-ui-test-key')
    widget = ChatWidget(Settings(ai_provider='deepseek', deepseek_model='deepseek-v4-flash'))
    widget.resize(580, 480)
    widget.show()
    yield app, widget
    widget.shutdown()
    widget.close()
    app.processEvents()


def wait(app, condition, seconds=3):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert condition()


def test_explicit_saved_asset_request_resumes_same_investigation_before_starting_another(chat,monkeypatch):
    app,widget=chat
    widget._last_investigation={'id':'existing-investigation'}
    continuation=Mock()
    monkeypatch.setattr(widget,'continue_investigation',continuation)
    factory=Mock();monkeypatch.setattr('grangerpet.chat.DeepSeekClient',factory)
    widget._submit_text('Покажи активы из сохранённых данных; не запускай сетевой поиск.')
    continuation.assert_called_once()
    assert continuation.call_args.args==('existing-investigation',)
    assert continuation.call_args.kwargs['followup']['intent']=='cached'
    factory.assert_not_called()


def test_chat_never_calls_cloud_on_creation_typing_or_settings_change(chat, monkeypatch):
    app, widget = chat
    factory = Mock()
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', factory)
    widget.input.setPlainText('This text has not been submitted')
    widget.set_settings(widget.settings)
    app.processEvents()
    factory.assert_not_called()
    assert 'не проверено' in widget.provider_status.toolTip()
    assert 'внешнему облачному провайдеру' in widget.notice.text()


def test_chat_sends_exact_model_in_worker_and_displays_plain_reply(chat, monkeypatch):
    app, widget = chat
    main_thread = threading.get_ident()
    calls = []
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            calls.append((model, deepcopy(messages), threading.get_ident()))
            return 'ТЕСТОВЫЙ ОТВЕТ <b>обычный текст</b>'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    activities = []
    widget.activity_changed.connect(activities.append)
    widget.input.setPlainText('Объясни OSINT')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    assert calls[0][0] == 'deepseek-v4-flash'
    assert calls[0][1] == [{'role': 'user', 'text': 'Объясни OSINT'}]
    assert calls[0][2] != main_thread
    assert '<b>обычный текст</b>' in widget.history.toPlainText()
    assert activities == ['thinking', 'happy']
    assert widget._context[-1]['role'] == 'model'
    assert widget.provider_status.text() == 'На связи'
    assert 'Подключено' in widget.provider_status.toolTip()


def test_cancel_preserves_history_and_rejects_late_reply_then_allows_next(chat, monkeypatch):
    app, widget = chat
    entered = threading.Event()
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            if messages[-1]['text'] == 'Первый вопрос':
                entered.set()
                cancel_event.wait(2)
                return 'LATE FAKE REPLY'
            return 'Новый тестовый ответ'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Первый вопрос')
    widget.send_message()
    wait(app, entered.is_set)
    widget.cancel()
    QTest.qWait(80)
    app.processEvents()
    assert 'Первый вопрос' in widget.history.toPlainText()
    assert 'LATE FAKE REPLY' not in widget.history.toPlainText()
    assert 'отменён' in widget.status.text()
    widget.input.setPlainText('Следующий вопрос')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    assert 'Новый тестовый ответ' in widget.history.toPlainText()
    assert widget._context[0]['text'] == 'Следующий вопрос'


def test_cancelled_jobs_are_released_after_worker_finishes(chat, monkeypatch):
    from grangerpet.ui_jobs import UiJob
    app, widget = chat
    completed = []
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            cancel_event.wait(2)
            completed.append(True)
            return 'Late fixture reply'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    for index in range(3):
        widget.input.setPlainText(f'Вопрос {index}')
        widget.send_message()
        widget.cancel()
        wait(app, lambda: len(completed) == index + 1)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    assert widget.findChildren(UiJob) == []
    assert 'Late fixture reply' not in widget.history.toPlainText()


def test_error_preserves_history_and_restores_send_controls(chat, monkeypatch):
    app, widget = chat
    class FakeClient:
        def chat(self, *_args, **_kwargs):
            raise AIError('Лимит DeepSeek API достигнут. Попробуйте позже.', code='quota', http_status=429)
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Тест ошибки')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    assert 'Тест ошибки' in widget.history.toPlainText()
    assert 'Достигнут лимит запросов DeepSeek API' in widget.history.toPlainText()
    assert widget.send.text() == 'Отправить'
    assert widget._context == []


def test_next_turn_receives_successful_russian_dialogue_context(chat, monkeypatch):
    app, widget = chat
    calls = []
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            calls.append(deepcopy(messages))
            return 'Явный тестовый ответ номер ' + str(len(calls))
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Первый русский вопрос')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    widget.input.setPlainText('Продолжи объяснение')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    assert calls[1] == [
        {'role': 'user', 'text': 'Первый русский вопрос'},
        {'role': 'model', 'text': 'Явный тестовый ответ номер 1'},
        {'role': 'user', 'text': 'Продолжи объяснение'},
    ]
    assert 'Явный тестовый ответ номер 2' in widget.history.toPlainText()


def test_payment_error_has_its_own_state_and_retains_draft_history_and_configuration(chat, monkeypatch):
    app, widget = chat
    class FakeClient:
        def chat(self, *_args, **_kwargs):
            raise AIError('Explicit HTTP 402 fixture', code='payment_required', http_status=402)
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Проверка ошибки оплаты')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    assert widget.ai_state.committed_snapshot()['connection_status'] == 'payment_required'
    assert widget.ai_state.can_send
    assert widget.settings.ai_provider == 'deepseek'
    assert widget.settings.deepseek_model == 'deepseek-v4-flash'
    assert widget.last_request['http_status'] == 402
    assert 'Проверка ошибки оплаты' in widget.history.toPlainText()
    assert '402' in widget.history.toPlainText()
    assert 'ИИ не подключ' not in widget.history.toPlainText()
    assert widget._context == []


def findings():
    return [
        {'id':'one','title':'Подтверждённая тестовая страница','type':'profile','platform':'Fixture',
         'url':'https://example.invalid/one','status':'verified','sources':['explicit-ui-fixture']},
        {'id':'two','title':'Тестовая гипотеза','type':'relationship','platform':'Fixture',
         'url':'https://example.invalid/two','status':'check','sources':['explicit-ui-fixture']},
    ]


def test_evidence_selection_defaults_to_confirmed_and_keeps_uncertain_opt_in(chat):
    _, widget = chat
    dialog = EvidenceSelection(findings(), 'deepseek', widget)
    assert [item['id'] for item in dialog.selected_results()] == ['one']
    assert 'требует проверки' in dialog.items.item(1).text()
    dialog.reject()


def test_analysis_only_explicit_selected_evidence_and_original_is_unchanged(chat, monkeypatch):
    app, widget = chat
    source = findings()
    original = deepcopy(source)
    calls = []
    def fake_analysis(provider, model, evidence, **kwargs):
        calls.append((provider, model, deepcopy(evidence), kwargs))
        evidence[0]['title'] = 'model cannot mutate source'
        return 'ТЕСТОВОЕ объяснение выбранного факта'
    monkeypatch.setattr('grangerpet.chat.explain_evidence', fake_analysis)
    monkeypatch.setattr(EvidenceSelection, 'exec', lambda self: QDialog.DialogCode.Accepted)
    assert calls == []
    widget.analyze_results(source)
    wait(app, lambda: not widget.busy)
    assert len(calls) == 1
    assert calls[0][:2] == ('deepseek', 'deepseek-v4-flash')
    assert [value['id'] for value in calls[0][2]] == ['one']
    assert calls[0][3]['external_consent'] is True
    assert source == original
    assert 'ТЕСТОВОЕ объяснение' in widget.history.toPlainText()
    assert widget._context == []


def test_dismissing_evidence_selection_does_not_send_anything(chat, monkeypatch):
    _, widget = chat
    request = Mock()
    monkeypatch.setattr('grangerpet.chat.explain_evidence', request)
    monkeypatch.setattr(EvidenceSelection, 'exec', lambda self: QDialog.DialogCode.Rejected)
    widget.analyze_results(findings())
    request.assert_not_called()
    assert not widget.busy and not widget.messages


def test_changing_provider_during_request_keeps_actual_response_identity(chat, monkeypatch):
    app, widget = chat
    entered, released = threading.Event(), threading.Event()
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            entered.set()
            released.wait(2)
            return 'ТЕСТОВЫЙ ответ исходной модели'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Тест смены настроек')
    widget.send_message()
    wait(app, entered.is_set)
    widget.set_settings(Settings(ai_provider='ollama', ollama_model='local-fixture'))
    released.set()
    wait(app, lambda: not widget.busy)
    assert widget.last_request['model'] == 'deepseek-v4-flash'
    assert widget.last_request['provider'] == 'deepseek'
    assert 'local-fixture' in widget.provider_status.toolTip()


def test_bubbles_have_real_alignment_natural_width_and_selectable_plain_text(chat):
    app, widget = chat
    outgoing = widget._append('user', 'Привет')
    incoming = widget._append('model', 'Hello, мир! <b>Это обычный текст</b>')
    app.processEvents()
    assert outgoing.width() < widget.history.viewport().width() * .5
    assert incoming.width() <= widget.history.viewport().width() * .82
    out_point = outgoing.mapTo(widget.history.viewport(), outgoing.rect().topLeft())
    in_point = incoming.mapTo(widget.history.viewport(), incoming.rect().topLeft())
    assert out_point.x() > in_point.x()
    assert incoming.text_view.toPlainText() == 'Hello, мир! <b>Это обычный текст</b>'
    cursor = incoming.text_view.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    incoming.text_view.setTextCursor(cursor)
    incoming.text_view.copy()
    assert QApplication.clipboard().text() == incoming.message_text


def test_composer_grows_to_five_lines_and_enter_sends_only_once(chat, monkeypatch):
    app, widget = chat
    calls = []
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            calls.append(messages)
            return 'Explicit keyboard fixture'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    assert 44 <= widget.input.height() <= 48
    widget.input.setPlainText('один\nдва\nтри\nчетыре\nпять\nшесть\nсемь')
    app.processEvents()
    assert 80 <= widget.input.height() <= 122
    widget.input.setPlainText('Привет')
    widget.input.setFocus()
    QTest.keyClick(widget.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert '\n' in widget.input.toPlainText()
    QTest.keyClick(widget.input, Qt.Key.Key_Return)
    wait(app, lambda: not widget.busy)
    assert len(calls) == 1
    assert len([item for item in widget.messages if item['role']=='user']) == 1


def test_reading_old_messages_does_not_jump_to_new_reply(chat):
    app, widget = chat
    for number in range(35):
        widget._append('model', f'ТЕСТОВОЕ сообщение {number}\nВторой абзац для проверки прокрутки.')
    app.processEvents();QTest.qWait(190);app.processEvents()
    bar = widget.history.verticalScrollBar()
    assert bar.maximum() > widget.history.height()
    bar.setValue(0)
    app.processEvents()
    widget._append('model', 'Новый настоящий результат появится здесь без прыжка к концу.')
    app.processEvents();QTest.qWait(190);app.processEvents()
    assert bar.value() == 0
    assert not widget.history._follow_bottom


def test_long_code_urls_and_cyrillic_wrap_without_horizontal_scroll(chat):
    app, widget = chat
    body = 'Русский и English\n\n```python\nprint("hello")\n```\n\nhttps://example.invalid/' + 'long-segment-'*80
    bubble = widget._append('model', body)
    app.processEvents()
    assert bubble.width() <= widget.history.viewport().width() * .82
    assert bubble.message_text == body
    assert bubble.text_view._plain == body
    assert 'print("hello")' in bubble.text_view.toPlainText()
    assert '```' not in bubble.text_view.toPlainText()
    assert widget.history.horizontalScrollBar().maximum() == 0
    assert bubble.text_view.horizontalScrollBar().maximum() == 0
    assert QFontInfo(bubble.text_view.font()).pixelSize() == 14
    assert QFontMetrics(bubble.text_view.font()).inFontUcs4(ord('Ж'))


def test_unconfigured_chat_preserves_draft_and_never_sends(chat, monkeypatch):
    app, widget = chat
    factory = Mock()
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', factory)
    widget.set_settings(Settings(ai_provider='none'))
    widget.input.setPlainText('Черновик до настройки')
    widget.send_message()
    assert widget.input.toPlainText() == 'Черновик до настройки'
    assert not widget.send.isEnabled()
    assert 'не настроен' in widget.provider_status.text()
    factory.assert_not_called()


def test_shared_verified_draft_does_not_enable_chat_until_committed(chat):
    app, widget = chat
    widget.set_settings(Settings(ai_provider='none'))
    widget.input.setPlainText('Черновик сохраняется при подключении')
    state = widget.ai_state
    token = state.begin_check('deepseek', 'deepseek-v4-flash', 'new-fixture-key')
    state.finish_check(token, success=True)
    assert state.snapshot()['connection_status'] == 'verified_unsaved'
    assert 'Сохраните' in widget.provider_status.text()
    assert not widget.send.isEnabled()
    # The simulated secure store must expose the new key before commit.
    from unittest.mock import patch
    with patch('grangerpet.ai_state.resolve_deepseek_key', return_value='new-fixture-key'):
        state.commit(Settings(ai_provider='deepseek', deepseek_model='deepseek-v4-flash'))
        app.processEvents()
        assert widget.send.isEnabled()
        assert widget.provider_status.text() == 'На связи'
        assert 'Подключено' in widget.provider_status.toolTip()
        assert widget.input.toPlainText() == 'Черновик сохраняется при подключении'


def test_retry_is_explicit_and_disabled_until_server_retry_after(chat, monkeypatch):
    app, widget = chat
    calls = []
    class FakeClient:
        def chat(self, model, messages, *, cancel_event):
            calls.append(1)
            raise AIError('Explicit 429 fixture', code='quota', http_status=429, retry_after=.3)
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Тест квоты')
    widget.send_message()
    wait(app, lambda: not widget.busy)
    retry = widget.history.bubbles[-1].retry
    assert not retry.isEnabled()
    assert len(calls) == 1
    QTest.qWait(350);app.processEvents()
    assert retry.isEnabled() and len(calls) == 1
    retry.click()
    wait(app, lambda: not widget.busy)
    assert len(calls) == 2


def test_bulk_history_keeps_only_one_transient_opacity_effect(chat):
    app, widget = chat
    for number in range(100):
        widget._append('model', f'ТЕСТОВОЕ сообщение {number}')
    assert len(widget.history.bubbles) == 100
    assert sum(bubble.graphicsEffect() is not None for bubble in widget.history.bubbles) <= 1
    app.processEvents();QTest.qWait(190);app.processEvents()
    assert not any(bubble.graphicsEffect() is not None for bubble in widget.history.bubbles)


def test_new_worker_failure_does_not_reuse_previous_quota_status(chat, monkeypatch):
    app, widget = chat
    attempts = []
    class FakeClient:
        def chat(self, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise AIError('Explicit quota fixture', code='quota', http_status=429)
            raise RuntimeError('Untrusted private server message must not appear')
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient', FakeClient)
    widget.input.setPlainText('Первый тест');widget.send_message()
    wait(app, lambda:not widget.busy)
    assert widget.last_request['code'] == 'quota'
    widget.input.setPlainText('Второй тест');widget.send_message()
    wait(app, lambda:not widget.busy)
    assert widget.last_request['code'] == 'provider_error'
    assert 'private server message' not in widget.history.toPlainText()
    assert widget.ai_state.committed_snapshot()['connection_status'] == 'network_error'
