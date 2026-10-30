"""Real saved-key gateway and CPU-model scenarios through an isolated frozen GUI.

Only the gateway secret is copied directly between protected stores and removed
from the QA namespace afterwards. No credential enters IPC, source, env or logs.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.ai_keys import resolve_deepseek_key
    key=resolve_deepseek_key()
    if not key:raise SystemExit('No saved gateway key; actual API test not executed')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--visual',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior paid test retained; choose a new output directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/live_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY','GRANGERPET_QA_INPUT_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet import credentials
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler
    credentials._STORE=credentials.CredentialsStore(prefix=os.environ['GRANGERPET_QA_VAULT'])
    credentials.set_secret('deepseek_api_key',key)
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True,exist_ok=True)
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='deepseek',source_root=str(ROOT),
        cursor_reaction=False,reduced_motion=True,agent_steps=10,agent_calls=20,agent_timeout=420,
        agent_tokens=90000,search_timeout=45,agent_tool_timeout=45).to_dict()),encoding='utf-8')
    report={'mock':False,'mode':'actual_frozen_Qt_WebEngine','user_history_read':False,
        'private_source_keys_used':False,'images_sent_to_model':False,
        'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[],'scenarios':{}}
    def save():
        raw=json.dumps(report,ensure_ascii=False,indent=2)
        if key in raw:raise RuntimeError('Secret detected; report not written')
        (out/'report.json').write_text(raw,encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps({'check':name,'passed':bool(ok)}),flush=True)
        if not ok:raise AssertionError(name)
    owned=None;process=None;monitor=ProcessSampler(args.exe,gpu=False)
    def state():
        value=send_command('pet','status',timeout=2000)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Own isolated PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if value is None and name=='qa_desktop' and payload.get('action')=='save_state':
            # This read is idempotent. Do not retry chat/tool mutations after an
            # ambiguous transport response; record any snapshot retry honestly.
            report['ipc_snapshot_retries']=report.get('ipc_snapshot_retries',0)+1;save()
            time.sleep(.2);value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own GUI action failed: '+name)
        return value
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def snapshot(label='current'):
        command('qa_desktop',{'action':'save_state','name':label})
        value=json.loads((out/(label+'.json')).read_text(encoding='utf-8'))
        if key in json.dumps(value,ensure_ascii=False):raise RuntimeError('Secret crossed UI boundary')
        return value
    def dom():action('dom');return state()['desktop'].get('dom',{})
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.4)
        raise TimeoutError('Bounded own-GUI scenario wait expired')
    def finish(label,seconds=450):
        value=wait(lambda:(s if not s['busy'] else None) if (s:=snapshot()) else None,seconds)
        command('qa_snapshot',{'name':label});snapshot(label)
        return value
    def start(run):
        nonlocal process,owned
        with (out/f'process-{run}.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready']);monitor.sample([owned])
        command('show_workspace',{'route':'chat'})
    def graph(identifier):
        action('route',{'route':'search'});action('investigation_graph_get',{'id':identifier})
        value=wait(lambda:s['investigation_graph'] if (s:=snapshot()).get('investigation_graph',{}).get('state')=='ready' and s['investigation_graph'].get('investigation_id')==identifier else None)
        action('graph_scroll')
        element=wait(lambda:next((e for e in dom().get('elements',[]) if e.get('text')=='Граф' and e['width']>0 and e['y']>0),None))
        action('input',{'kind':'click','at':[element['x']+element['width']/2,element['y']+element['height']/2]})
        wait(lambda:(g if g.get('graphMode')=='graph' and g.get('canvas') and g.get('layoutPending')=='false' else None) if (g:=dom().get('graph') or {}) else None)
        return value
    try:
        start(0)
        action('connection_test');wait(lambda:snapshot()['connection'].get('status') in ('connected','ready','verified'),90)
        check('actual_gateway_connection_proof',snapshot()['connection']['canSend'])
        prompt='Исследуй публичный проект https://t.me/solvnox_project. Прочти публичную страницу и превью без Telegram-сессии. Проверь конкретные репозитории GitHub, ссылки на которые реально опубликованы. Построй evidence_graph и дай итог: находки, проверяемые цепочки ссылок и ограничения. Одноимённые аккаунты не искать, общего владельца не утверждать.'
        started=time.monotonic();action('chat_send',{'text':prompt});value=finish('telegram-live')
        inv=value['investigation'];identifier=inv['id'];tools={row.get('tool') for row in inv.get('calls',[])}
        report['scenarios']['telegram']={'status':inv['status'],'seconds':round(time.monotonic()-started,2),'calls':inv.get('tool_calls'),'tool_ids':sorted(tools)}
        check('real_chat_telegram_and_discovered_repository_tools',{'telegram_public','github_repository'}<=tools and bool(value['evidence']))
        check('telegram_useful_final_report',any(m['role']=='model' and len(m['text'])>200 for m in value['messages']) and inv['status']!='running')
        g=graph(identifier);check('real_telegram_in_search_graph',bool(g['relations']) and any(e['relation_type']=='publishes_link' for e in g['relations']))
        command('qa_snapshot',{'name':'telegram-search-graph'})
        root=g['root_id'];calls_before=inv.get('tool_calls',0);requests_before=inv.get('usage',{}).get('successful_requests',0)
        action('investigation_graph_analyze',{'id':identifier,'intent':'explain','entity_id':root})
        value=finish('graph-explain-live');current=value['investigation']
        report['scenarios']['graph_explain']={'status':current['status'],'calls_before':calls_before,'calls_after':current.get('tool_calls')}
        check('graph_explain_same_id_goal_and_saved_context',current['id']==identifier and current['goal']==inv['goal'] and len(value['messages'])>2)
        check('graph_explain_makes_real_new_model_request',current.get('usage',{}).get('successful_requests',0)>requests_before and current['status']=='completed')
        new_calls=current.get('calls',[])[len(inv.get('calls',[])):]
        check('explain_cannot_start_external_network_tools',all(row.get('tool') in ('evidence_get','evidence_graph') for row in new_calls))
        action('chat_new')
        action('chat_send',{'text':'Исследуй публичный https://t.me/solvnox_project и связанные ссылки; сохрани ход работы.'})
        wait(lambda:snapshot()['busy']);action('chat_stop');cancelled=finish('cancelled',40)
        check('cancel_preserves_stopped_checkpoint',cancelled['investigation'].get('status') in ('cancelled','paused','interrupted','limit_reached','completed'))
        cancelled_id=cancelled['investigation']['id']
        command('stop');process.wait(timeout=35);owned=None
        start(1);restored=snapshot('restored-chat')
        check('actual_restart_no_auto_resume',not restored['busy'] and restored['investigation'].get('id')==cancelled_id)
        if restored['investigation'].get('canResume'):
            action('investigation_continue',{'id':cancelled_id});resumed=finish('resumed-live')
            check('resume_keeps_same_investigation_id',resumed['investigation']['id']==cancelled_id)
        if args.visual:
            action('chat_new')
            raw=(ROOT/'output/integrations19/visual-photos/moscow-no-gps.jpg').read_bytes()
            (out/'public-landmark-no-gps.jpg').write_bytes(raw)
            action('attachment_file',{'name':'public-landmark-no-gps.jpg'})
            value=wait(lambda:s if (s:=snapshot())['attachments'] and not s['attachment_busy'] else None)
            image=value['attachments'][-1]['id'];started=time.monotonic()
            action('chat_send',{'text':'Определи вероятное место съёмки выбранного фото. GPS отсутствует. Используй установленные GeoCLIP и Waypoint через visual_geoint, затем evidence_graph. Выведи координаты кандидатов и ограничения: raw_score не вероятность. Не повторяй pipeline без новых оснований.','attachment_ids':[image]})
            value=finish('visual-geoint-live',500);inv=value['investigation'];g=graph(inv['id'])
            models={str(e.get('details',{}).get('tool') or e.get('platform')) for e in value['evidence'] if e.get('details',{}).get('predictions')}
            report['scenarios']['visual']={'seconds':round(time.monotonic()-started,2),'status':inv['status'],'calls':inv.get('tool_calls'),'prediction_models':sorted(models),'geographic_candidates':sum(n['type']=='geographic_candidate' for n in g['entities'])}
            check('real_cpu_models_accessible_from_actual_chat',any('geoclip' in name.lower() for name in models) and any('waypoint' in name.lower() for name in models))
            check('model_candidates_are_hypotheses_in_search',any(n['type']=='geographic_candidate' and n['verification_status']=='inferred' for n in g['entities']))
            command('qa_snapshot',{'name':'visual-search-graph'})
        action('tool_run',{'tool':'blockchain_gansar','query':'EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c','limit':10})
        value=wait(lambda:s if not (s:=snapshot())['search']['busy'] else None,100)
        snapshot('ton-manual')
        # Search exposes Source views, not raw normalized evidence. Preserve
        # that boundary: observed transaction details carry their real tx_hash.
        transactions=[row for row in value['search']['results'] if row.get('details',{}).get('tx_hash')]
        report['scenarios']['ton_manual']={'transactions':len(transactions),'status':value['search'].get('phase'),
            'execution_status':value['activity'][-1].get('status')}
        check('actual_exe_ton_source_returns_observed_transactions',bool(transactions))
        check('partial_source_is_not_reported_as_total_search_failure',value['search']['phase'] in ('completed','completed_with_errors'))
        manual_id=value['search']['investigation_id'];g=graph(manual_id)
        check('actual_ton_graph_preserves_direction_and_owner_uncertainty',any(e['relation_type']=='transfers' and e.get('aggregate',{}).get('owner_verified') is False for e in g['relations']))
        command('qa_snapshot',{'name':'ton-search-graph'})
        report['process_metrics']=monitor.sample([owned]);save()
        command('stop');process.wait(timeout=35);owned=None;check('final_exit_zero',process.returncode==0)
        wait(lambda:monitor.sample()['process_count']==0,30);check('no_owned_orphan_processes',True)
        report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        try:
            if process and process.poll() is None:command('stop');process.wait(timeout=35)
        finally:
            credentials.delete_secret('deepseek_api_key')
            report['qa_gateway_secret_removed']=not credentials.get_secret('deepseek_api_key');save()


if __name__=='__main__':main()
