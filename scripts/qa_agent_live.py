"""One bounded real investigation with the user's saved DeepSeek connection."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from grangerpet.ai import DeepSeekClient, AIError
    from grangerpet.agent import AgentRunner, AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.ai_keys import resolve_deepseek_key, DEFAULT_DEEPSEEK_MODEL
    from grangerpet.config import SettingsStore
    directory = ROOT/'output/agent-qa/live-investigation'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'report.json'
    if path.exists():
        raise SystemExit('Prior live investigation preserved; do not rerun automatically')
    key = resolve_deepseek_key()
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'actual LLM and actual local OSINT adapters',
              'mock': False, 'query': 'Найди публичные упоминания никнейма solvnox: проверь публичные профили и индексируемые упоминания, сопоставь факты. Не проверяй email, не обращайся через авторизованные сессии. Для каждого инструмента limit=3. Не больше трёх инструментов.',
              'key_available': bool(key), 'events': []}
    if not key:
        report.update(api_test='not_executed_no_key', passed=False)
    else:
        registry = ToolRegistry(SettingsStore().load(), redactions=(key,))
        runner = AgentRunner(DeepSeekClient(key), registry,
            limits=AgentLimits(max_steps=4, max_tool_calls=3, timeout=100, max_tokens=24000))
        started = time.monotonic()
        try:
            result = runner.run(DEFAULT_DEEPSEEK_MODEL, [{'role': 'user', 'text': report['query']}],
                cancel_event=threading.Event(), on_event=lambda event: report['events'].append({k:v for k,v in event.items() if k in ('type','tool','count','status','step','code')}))
            report.update(result=result, elapsed_seconds=round(time.monotonic()-started, 3),
                passed=bool(result.get('text')) and bool(result['investigation']['tool_calls']) and bool(result.get('evidence')),
                api_test='executed')
        except AIError as error:
            report.update(passed=False, api_test='failed', code=error.code, http_status=error.http_status,
                          partial=runner.snapshot())
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    assert not key or key not in encoded
    path.write_text(encoded+'\n', encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'api_test':report['api_test'],
        'elapsed_seconds':report.get('elapsed_seconds'),'steps':report.get('result',{}).get('investigation',{}).get('steps'),
        'tool_calls':report.get('result',{}).get('investigation',{}).get('tool_calls'),
        'evidence':len(report.get('result',{}).get('evidence',[]))}))


if __name__ == '__main__':
    main()
