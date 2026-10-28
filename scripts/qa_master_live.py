"""Bounded real DeepSeek personality + deep-page-reading investigation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.ai import DeepSeekClient, AIError
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    from grangerpet.agent import AgentRunner,AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import SettingsStore
    folder=ROOT/'output/master-qa/live-deep';folder.mkdir(parents=True,exist_ok=True)
    destination=folder/'report.json'
    if destination.exists():raise SystemExit('Prior live evidence preserved')
    key=resolve_deepseek_key();report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'mock':False,'key_available':bool(key),'events':[]}
    if not key:
        report.update(passed=False,reason='missing_key')
    else:
        client=DeepSeekClient(key)
        answers=[]
        try:
            for prompt in ('Привет, Гермиона. Как думаешь, я могу считать два одинаковых никнейма доказательством одного владельца? Ответь живо и коротко, до трёх предложений.',
                           'А ты настоящий человек или программа? Ответь честно и коротко.'):
                answers.append(client.chat(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':prompt}]))
            report['ordinary_answers']=answers
            registry=ToolRegistry(SettingsStore().load(),redactions=(key,))
            prompt=('Исследуй публичный никнейм torvalds. Найди релевантную публичную страницу профиля или репозитория, '
                    'прочитай её через web_read и при необходимости открой одну связанную страницу для проверки. '
                    'Раздели прочитанные на странице факты, сниппеты и гипотезы. Не устанавливай личность по совпадению ника. '
                    'Не используй авторизованные сервисы/email. Не больше 6 инструментов; limit=3 для поиска. '
                    'Короткий итог с таблицей и реальными evidence_id/URL.')
            runner=AgentRunner(client,registry,limits=AgentLimits(max_steps=6,max_tool_calls=6,timeout=180,max_tokens=42000))
            start=time.monotonic()
            result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':prompt}],cancel_event=threading.Event(),
                on_event=lambda row:report['events'].append({k:v for k,v in row.items() if k in ('type','tool','count','status','step')}))
            pages=[row for row in result['evidence'] if row.get('details',{}).get('reading_method')=='direct_http']
            report.update(result=result,elapsed_seconds=round(time.monotonic()-start,3),direct_pages=len(pages),
                          passed=bool(pages) and bool(result['text']),actual_api_executed=True)
        except AIError as error:
            report.update(passed=False,error={'code':error.code,'http_status':error.http_status})
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    assert not key or key not in encoded
    destination.write_text(encoded+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'direct_pages':report.get('direct_pages'),
        'elapsed_seconds':report.get('elapsed_seconds'),'steps':report.get('result',{}).get('investigation',{}).get('steps')}))


if __name__=='__main__':main()
