"""The real Qt/UiJob/AgentRunner path with explicit local LLM/source fixtures."""
from copy import deepcopy
import json
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from grangerpet.chat import ChatWidget, investigation_requested
from grangerpet.config import Settings, SettingsStore


FACT={'id':'fixture','title':'Explicit source fixture','type':'web','platform':'Fixture','url':'https://example.org/',
      'status':'indexed','description':'TEST DATA, not a real network finding','sources':['fixture']}


class Registry:
    calls=[]
    approval=False
    hold=False
    def __init__(self,*a,**k):self.calls=[]
    def catalog(self):return [{'name':'web_search','available':True,'requires_approval':self.approval}]
    def schemas(self):return [{'type':'function','function':{'name':'web_search','parameters':{'type':'object'}}}]
    def execute(self,name,args,*,cancel_event,deadline,approved=False,on_event=None):
        self.calls.append((name,args));on_event({'type':'evidence','records':[deepcopy(FACT)]})
        while self.hold and not cancel_event.is_set():time.sleep(.01)
        return {'tool':name,'query':'fixture','status':'complete','results':[deepcopy(FACT)]}


class Client:
    def __init__(self):self.n=0
    def complete_turn(self,*a,**k):
        self.n+=1
        return {'message':{'role':'assistant','content':'Итог теста' if self.n>1 else None,
                 **({'tool_calls':[{'id':'call_fixture','type':'function','function':{'name':'web_search','arguments':'{"query":"fixture"}'}}]} if self.n==1 else {})},
                 'metadata':{'usage':{'total_tokens':30}}}


@pytest.fixture
def widget(monkeypatch,tmp_path):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('grangerpet.ai_state.resolve_deepseek_key',lambda:'explicit-ui-fixture')
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient',Client)
    monkeypatch.setattr('grangerpet.chat.ToolRegistry',Registry)
    Registry.approval=Registry.hold=False
    value=ChatWidget(Settings(ai_provider='deepseek'),SettingsStore(tmp_path/'settings.json'))
    value.resize(620,500);value.show()
    yield app,value
    value.shutdown();value.close();app.processEvents()


def wait(app,predicate):
    end=time.monotonic()+4
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(10)
    assert predicate()


def test_investigation_runs_inside_existing_worker_and_publishes_provenance(widget):
    app,chat=widget;facts=[];states=[]
    chat.evidence_received.connect(lambda rows:facts.extend(rows));chat.activity_changed.connect(states.append)
    chat.input.setPlainText('Найди публичные упоминания fixture');chat.send_message()
    wait(app,lambda:not chat.busy)
    assert facts and facts[0]['evidence_id'].startswith('ev_') and facts[0]['provenance']['tool']=='web_search'
    assert 'working' in states and states[-1]=='happy'
    assert 'https://example.org/' in chat.history.toPlainText()
    assert chat._last_investigation['steps']==2
    assert list(chat._journal.directory.glob('*.json'))


def test_sensitive_tool_prompts_and_refusal_does_not_call_adapter(widget):
    app,chat=widget;Registry.approval=True
    chat.input.setPlainText('Проверь публичную запись fixture');chat.send_message()
    wait(app,lambda:chat._approval_box is not None)
    assert chat.busy
    chat._approval_box.done(QMessageBox.StandardButton.No)
    wait(app,lambda:not chat.busy)
    assert not chat._agent_registry.calls


def test_cancel_keeps_received_evidence_and_stops_following_llm_step(widget):
    app,chat=widget;Registry.hold=True;facts=[]
    chat.evidence_received.connect(lambda rows:facts.extend(rows))
    chat.input.setPlainText('Найди fixture');chat.send_message()
    wait(app,lambda:bool(facts))
    chat.cancel();assert not chat.busy
    QTest.qWait(100);app.processEvents()
    saved=json.loads(next(chat._journal.directory.glob('*.json')).read_text(encoding='utf-8'))
    assert saved['status']=='cancelled' and saved['evidence']
    assert len(chat._context)==0 and len(chat._agent_registry.calls)==1


def test_streaming_updates_a_single_existing_bubble(widget,monkeypatch):
    app,chat=widget
    class StreamClient:
        last_response_metadata={}
        def stream_chat(self,model,history,*,on_text,cancel_event):
            on_text('Тест');time.sleep(.03);on_text('Тест потока');return 'Тест потока'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient',StreamClient)
    chat.input.setPlainText('Привет');chat.send_message();wait(app,lambda:not chat.busy)
    assert len(chat.messages)==2 and len(chat.history.bubbles)==2
    assert chat.messages[-1]['text']=='Тест потока' and chat.history.toPlainText().count('Тест потока')==1


def test_routing_preserves_ordinary_conversation():
    assert investigation_requested('Найди публичные упоминания solvnox')
    assert investigation_requested('Проверь DNS домена example.org')
    assert not investigation_requested('Привет, Гермиона!')
    assert not investigation_requested('Без поиска объясни, что такое DNS и как проверять источники')
