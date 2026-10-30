"""Arithmetic and report-state regressions; all source data here are fixtures."""
from copy import deepcopy
import json
import threading

import httpx

from grangerpet.agent import AgentLimits, AgentRunner
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.ai import DeepSeekClient
from grangerpet.engine.blockchain_analytics import analyze_transactions, canonical_address
from grangerpet.engine.blockchain_rows import normalize_dossier
from grangerpet.investigation_analysis import analyze, factual_report
from test_agent_lifecycle import Registry, Client, HISTORY, response, tool
from test_agent_completion import Bytes, frame

TON = 'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
RAW = '0:8c50fdc65bbb398b475838a8037346fe9abe97d09870a296d0df46146f34dd64'
PEER = '0:'+'1'*64


def tx(identifier, amount='0.1', **values):
    return {'chain': 'ton', 'event_id': identifier, 'tx_hash': identifier,
        'from_address': TON, 'to_address': PEER, 'asset': 'TON', 'amount_decimal': amount,
        'timestamp': '2026-10-01T12:00:00Z', 'url': 'https://tonviewer.com/transaction/'+identifier, **values}


def test_ton_aliases_exact_decimal_sources_and_directions():
    first = tx('a', '0.1000000000000000001')
    duplicate = {**first, 'from_address': RAW, 'source': 'other provider'}
    result = analyze_transactions([first, duplicate, tx('b', '0.2'), tx('c', '3', from_address=PEER, to_address=RAW),
        tx('d', None), tx('e', '1000', status='failed')], TON, 'ton')
    assert result['unique_events'] == 4
    assert result['excluded'] == {'duplicate_observations': 1, 'failed_events': 1}
    assert result['assets'][0]['outgoing'] == '0.3000000000000000001'
    assert result['assets'][0]['incoming'] == '3'
    assert result['assets'][0]['unknown_amounts'] == 1
    assert result['unique_counterparties'] == 1
    assert result['activity_by_day_utc'] == {'2026-10-01': 4}
    assert result['largest_transfers_by_asset']['ton|TON'][0]['amount'] == '3'


def test_same_ticker_different_contracts_not_summed_and_action_events_not_merged():
    result = analyze_transactions([tx('event1', '2', tx_hash='same', asset='USD', contract='0:'+'2'*64),
        tx('event2', '4', tx_hash='same', asset='USD', contract='0:'+'3'*64)], TON, 'ton')
    assert result['unique_events'] == 2 and len(result['assets']) == 2
    assert sorted(row['outgoing'] for row in result['assets']) == ['2', '4']


def test_ton_invalid_checksum_different_workchain_and_testnet_do_not_merge():
    import base64
    import binascii
    payload = bytearray(base64.urlsafe_b64decode(TON))[:34]
    payload[0] |= 0x80
    test_only = base64.urlsafe_b64encode(payload+binascii.crc_hqx(payload, 0).to_bytes(2, 'big')).decode()
    assert canonical_address('ton', TON) == RAW
    assert canonical_address('ton', test_only) != RAW
    assert canonical_address('ton', TON[:-1]+'x') != RAW
    assert canonical_address('ton', '-1:'+RAW[2:]) != RAW


def test_aggregate_uses_entire_dto_before_evidence_transaction_page_limit():
    dossier = {'target_address': TON, 'detected_chains': ['ton'], 'transactions': [tx(str(i), '1') for i in range(302)]}
    rows = normalize_dossier(dossier, max_transactions=20)
    assert sum(row['type'] == 'transaction' for row in rows) == 20
    analytics = next(row for row in rows if row['type'] == 'blockchain_analytics')
    assert analytics['details']['data']['unique_events'] == 302
    normalized = [normalize_evidence(row, 'blockchain_gansar', TON) for row in rows]
    result = analyze({'goal': TON, 'evidence': normalized})
    full = next(iter(result['blockchain'].values()))
    assert full['unique_events'] == 302 and full['assets'][0]['outgoing'] == '302'
    report = factual_report(result, language_unavailable=True)
    assert '302 уникальных событий' in report and 'Языковой анализ недоступен' in report
    assert '**Сведения источников**' not in report and 'ev_' not in report


def test_no_progress_runs_tool_free_synthesis_and_completes_answer():
    registry = Registry()
    client = Client([*[response(tool(str(index))) for index in range(4)], response(text='По полученным страницам установлены публичные сведения; полнота ограничена.')])
    events = []
    result = AgentRunner(client, registry).run('fixture', HISTORY, on_event=events.append)
    assert len(registry.calls) == 1
    assert result['investigation']['research_stop_reason'] == 'no_progress'
    assert result['investigation']['status'] == 'completed'
    assert result['investigation']['report_status'] == 'completed'
    assert result['text'].startswith('По полученным страницам')
    assert not any(row.get('role') == 'tool' for row in client.requests[-1])
    assert {row.get('type') for row in events} >= {'phase', 'text'}


def test_sse_report_continues_on_real_finish_length_without_clipping_16000_chars():
    requests = []
    pieces = ['Первый раздел. '+'a'*18000, 'Второй раздел. '+'b'*17000]
    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)-1
        return httpx.Response(200, headers={'content-type':'text/event-stream'}, stream=Bytes([
            frame(pieces[index]), frame('', finish='length' if index == 0 else 'stop'),
            b'data: {"choices":[],"usage":{"prompt_tokens":30,"completion_tokens":20,"total_tokens":50}}\n\n',
            b'data: [DONE]\n\n']))
    client = DeepSeekClient('FIXTURE-NOT-REAL-KEY', client_factory=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(transport), **kw))
    # A tiny research budget intentionally enters the separate synthesis phase.
    runner = AgentRunner(client, Registry(), limits=AgentLimits(max_tokens=1))
    events = []
    result = runner.run('deepseek-v4-flash', HISTORY, on_event=events.append)
    assert result['text'] == '\n\n'.join(pieces)
    assert len(result['text']) > 32000 and len(requests) == 2
    assert all('tools' not in request for request in requests)
    assert all(request['max_tokens'] == 8192 for request in requests)
    assert result['investigation']['report_parts'] == 2
    assert result['metadata']['usage']['total_tokens'] == 100
    assert next(row for row in reversed(events) if row['type'] == 'text')['text'] == result['text']
    assert runner.checkpoint()['report_parts'] == pieces


def test_legacy_attachment_protocol_is_not_part_of_analysis_goal():
    value = analyze({'goal':'Найди место\n\nВыбранные локальные изображения (служебный протокол)', 'evidence':[]})
    assert value['goal'] == 'Найди место'


def test_source_ids_are_validated_and_labels_are_human_even_mid_stream():
    runner = AgentRunner(Client([]), Registry())
    runner._record = {'goal':''}
    runner._store.add({'tool':'web_search', 'query':'fixture', 'status':'complete', 'results':[
        {'id':'fixture', 'type':'web', 'title':'Fixture', 'platform':'Fixture', 'url':'https://example.org/'}]})
    identifier = runner._store.records()[0]['evidence_id']
    assert runner._ledger('['+identifier+'](#'+identifier+')') == '[доказательство](#'+identifier+')'
    assert runner._ledger('`'+identifier+'`') == '[доказательство](#'+identifier+')'
    assert runner._ledger('[evidence](#ev_'+'f'*20+')') == '[доказательство не найдено]'


def test_new_followup_preserves_previous_report_and_starts_its_own_parts():
    class Reports(Client):
        def __init__(self,text):super().__init__([]);self.text=text
        def stream_report(self,*args,on_text,**kwargs):
            on_text(self.text)
            return response(text=self.text)
    first=AgentRunner(Reports('Первый готовый отчёт.'),Registry(),limits=AgentLimits(max_tokens=1))
    first.run('fixture',HISTORY)
    second=AgentRunner(Reports('Новый ответ на уточнение.'),Registry(),limits=AgentLimits(max_tokens=1))
    result=second.run('fixture',[],resume_state=first.checkpoint(),
        followup={'text':'Объясни сохранённые выводы.','context':{},'intent':'explain'})
    saved=second.checkpoint()
    assert result['text']=='Новый ответ на уточнение.'
    assert saved['report_parts']==['Новый ответ на уточнение.']
    assert saved['completed_reports'][0]['parts']==['Первый готовый отчёт.']
    assert saved['synthesis_reserved_tokens']==8192
