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
import shutil
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
    parser.add_argument('--image',type=Path,help='Explicit authorized photo for the real visual chat scenario')
    parser.add_argument('--resume-visual',type=Path,help='Resume one explicitly named prior isolated visual QA profile; no credentials are copied')
    parser.add_argument('--source',action='store_true',help='Run current source with a QA-only stack watchdog')
    parser.add_argument('--identity-only',action='store_true',help='Targeted real EXE check of the final identity-routing fix')
    parser.add_argument('--cancel-only',action='store_true',help='Actual cancel after observed blockchain evidence, then restart')
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
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True,exist_ok=True)
    if args.resume_visual:
        previous=args.resume_visual.resolve()
        if not previous.is_relative_to((ROOT/'output/reconstruction').resolve()):raise ValueError('Only an isolated QA profile may be resumed')
        prior=json.loads((previous/'report.json').read_text(encoding='utf-8'))
        if not prior.get('qa_gateway_secret_removed') or prior.get('exe_sha256')!=hashlib.sha256(args.exe.read_bytes()).hexdigest():
            raise ValueError('Previous QA must be closed and belong to this binary')
        source=previous/'appdata/GrangerPet'
        for name in ('attachments','public-media','map-tiles','investigations','conversations'):
            if (source/name).is_dir():shutil.copytree(source/name,profile/name)
        if (source/'chat-history.dpapi').is_file():shutil.copy2(source/'chat-history.dpapi',profile/'chat-history.dpapi')
        from grangerpet.agent_journal import InvestigationJournal
        from grangerpet.graph_store import GraphViewStore
        journal=InvestigationJournal(profile/'investigations');views=GraphViewStore(journal)
        for path in journal.directory.glob('*.checkpoint.dpapi'):
            identifier=path.name.split('.')[0]
            views.save(identifier,{**views.load(identifier),'mode':'graph'})
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='deepseek',source_root=str(ROOT),
        cursor_reaction=False,reduced_motion=True,agent_steps=30,agent_calls=60,agent_timeout=900,
        agent_tokens=180000,research_mode='quick',search_timeout=45,agent_tool_timeout=45).to_dict()),encoding='utf-8')
    report={'mock':False,'mode':'actual_source_Qt_WebEngine' if args.source else 'actual_frozen_Qt_WebEngine','user_history_read':False,
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
            time.sleep(.5)
        raise TimeoutError('Bounded own-GUI scenario wait expired')
    def finish(label,seconds=450):
        value=wait(lambda:(s if not s['busy'] else None) if (s:=snapshot()) else None,seconds)
        command('qa_snapshot',{'name':label});snapshot(label)
        return value
    def start(run):
        nonlocal process,owned
        argv=[str(args.exe.resolve()),'--pet','--interaction-qa']
        if args.source:
            wrapper=out/'source-watchdog.py'
            wrapper.write_text('import sys,faulthandler\nsys.path.insert(0,'+repr(str(ROOT))+')\nf=open('+repr(str(out/'stacks.log'))+',"w")\nfaulthandler.dump_traceback_later(15,repeat=True,file=f)\nfrom main import main\nraise SystemExit(main())\n',encoding='utf-8')
            argv=[sys.executable,str(wrapper),'--pet','--interaction-qa']
        with (out/f'process-{run}.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready']);monitor.sample([owned])
        command('show_workspace',{'route':'chat'})
    def graph(identifier):
        command('show_workspace',{'route':'search'});action('window',{'mode':'maximize'})
        action('investigation_graph_get',{'id':identifier,'mode':'graph'})
        value=wait(lambda:s['investigation_graph'] if (s:=snapshot()).get('investigation_graph',{}).get('state')=='ready' and s['investigation_graph'].get('investigation_id')==identifier else None)
        if (dom().get('graph') or {}).get('graphMode')!='graph':
            # A mounted workspace owns its view after its first load; opening
            # another backend projection does not replace that React state.
            action('graph_scroll')
            element=wait(lambda:next((e for e in dom().get('elements',[]) if e.get('text')=='Граф' and e['width']>0 and 0<e['y']<dom().get('height',0)-35),None))
            action('input',{'kind':'click','at':[element['x']+element['width']/2,element['y']+min(18,element['height']/2)]})
        wait(lambda:(g if g.get('investigationId')==identifier and g.get('graphMode')=='graph' and g.get('canvas') and g.get('layoutPending')=='false' else None) if (g:=dom().get('graph') or {}) else None)
        return value
    try:
        credentials.set_secret('deepseek_api_key',key)
        start(0)
        action('connection_test');wait(lambda:snapshot()['connection'].get('status') in ('connected','ready','verified'),90)
        check('actual_gateway_connection_proof',snapshot()['connection']['canSend'])
        if args.resume_visual:
            from grangerpet.agent_journal import InvestigationJournal
            value=snapshot();identifier=value.get('investigation',{}).get('id')
            if not identifier:raise ValueError('The prior visual investigation was not restored')
            journal=InvestigationJournal(profile/'investigations');saved=journal.load_checkpoint(identifier)
            before=len(saved['record'].get('calls',[]))
            check('actual_cpu_observations_survive_visual_restart',all(any(r.get('details',{}).get('capability')==name and
                r['details'].get('status')=='completed' and (name=='image_understand' or r['details'].get('predictions'))
                for r in saved.get('evidence',[])) for name in ('image_understand','geoclip_predict','waypoint_predict')))
            already_complete=saved['record'].get('status')=='completed' and saved['record'].get('report_status')=='completed'
            if not already_complete:
                action('investigation_continue',{'id':identifier})
                value=finish('visual-restored-answer',650);inv=value['investigation']
            else:
                # Restored public summaries deliberately exclude report text.
                # Verify the protected record against the actual chat message;
                # do not send a resume command to a completed investigation.
                value=snapshot('visual-restored-answer');inv=saved['record']
                check('completed_visual_report_visible_in_restored_chat',any(
                    m.get('role')=='model' and m.get('text')==inv.get('final_report') for m in value.get('messages',[])))
            check('visual_restore_keeps_same_investigation',inv['id']==identifier)
            check('visual_restored_analytical_answer_completed',inv['status']=='completed' and inv.get('report_status')=='completed' and len(inv.get('final_report',''))>500)
            saved=journal.load_checkpoint(identifier)
            models=[{'tool':r['details'].get('capability'),'status':r['details'].get('status'),
                'predictions':len(r['details'].get('predictions') or [])} for r in saved.get('evidence',[])
                if r.get('details',{}).get('execution_mode')=='LOCAL_MODEL']
            (out/'actual-model-check.json').write_text(json.dumps({'exe_sha256':report['exe_sha256'],'models':models,
                'both_geolocators_completed':all(any(r['tool']==name and r['status']=='completed' and r['predictions']>0 for r in models)
                    for name in ('geoclip_predict','waypoint_predict'))},indent=2),encoding='utf-8')
            report['scenarios']['visual_restore']={'id':identifier,'status':inv['status'],'report_status':inv.get('report_status'),
                'new_calls':inv.get('calls',[])[before:],'prior_qa_timeout_preserved':True,
                'completed_report_restored_without_regeneration':already_complete}
            g=graph(identifier);command('qa_snapshot',{'name':'visual-restored-graph'})
            check('restored_visual_graph_has_original_and_reference_pixels',any(n['type']=='image' and n.get('attributes',{}).get('original_image') and n['attributes'].get('media',{}).get('thumbnail') for n in g['entities']) and any(n['type']=='image' and n.get('attributes',{}).get('reference_photo') and n['attributes'].get('media',{}).get('thumbnail') for n in g['entities']))
            action('route',{'route':'chat'})
            wait(lambda:'Диалог с Гермионой' in dom().get('headings',[]))
            command('qa_snapshot',{'name':'visual-restored-chat'})
            previous_calls=len(inv.get('calls',[]))
            action('investigation_graph_analyze',{'id':identifier,'intent':'explain','entity_id':g['root_id']})
            value=finish('visual-restored-local-followup',180)
            fresh=value['investigation'].get('calls',[])[previous_calls:]
            check('restored_visual_followup_keeps_identity_and_stays_local',value['investigation']['id']==identifier and value['investigation'].get('report_status')=='completed' and len(value['investigation'].get('final_report',''))>500 and all(c.get('tool') in ('evidence_get','evidence_graph') for c in fresh))
        elif args.visual:
            if not args.image or not args.image.is_file():raise ValueError('--visual requires an explicit --image')
            # The local command pipe is intentionally limited to 16 KiB.
            # Existing QA attachment_file reads only this named isolated input.
            (out/'photo.jpg').write_bytes(args.image.read_bytes())
            action('attachment_file',{'name':'photo.jpg'})
            chosen=wait(lambda:s['attachments'] if (s:=snapshot()).get('attachments') and not s.get('attachment_busy') else None,40)
            action('chat_send',{'text':'Гермиона, исследуй географические признаки выбранной фотографии. Опиши реальные видимые объекты, '
                'получи GeoCLIP и Waypoint кандидаты, проверь их через geoint_research, покажи реальные сравнительные фотографии и объясни ограничения. '
                'Не повторяй inference без новой задачи и не утверждай точный адрес без независимых признаков.',
                'attachment_ids':[chosen[-1]['id']]})
            value=finish('visual-agent-answer',800);inv=value['investigation'];identifier=inv['id']
            calls=inv.get('calls',[]);names=[c.get('tool') for c in calls]
            report['scenarios']['visual']={'id':identifier,'status':inv['status'],'calls':calls,
                'report_status':inv.get('report_status'),'source_sha256':hashlib.sha256(args.image.read_bytes()).hexdigest()}
            check('actual_visual_pipeline_backend_call','visual_geoint' in names)
            check('actual_geoint_research_backend_call','geoint_research' in names)
            from grangerpet.agent_journal import InvestigationJournal
            journal=InvestigationJournal(profile/'investigations');saved=journal.load_checkpoint(identifier)
            rows=saved.get('evidence',[])
            check('actual_pixel_description_in_evidence',any(r.get('details',{}).get('capability')=='image_understand' and r['details'].get('description') for r in rows))
            check('actual_geoclip_and_waypoint_predictions_in_exe',all(any(
                r.get('details',{}).get('capability')==name and r['details'].get('status')=='completed' and r['details'].get('predictions')
                for r in rows) for name in ('geoclip_predict','waypoint_predict')))
            refs=[r for r in rows if r.get('type')=='reference_image']
            report['scenarios']['visual']['references_found']=len(refs)
            report['scenarios']['visual']['references_fetched']=sum(r['details'].get('image_fetched') is True for r in refs)
            answer=inv.get('final_report','')
            check('visual_answer_has_substance_and_no_raw_protocol',len(answer)>500 and not __import__('re').search(r'(?<!#)ev_[a-f0-9]{20}',answer) and 'Выбранные локальные изображения (служебный протокол)' not in answer)
            g=graph(identifier);command('qa_snapshot',{'name':'visual-agent-graph'})
            check('visual_graph_keeps_original_image',any(n['type']=='image' and n.get('attributes',{}).get('original_image') for n in g['entities']))
            action('route',{'route':'chat'});command('qa_snapshot',{'name':'visual-agent-chat'})
            previous_calls=len(calls)
            action('investigation_graph_analyze',{'id':identifier,'intent':'explain','entity_id':g['root_id']})
            value=finish('visual-local-followup',180)
            fresh=value['investigation'].get('calls',[])[previous_calls:]
            check('visual_followup_keeps_identity_without_model_rerun',value['investigation']['id']==identifier and all(c.get('tool') in ('evidence_get','evidence_graph') for c in fresh))
            report['scenarios']['visual_followup']={'id':identifier,'calls':fresh}
        elif args.cancel_only:
            from grangerpet.agent_journal import InvestigationJournal
            target='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
            action('chat_send',{'text':'Исследуй '+target+' через blockchain_gansar operation profile mode deep; сохраняй полученные наблюдения.'})
            value=wait(lambda:(s if any(row.get('details',{}).get('tx_hash') for row in s.get('evidence',[])) else None) if (s:=snapshot()) else None,100)
            identifier=value['investigation']['id'];started=time.monotonic();action('chat_stop')
            value=finish('cancelled-blockchain',30)
            report['scenarios']['cancel']={'seconds_until_ui_idle':round(time.monotonic()-started,3),'id':identifier,'status':value['investigation'].get('status')}
            check('cancel_returns_control_without_waiting_for_query_deadline',time.monotonic()-started<8)
            journal=InvestigationJournal(profile/'investigations')
            saved=wait(lambda:p if (p:=journal.load_checkpoint(identifier)).get('record',{}).get('status') in ('cancelled','paused','interrupted','limit_reached') else None,35)
            check('cancel_retains_actual_observed_evidence',bool(saved.get('evidence')))
            before=len(saved['evidence'])
            command('stop');process.wait(timeout=35);owned=None;start(1)
            saved=journal.load_checkpoint(identifier)
            check('cancelled_evidence_survives_actual_restart',len(saved.get('evidence',[]))>=before)
            check('restart_does_not_automatically_repeat_cancelled_query',not snapshot()['busy'])
        else:
            if not args.identity_only:
                target='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
                prompt='Гермиона, исследуй этот TON-адрес '+target+'. В режиме quick найди активы, транзакции, NFT и контрагентов. Используй реальные blockchain_gansar operation profile и nft scope wallet, затем evidence_graph. Дай итог с ограничениями источников. Данных полного DTO и рассчитанных агрегатов достаточно: не читай отдельные события через evidence_get. После profile, nft и evidence_graph переходи к анализу. Не исследуй соседние адреса сейчас.'
                action('chat_send',{'text':prompt});value=finish('ton-agent',360)
                inv=value['investigation'];identifier=inv['id']
                calls=inv.get('calls',[])
                report['scenarios']['ton']={'id':identifier,'status':inv['status'],'calls':calls}
                check('actual_chat_blockchain_calls',any(row.get('tool')=='blockchain_gansar' for row in calls))
                check('actual_chat_nft_branch',any(row.get('tool')=='blockchain_gansar' and row.get('arguments',{}).get('operation')=='nft' for row in calls))
                check('actual_chat_graph_tool',any(row.get('tool')=='evidence_graph' for row in calls))
                g=graph(identifier);command('qa_snapshot',{'name':'ton-agent-graph'})
                check('actual_asset_nodes',any(node['type']=='asset' for node in g['entities']))
                wallet=next(node for node in g['entities'] if node['type']=='blockchain_address' and node.get('attributes',{}).get('is_root'))
                action('investigation_graph_select',{'id':identifier,'entity_id':wallet['id']})
                previous_calls=len(inv.get('calls',[]))
                action('chat_send',{'text':'Покажи активы кошелька '+target+' из сохранённых данных: blockchain_gansar operation cached section assets. Новых сетевых поисков не запускай.'})
                value=finish('cached-assets',150);cached_inv=value['investigation']
                report['scenarios']['cached_assets']={'id':cached_inv['id'],'calls':cached_inv.get('calls',[])}
                check('cached_assets_have_actual_backend_call',cached_inv['id']==identifier and any(row.get('tool') in ('blockchain_gansar','evidence_get') for row in cached_inv.get('calls',[])[previous_calls:]))
                from grangerpet.agent_journal import InvestigationJournal
                journal=InvestigationJournal(profile/'investigations')
                saved=journal.load_checkpoint(identifier)
                local=[row for row in saved.get('executions',[]) if row.get('from_saved_data')]
                check('cached_assets_perform_zero_http_requests',bool(local) and all(row.get('source_diagnostics',{}).get('http_requests')==0 for row in local))
                g=graph(identifier)
                counterparty=next(node for node in g['entities'] if node['type']=='blockchain_address' and node['id']!=wallet['id'] and node.get('attributes',{}).get('address'))
                action('investigation_graph_select',{'id':identifier,'entity_id':counterparty['id']})
                previous_calls=len(cached_inv.get('calls',[]))
                action('chat_send',{'text':'Исследуй выделенного контрагента '+str(counterparty['attributes']['address'])+' на один уровень глубже. Используй blockchain_gansar operation trace chain ton mode quick depth 1. Обнови evidence_graph один раз и дай краткий итог.'})
                value=finish('selected-counterparty',240);focused=value['investigation']
                new=focused.get('calls',[])[previous_calls:]
                check('selected_counterparty_uses_same_investigation',focused['id']==identifier)
                check('selected_counterparty_has_real_blockchain_call',any(row.get('tool')=='blockchain_gansar' and row.get('arguments',{}).get('operation') in ('trace','profile','transactions') for row in new))
                report['scenarios']['counterparty']={'id':identifier,'calls':new}
                g=graph(identifier);edge=next(row for row in g['relations'] if row.get('evidence_ids'))
                previous_calls=len(focused.get('calls',[]))
                action('investigation_graph_select',{'id':identifier,'relation_id':edge['id']})
                action('investigation_graph_analyze',{'id':identifier,'intent':'explain','relation_id':edge['id']})
                value=finish('explain-edge',150);explained=value['investigation'];new=explained.get('calls',[])[previous_calls:]
                check('explain_edge_stays_local_and_keeps_identity',explained['id']==identifier and not any(row.get('tool') not in ('evidence_get','evidence_graph') for row in new))
                report['scenarios']['explain_edge']={'id':identifier,'calls':new,'relation_id':edge['id']}
                command('stop');process.wait(timeout=35);owned=None;start(1)
                previous_calls=len(explained.get('calls',[]))
                action('chat_send',{'text':'Продолжи сохранённое расследование. Используй уже собранные данные и blockchain_gansar operation cached section assets для '+target+'. Не повторяй сетевые проверки. Дай краткий итог.'})
                value=finish('resumed-investigation',180)
                check('actual_restart_resume_keeps_investigation',value['investigation']['id']==identifier)
                report['scenarios']['restart_resume']={'id':identifier,'calls':value['investigation'].get('calls',[])[previous_calls:]}
                action('chat_new')
            action('chat_send',{'text':'Проверь ENS и Web3-идентификаторы публичного адреса 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045. Выполни blockchain_gansar operation identity mode quick, не полный финансовый поиск. Укажи forward/reverse проверку и ограничения.'})
            value=finish('ens-agent',200);report['scenarios']['ens']={'status':value['investigation']['status'],'calls':value['investigation'].get('calls',[])}
            check('real_identity_tool_call',any(row.get('tool')=='blockchain_gansar' and row.get('arguments',{}).get('operation')=='identity' for row in value['investigation'].get('calls',[])))
            if args.identity_only:
                actual=value['investigation'].get('calls',[])
                check('identity_goal_skips_financial_profile',actual[0]['arguments'].get('operation')=='identity' and not any(row.get('tool')=='blockchain_gansar' and row.get('arguments',{}).get('operation') in (None,'profile') for row in actual))
                identity=[row for row in actual if row.get('tool')=='blockchain_gansar' and row.get('arguments',{}).get('operation')=='identity' and row.get('arguments',{}).get('address','').lower()=='0xd8da6bf26964af9d7eed9e03e53415d37aa96045']
                check('equivalent_identity_options_do_not_repeat_network_operation',len(identity)==1)
        report['process_metrics']=monitor.sample([owned]);save()
        command('stop');process.wait(timeout=35);owned=None;check('final_exit_zero',process.returncode==0)
        wait(lambda:monitor.sample()['process_count']==0,30);check('no_owned_orphan_processes',True)
        report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        try:
            if process and process.poll() is None:
                try:command('stop');process.wait(timeout=35)
                except (RuntimeError,subprocess.TimeoutExpired):
                    import signal
                    if owned:
                        try:os.kill(owned,signal.SIGTERM)
                        except (OSError,ProcessLookupError):pass
                    process.terminate();process.wait(timeout=15)
        finally:
            credentials.delete_secret('deepseek_api_key')
            report['qa_gateway_secret_removed']=not credentials.get_secret('deepseek_api_key');save()


if __name__=='__main__':main()
