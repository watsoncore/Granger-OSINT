"""Bounded real gateway and actual registry checks. Full results stay in output."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
GOALS={
 'ip':'Исследуй IP 66.249.67.41: RDAP, сеть и AS, обратное имя, публичные репутационные источники. Отдели оператора сети от владельца устройства. Не ищи числовой адрес как слова в Wikipedia. Итог по-русски с прямыми ссылками и ограничениями.',
 'domain':'Исследуй домен example.org пассивными доступными инструментами: DNS, RDAP, сертификаты при доступности. Без сканирования портов. Сопоставь фактические данные и ограничения, дай ссылки.',
 'steam':'Исследуй только публичный Steam-профиль https://steamcommunity.com/id/robinwalker: поля профиля, опубликованные прежние имена и открытые ссылки друзей. Не устанавливай реальную личность и не объединяй аккаунты других платформ. Краткий связный итог со ссылкой.',
 'browser':'Используй настоящий browser_* для публичного учебного сайта https://www.scrapethissite.com/pages/forms/ . Последовательно открой страницу, введи New в поисковое поле q, нажми Search, прочитай таблицу, прокрути до пагинации, перейди по ссылке на страницу2, прочитай её таблицу и сделай screenshot для локального OCR. Используй текущие snapshot_id/element_id, зависимые действия отдельно. Верни три реальные строки со второй страницы и ссылку. Не заменяй управление браузером web_read. Это чтение GET-формы, без входа и публикаций.',
 'telegram':'Прочитай только открытые опубликованные сведения https://t.me/telegram через существующие Telegram public инструменты. Без сессии, входа или извлечения участников. Раздели факты канала и неподтверждённые сведения.',
 'ton':'Исследуй публичный TON-адрес UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ через существующий Gansar: состояние адреса, баланс, доступные транзакции и ограничения. Никакой идентификации владельца. Не считать нулевой адрес человеком. Краткий итог.'}


def main():
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    from grangerpet.ai import DeepSeekClient
    from grangerpet.agent import AgentRunner,AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.context import conversation_context
    p=argparse.ArgumentParser();p.add_argument('--scenario',choices=(*GOALS,'casual'),required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence retained; choose a new output directory')
    key=resolve_deepseek_key();out.mkdir(parents=True)
    if not key:
        (out/'summary.json').write_text(json.dumps({'live':False,'reason':'saved_gateway_key_missing'}),encoding='utf-8');return 2
    os.environ['APPDATA']=str(out/'isolated-appdata')
    client=DeepSeekClient(key);started=time.monotonic();events=[];checkpoints=[]
    report={'scenario':args.scenario,'test_kind':'real_gateway_and_actual_tools','model':DEFAULT_DEEPSEEK_MODEL,
        'at':datetime.now(timezone.utc).isoformat(),'user_history_read':False,'source_api_keys_used':False}
    def write(name,value):
        raw=json.dumps(value,ensure_ascii=False,indent=2)
        if key in raw:raise RuntimeError('Refuse secret in QA output')
        (out/name).write_text(raw,encoding='utf-8')
    registry=None
    try:
        if args.scenario=='casual':
            answers=[]
            history=[{'role':'user','text':'Исследуй @solvnox и Apple'}, {'role':'model','text':'429 ошибка шлюза. @solvnox не проверен.','investigation_id':'old'}]
            for current in ('Привет, Гермиона!','Как твои дела?','Расскажи ещё что-нибудь интересное'):
                history.append({'role':'user','text':current});selected=conversation_context(history,current)
                assert 'solvnox' not in str(selected) and '429' not in str(selected)
                answer=client.stream_chat(DEFAULT_DEEPSEEK_MODEL,selected,cancel_event=threading.Event(),on_text=lambda text:None)
                answers.append({'question':current,'answer':answer,'metadata':client.last_response_metadata})
                history.append({'role':'model','text':answer})
            write('answers.json',answers);report.update(passed=all('solvnox' not in a['answer'].casefold() for a in answers),gateway_responses=len(answers),tool_calls=0)
        else:
            class Scope(ToolRegistry):
                def initial_calls(self,goal):
                    return [] if args.scenario=='browser' else super().initial_calls(goal)
                def schemas(self,*,task=None,**kwargs):
                    rows=super().schemas(task=task,**kwargs)
                    return [row for row in rows if row['function']['name'].startswith('browser_') or row['function']['name'] in ('evidence_get','evidence_graph')] if args.scenario=='browser' else rows
            from grangerpet.geoint_tools import attachment_store
            registry=Scope(Settings(),secret_getter=lambda name:'',redactions=(key,))
            registry._image_store_provider=lambda:attachment_store(out/'isolated-appdata')
            runner=AgentRunner(client,registry,limits=AgentLimits(max_steps=12,max_tool_calls=16,max_tokens=150000,
                timeout=480,per_tool_timeout=60,per_request_timeout=120,synthesis_timeout=180))
            def event(value):
                events.append(value)
                if value.get('type')!='text':print(json.dumps({'type':value.get('type'),'tool':value.get('name') or value.get('tool'),'status':value.get('status')},ensure_ascii=False),flush=True)
            result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':GOALS[args.scenario]}],
                cancel_event=threading.Event(),on_event=event,checkpoint_callback=checkpoints.append)
            write('result.json',result)
            write('checkpoint.json',runner.checkpoint())
            executions=result['investigation'].get('executions',[])
            report.update(status=result['investigation']['status'],tool_calls=len(executions),checkpoint_count=len(checkpoints),
                tools=[{'tool':row.get('tool'),'status':row.get('status')} for row in executions],
                evidence_count=len(result.get('evidence',[])),answer_characters=len(result['text']),usage=result['metadata'].get('usage'))
            expected={'browser':{'browser_navigate','browser_type','browser_click','browser_scroll','browser_screenshot'},
                'ip':{'network_rdap','network_routing'},'steam':{'steam_profile','steam_aliases','steam_friends'},
                'domain':{'domain_dns','domain_rdap'},'telegram':{'telegram_public'},'ton':{'blockchain_gansar'}}[args.scenario]
            completed={row.get('tool') for row in executions if row.get('status') in ('complete','partial','empty','completed')}
            report['passed']=expected<=completed and result['investigation']['status']=='completed'
            if registry.browser_state().get('image'):
                import base64
                state=registry.browser_state();(out/'browser.jpg').write_bytes(base64.b64decode(state['image'].split(',',1)[1]))
                report['browser_final_url']=state['url']
        report['elapsed_seconds']=round(time.monotonic()-started,3);write('summary.json',report)
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return 0 if report.get('passed') else 1
    finally:
        if registry:registry.close()


if __name__=='__main__':raise SystemExit(main())
