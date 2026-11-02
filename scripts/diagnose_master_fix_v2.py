"""Controlled real gateway capture. No user history, fake keys or raw success bodies."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.ai import DeepSeekClient,AIError
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    from grangerpet.agent import AgentRunner,AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    import httpx
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--scenario',choices=('chat','short','site','broad','catalog','invalid'),required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence preserved; choose another directory')
    key=resolve_deepseek_key();out.mkdir(parents=True)
    if not key:raise SystemExit('Saved gateway key unavailable; no real request made')
    os.environ['APPDATA']=str(out/'isolated-appdata');requests=[]
    def write(name,value):
        raw=json.dumps(value,ensure_ascii=False,indent=2).replace(key,'[redacted]')
        raw=re.sub(r'AIza[A-Za-z0-9_-]{25,}|sk-[A-Za-z0-9_-]{25,}','[credential-pattern-redacted]',raw)
        (out/name).write_text(raw,encoding='utf-8')
    async def capture(response):
        try:payload=json.loads(response.request.content)
        except (ValueError,httpx.RequestNotRead):payload={}
        row={'at':datetime.now(timezone.utc).isoformat(),'http_status':response.status_code,'parameter_names':sorted(payload),
            'model':payload.get('model'),'max_tokens':payload.get('max_tokens'),'stream':payload.get('stream'),
            'roles':[m.get('role') for m in payload.get('messages',[]) if isinstance(m,dict)],
            'message_characters':sum(len(str(m.get('content') or '')) for m in payload.get('messages',[]) if isinstance(m,dict)),
            'tools':[t.get('function',{}).get('name') for t in payload.get('tools',[]) if isinstance(t,dict)]}
        requests.append(row);write('http.json',requests)
    class DiagnosticClient(DeepSeekClient):
        async def _check_response(self,response,payload):
            if not response.is_error:return await super()._check_response(response,payload)
            raw=bytearray()
            async for chunk in response.aiter_bytes():
                remaining=16000-len(raw);raw.extend(chunk[:remaining])
                if len(chunk)>remaining:break
            row=requests[-1]
            row['error_body_sha256']=hashlib.sha256(raw).hexdigest()
            # This scenario only sends our stated public test targets. The
            # bounded error body stays in ignored private QA output.
            row['controlled_public_error_body']=raw[:16000].decode('utf-8','replace')
            write('http.json',requests)
            # A bounded copy of the actual response lets production diagnose it
            # after this QA observer has consumed its stream. No second HTTP call.
            bounded=httpx.Response(response.status_code,headers=response.headers,request=response.request,content=bytes(raw))
            return await super()._check_response(bounded,payload)
    def factory(**kwargs):return httpx.AsyncClient(**kwargs,event_hooks={'response':[capture]})
    client=DiagnosticClient(key,client_factory=factory,timeout=100)
    goals={'short':'а этот IP 87.199.131.94?',
        'site':'Пассивно исследуй https://voin-cs.kz/ : прочитай опубликованные страницы, DNS, RDAP, ASN, публичные ссылки и доступные архивы. Без активного сканирования. Дай содержательный отчёт по-русски с фактическими находками и ограничениями.',
        'broad':'Пассивно исследуй https://voin-cs.kz/ : DNS RDAP IP ASN domain historical contacts, Telegram VK Instagram Steam TikTok GitHub repository username email phone GEOINT geoclip waypoint graph shadow hash. Только публичные read-only источники, без Nuclei и активных проверок. Покажи только уместные находки; не исследуй случайных людей.',
        'catalog':'Какие инструменты доступны для Steam? Проверь актуальный каталог и последние результаты, без сетевого исследования профилей.'}
    report={'scenario':args.scenario,'live':True,'user_history_read':False,'source_keys_used':False};started=time.monotonic();registry=None
    try:
        if args.scenario=='chat':
            answer=client.chat(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':'Привет, Гермиона. Ответь коротко.'}]);report.update(answer_characters=len(answer),status='completed')
        elif args.scenario=='invalid':
            report['intentional_invalid_control']=True
            async def invalid():
                async with client._client() as transport:
                    return await client._post(transport,{'model':DEFAULT_DEEPSEEK_MODEL,
                        'messages':'CONTROL_INVALID_MESSAGES_TYPE','max_tokens':1,'stream':False})
            client._run(invalid,None)
            report['status']='provider_accepted_invalid_control'
        else:
            registry=ToolRegistry(Settings(),secret_getter=lambda name:'',redactions=(key,))
            report['bound_tool_count']=len(registry.schemas(task=goals[args.scenario]))
            runner=AgentRunner(client,registry,limits=AgentLimits(max_steps=6,max_tool_calls=10,max_tokens=180000,timeout=240,per_tool_timeout=40,per_request_timeout=100,synthesis_timeout=120))
            result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':goals[args.scenario]}],
                checkpoint_callback=lambda value:write('checkpoint.json',value))
            write('result.json',result);report.update(status=result['investigation']['status'],stop_reason=result['investigation'].get('stop_reason'),
                evidence_count=len(result.get('evidence',[])),answer_characters=len(result['text']),
                api_error=result['investigation'].get('api_error'),
                executions=[{'tool':row.get('tool'),'status':row.get('status')} for row in result['investigation'].get('executions',[])])
    except AIError as error:report.update(status='error',error_code=error.code,http_status=error.http_status,diagnostic=error.diagnostic)
    finally:
        if registry:registry.close()
        report.update(http_requests=len(requests),http_errors=[r['http_status'] for r in requests if r['http_status']>=400],elapsed_seconds=round(time.monotonic()-started,3))
        write('summary.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
