"""Reproducible context benchmark over synthetic, non-personal source fixtures.

Default is fully offline: exact UTF-8 request bytes, protocol/evidence/retention
checks. --live replays the final old/new working context once per selected
scenario through the already configured gateway; only provider usage and
objective fixture checks are saved. This does not measure live OSINT coverage.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grangerpet.agent import AgentRunner
from grangerpet.agent_tools import _SPECS
from grangerpet.ai import DeepSeekClient, AIError
from grangerpet.ai_keys import DEFAULT_DEEPSEEK_MODEL
from grangerpet.investigation import InvestigationEvidence


def baseline_module(revision):
    source = subprocess.check_output(['git', 'show', revision + ':grangerpet/agent.py'], cwd=ROOT)
    module = types.ModuleType('grangerpet._benchmark_old_agent')
    module.__package__ = 'grangerpet'
    sys.modules[module.__name__] = module
    exec(compile(source, '<verified-git-baseline-agent>', 'exec'), module.__dict__)
    return module


def encoded_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


class FixtureRegistry:
    def __init__(self):
        self.calls = []
        self.evidence = InvestigationEvidence()

    def catalog(self):
        return [{'name':spec.name,'source':spec.source,'kind':spec.kind,'description':spec.description,
                 'available':spec.name not in ('username_snoop','telegram_public','vk_public'),
                 'state':'ready' if spec.name not in ('username_snoop','telegram_public','vk_public') else 'auth_required',
                 'reason':'Synthetic local readiness fixture; no service request.', 'requires_approval':False}
                for spec in _SPECS]

    def schemas(self):
        return [{'type':'function','function':{'name':spec.name,'description':spec.description,
            'parameters':{'type':'object','properties':{spec.argument:{'type':'string','maxLength':spec.max_length},
                'limit':{'type':'integer','minimum':1,'maximum':10}},'required':[spec.argument],'additionalProperties':False}}}
            for spec in _SPECS if spec.name not in ('username_snoop','telegram_public','vk_public')]

    def execute(self, name, args, **kwargs):
        self.calls.append((name,deepcopy(args)))
        query = args.get('query', args.get('url','fixture'))
        if name == 'web_read':
            index=int(query.rsplit('/',1)[-1])
            content=('Aurora public archive. Historical 2020 material; ownership remains unverified. Code ORIGIN-11. '
                     if index==0 else 'Aurora related historical archive; authorship remains unverified. ')
            content += ('Navigation and unrelated published editorial material. '*180)
            content += ' Aurora technical finding: verification code PRISM-29. This report does not establish the owner of any nickname. '
            content=content[:12000]
            rows=[{'id':query,'title':'Aurora archive '+str(index),'type':'web','platform':'Fixture',
                'url':query,'status':'verified','description':content[:2000],'sources':['web_read'],
                'details':{'reading_method':'direct_http','content_excerpt':content[:2000],'content_text':content,
                    'headings':[{'level':1,'text':'Aurora archive'}],'metadata':{'description':'Synthetic public-source fixture'},
                    'links':[],'tables':[],'crawl_depth':0,'verification':'Synthetic controlled fixture, not a real website observation.'}}]
        else:
            rows=[{'id':'result_'+str(index),'title':'Aurora source '+str(index),'type':'web','platform':'Fixture',
                'url':'https://example.org/aurora/'+str(index),'status':'indexed','sources':['web_search'],
                'description':('Aurora archive 2020: code AXIOM-7. The same nickname is not proof of common ownership. '
                               'This is an indexed snippet that still needs page verification. ')*4}
                for index in range(8)]
        result={'tool':name,'query':query,'status':'complete','obtained_at':'2026-10-28T00:00:00+00:00','results':rows,
                'limitations':['Synthetic fixture, not real OSINT evidence. Identity remains unverified.']}
        self.evidence.add(result)
        return result


class ScriptedClient:
    def __init__(self, calls):
        self.calls = list(calls)
        self.requests = []

    def complete_turn(self, model, messages, **kwargs):
        self.requests.append({'messages':deepcopy(messages),'tools':deepcopy(kwargs.get('tools',[]))})
        if self.calls:
            name,args=self.calls.pop(0)
            message={'role':'assistant','content':'Сопоставлю очередной доступный источник; личность остаётся неустановленной.',
                     'tool_calls':[{'id':'fixture_'+str(len(self.requests)),'type':'function',
                        'function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}
        else:
            message={'role':'assistant','content':'Синтетический сценарий завершён; это не реальная проверка сайтов.'}
        return {'message':message,'metadata':{}}


SCENARIOS = {
    'small_search': [('web_search',{'query':'Aurora public archive '+str(index)})for index in range(2)],
    'repeated_sources': [('web_search',{'query':'Aurora independent archive '+str(index)})for index in range(10)],
    'long_pages': [('web_read',{'url':'https://example.org/archive/'+str(index)})for index in range(6)],
}
GOAL = ('Сопоставь исторические публичные материалы Aurora. Найди опубликованные проверочные коды, даты и неопределённости. '
        'Не устанавливай личность по совпадению никнеймов; не представляй поисковый сниппет прочитанной страницей.')


def run_fixture(runner_type, calls):
    client,registry=ScriptedClient(calls),FixtureRegistry()
    runner=runner_type(client,registry)
    result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':GOAL}])
    checkpoint=runner.checkpoint()
    request_sizes=[encoded_bytes(value)for value in client.requests]
    protocol=checkpoint.get('protocol_archive',checkpoint['messages'])
    valid=True
    for request in client.requests:
        pending=set()
        for row in request['messages']:
            if row['role']=='assistant' and row.get('tool_calls'):
                if pending:valid=False
                pending={call['id']for call in row['tool_calls']}
            elif row['role']=='tool':
                if row.get('tool_call_id')not in pending:valid=False
                pending.discard(row.get('tool_call_id'))
        valid=valid and not pending
    return {'requests':len(client.requests),'tool_calls':len(registry.calls),'evidence_count':len(result['evidence']),
        'evidence_ids':sorted(row['evidence_id']for row in result['evidence']),
        'input_utf8_bytes_per_step':request_sizes,'total_input_utf8_bytes':sum(request_sizes),
        'final_input_utf8_bytes':request_sizes[-1],'valid_tool_protocol':valid,
        'all_primary_content_retained':all(row.get('details',{}).get('content_text','').endswith(
            registry.evidence.get(row['evidence_id']).get('details',{}).get('content_text',''))for row in result['evidence']),
        'protocol_archive_messages':len(protocol),'context_compactions':result['investigation'].get('context_compactions',0)},client.requests[-1]


def live_probe(client, request, expected):
    messages=deepcopy(request['messages'])
    messages.append({'role':'user','content':'Заверши сопоставление только предоставленных тестовых источников. '
        'Верни краткий JSON: observed_codes (только коды из источников), dates, uncertainties. '
        'Не запускай инструменты. Это синтетический benchmark, не настоящие OSINT-находки.'})
    started=time.monotonic()
    try:
        turn=client.complete_turn(DEFAULT_DEEPSEEK_MODEL,messages,tools=[],max_output_tokens=500)
        text=str(turn.get('message',{}).get('content',''))
        return {'status':'success','seconds':round(time.monotonic()-started,3),
            'usage':turn.get('metadata',{}).get('usage',{}),
            'quality':{'expected_codes_retained':{code:code in text for code in expected},
                       'uncertainty_retained':bool(re.search(r'(?iu)(неустанов|не\s+установ|неподтверж|не\s+подтверж|неопредел|unverified|uncertain|не\s+доказ|не\s+является)',text))}}
    except AIError as error:
        return {'status':'error','error_code':error.code,'http_status':error.http_status}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',default='dd3d587')
    parser.add_argument('--output',type=Path,default=ROOT/'output/master-3.1-qa/context-benchmark.json')
    parser.add_argument('--scenarios',default=','.join(SCENARIOS))
    parser.add_argument('--live',action='store_true',help='Make exactly two real gateway calls per selected synthetic scenario.')
    args=parser.parse_args()
    selected=args.scenarios.split(',')
    if not selected or set(selected)-SCENARIOS.keys():parser.error('Unknown benchmark scenario')
    old=baseline_module(args.baseline_ref)
    report={'baseline_ref':args.baseline_ref,'synthetic_fixture':True,
            'byte_measurement':'Exact serialized UTF-8 model-input bytes, not billed tokens.',
            'live':args.live,'scenarios':{}}
    client=DeepSeekClient() if args.live else None
    for name in selected:
        before,before_request=run_fixture(old.AgentRunner,SCENARIOS[name])
        after,after_request=run_fixture(AgentRunner,SCENARIOS[name])
        item={'before':before,'after':after,'same_evidence_ids':before['evidence_ids']==after['evidence_ids'],
              'same_tool_calls':before['tool_calls']==after['tool_calls']}
        if client:
            expected=['ORIGIN-11','PRISM-29']if name=='long_pages'else['AXIOM-7']
            item['live_before']=live_probe(client,before_request,expected)
            item['live_after']=live_probe(client,after_request,expected)
        report['scenarios'][name]=item
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(name+': '+json.dumps({key:item[key]for key in ('same_evidence_ids','same_tool_calls')})+
              ' bytes '+str(before['total_input_utf8_bytes'])+' -> '+str(after['total_input_utf8_bytes']),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
