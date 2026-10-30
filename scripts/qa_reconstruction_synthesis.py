"""Actual saved gateway credential and saved public Gansar sample; no new collectors."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Prior live evidence exists; choose another directory explicitly.')
    from grangerpet.ai_keys import resolve_deepseek_key, DEFAULT_DEEPSEEK_MODEL
    key = resolve_deepseek_key()
    args.output.mkdir(parents=True)
    if not key:
        (args.output/'report.json').write_text('{"status":"not_executed_no_saved_key"}', encoding='utf-8')
        print('not_executed_no_saved_key')
        return
    os.environ['APPDATA'] = str(args.output.resolve()/'appdata')
    from grangerpet.agent import AgentRunner, AgentLimits
    from grangerpet.ai import DeepSeekClient
    from grangerpet.investigation import InvestigationEvidence
    from grangerpet.investigation_analysis import analyze, factual_report
    class SavedOnly:
        def catalog(self): return []
        def schemas(self): return []
        def execute(self, *args, **kwargs): raise AssertionError('No external tool is allowed during synthesis')
        def begin_investigation(self):
            runner._store.add(source)
    source = json.loads(args.result.read_text(encoding='utf-8'))
    goal = ('Разбери сохранённые данные TON-адреса UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd. '
        'Объясни направления и объёмы переводов по активам, крупнейшие операции, основных контрагентов, '
        'повторяющиеся взаимодействия, активность по датам, токены и NFT, метки сервисов и пределы достоверности. '
        'Ответ нужен по существу с источниками, а не перечень evidence. Новые внешние запросы не нужны.')
    runner = AgentRunner(DeepSeekClient(key), SavedOnly(), limits=AgentLimits(max_tokens=1, synthesis_timeout=240))
    events, started = [], time.monotonic()
    result = runner.run(DEFAULT_DEEPSEEK_MODEL, [{'role':'user', 'text':goal}], on_event=events.append)
    (args.output/'answer.md').write_text(result['text'], encoding='utf-8')
    analysis = analyze(result['investigation'])
    (args.output/'local-analysis.json').write_text(json.dumps(analysis, ensure_ascii=False), encoding='utf-8')
    (args.output/'fallback.md').write_text(factual_report(analysis, language_unavailable=True), encoding='utf-8')
    report = {'mock':False, 'mode':'actual_gateway_sse_saved_public_gansar_302_sample',
        'elapsed_seconds':round(time.monotonic()-started, 3), 'state':result['investigation']['status'],
        'report_status':result['investigation'].get('report_status'), 'synthesis_error':result['investigation'].get('synthesis_error'),
        'report_parts':result['investigation'].get('report_parts'), 'characters':len(result['text']),
        'stream_events':sum(row['type']=='text' for row in events), 'external_tool_calls':0,
        'usage':result['metadata'].get('usage'), 'secret_leaked': key in result['text'],
        'raw_evidence_ids': bool(__import__('re').search(r'(?<!#)ev_[a-f0-9]{20}', result['text']))}
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
