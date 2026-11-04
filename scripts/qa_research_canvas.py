"""Sequential real Qt/WebEngine canvas acceptance in an isolated QA profile."""
import argparse
import hashlib
import io
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
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exe',type=Path);parser.add_argument('--gansar',action='store_true')
    parser.add_argument('--keep-open',action='store_true',help='Keep the verified own QA window for native dialog review until qa-close.flag')
    parser.add_argument('--cancel',action='store_true',help='Cancel one real bounded read-only Gansar request and verify restart')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a fresh evidence directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_QA_VAULT='GrangerPet/QA/canvas_'+namespace,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtWidgets import QApplication
    from grangerpet.ipc import send_command
    from grangerpet.config import Settings
    from perf_process_metrics import ProcessSampler
    from PIL import Image
    app=QApplication.instance() or QApplication([])
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    report={'origin':'frozen-EXE' if args.exe else 'native-source','mocked':False,'isolated_profile':True,
        'gateway_calls':0,'checks':[],'live_tools':[],'screenshots':[]}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    owned=None;process=None
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)});save();print(json.dumps(report['checks'][-1]),flush=True)
        if not value:raise AssertionError(name)
    def wait(fn,seconds=50):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.35)
        raise TimeoutError('Bounded own canvas QA wait')
    def state():
        row=send_command('pet','status',timeout=8000)
        if row and owned and row.get('pid')!=owned:raise RuntimeError('Unrelated instance; no control')
        return row
    def command(action,payload=None):
        row=send_command('pet',action,payload or {},timeout=12000)
        if not row or not row.get('ok'):raise RuntimeError('Own command failed: '+action)
        return row
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.3)
        if name not in ('input','dom','window'):
            response=state().get('desktop',{}).get('last_response',{})
            if response.get('ok') is False:raise RuntimeError('Own UI action rejected: '+str(response.get('error')))
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current-state'})
        return json.loads((out/'current-state.json').read_text(encoding='utf-8'))
    def canvas():return snapshot().get('research_canvas',{})
    def settled(revision=None):
        def ready():
            row=canvas()
            if row.get('error'):raise RuntimeError('Canvas operation: '+row['error'])
            return row if row and not row.get('busy') and (revision is None or row.get('document',{}).get('revision',0)>revision) else None
        return wait(ready)
    def edit(operation,arguments):
        doc=canvas()['document'];action('research_canvas_edit',{'id':doc['id'],'revision':doc['revision'],'operation':operation,'arguments':arguments})
        return settled(doc['revision'])['document']
    def dom():
        action('dom');return state()['desktop'].get('dom',{})
    def metrics():
        previous=canvas().get('metrics',{}).get('generation',0)
        action('research_canvas_metrics')
        return wait(lambda:m if (m:=canvas().get('metrics',{})).get('generation',0)>previous else None)
    def click(label):
        def element():
            d=dom()
            return next((e for e in d.get('elements',[]) if (e.get('label')==label or e.get('text')==label) and e['width']>0 and 0<e['y']<d['height']-16),None)
        e=wait(element);action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(16,e['height']/2)]})
    def shot(label):
        command('qa_snapshot',{'name':label});time.sleep(.4)
        path=out/(label+'-search.png')
        if path.exists():report['screenshots'].append({'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()});save()
    def start(number):
        nonlocal process,owned
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/f'process-{number}.log').open('wb') as stream:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
        owned=wait(state,75)['pid'];wait(lambda:state()['desktop']['ready'],60)
        command('show_workspace',{'route':'search'});action('window',{'mode':'maximize'})
    try:
        start(0);click('Мои расследования');click('Новое расследование')
        doc=wait(lambda:canvas().get('document'));identifier=doc['id']
        check('actual_click_created_empty_investigation',doc['entities']==[] and doc['revision']==1)
        for kind,label,position in [('infrastructure_asset','66.249.67.41',{'x':0,'y':0}),
                ('domain','example.org',{'x':340,'y':0}),('blockchain_address','UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd',{'x':680,'y':0})]:
            doc=edit('node',{'type':kind,'label':label,'position':position})
        ids=[n['id'] for n in doc['entities']]
        doc=edit('edge',{'from_id':ids[0],'to_id':ids[1],'relation_type':'potentially_related','status':'inferred'})
        doc=edit('edge',{'from_id':ids[1],'to_id':ids[2],'relation_type':'linked_to','status':'unverified'})
        edge=doc['relations'][0]
        doc=edit('edge_edit',{'relation_id':edge['id'],'from_id':edge['from_id'],'to_id':edge['to_id'],'relation_type':'analyst_comparison','status':'inferred'})
        doc=edit('annotate',{'entity_id':ids[0],'annotation':{'markdown':'**Синтетическая заметка QA**. Связь вручную, не доказательство.'}})
        check('three_typed_nodes_two_analyst_relations',len(doc['entities'])==3 and len(doc['relations'])==2 and all(not e['evidence_ids'] for e in doc['relations']))
        doc=edit('positions',{'positions':{ids[0]:{'x':40,'y':60,'pinned':True}}})
        doc=edit('group',{'ids':ids[:2],'label':'Сеть QA'})
        check('group_membership_and_pin_saved',doc['view']['positions'][ids[0]]['pinned'] and all(n['attributes'].get('parent_group_id') for n in doc['entities'] if n['id'] in ids[:2]))
        image=Image.new('RGB',(96,64),'#31617b');buffer=io.BytesIO();image.save(buffer,'PNG');(out/'fixture.png').write_bytes(buffer.getvalue())
        command('qa_desktop',{'action':'attachment_file','payload':{'name':'fixture.png'}})
        attachment=wait(lambda:s['attachments'][-1] if (s:=snapshot()).get('attachments') and not s.get('attachment_busy') else None)
        old=doc['revision'];action('research_canvas_attach',{'id':doc['id'],'revision':old,'attachment_id':attachment['id']});doc=settled(old)['document']
        check('encrypted_local_image_attached',any(n['attributes'].get('attachment_id')==attachment['id'] and n['attributes'].get('media',{}).get('thumbnail','').startswith('data:image/') for n in doc['entities']))
        # Real free source through the same manual ToolRegistry, never fixtures.
        for tool,node_id,arguments in [('network_rdap',ids[0],{'resource':'66.249.67.41'})]+(
                [('blockchain_gansar',ids[2],{'address':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','mode':'quick','operation':'profile','limit':5,'depth':0})] if args.gansar else []):
            before=len(doc['entities']);start_time=time.monotonic();action('research_canvas_tool',{'id':doc['id'],'revision':doc['revision'],'entity_id':node_id,'tool':tool,'query':next(iter(arguments.values())),'arguments':arguments,'limit':10})
            preview=wait(lambda:r['preview'] if (r:=canvas()).get('preview',{}).get('tool')==tool and not snapshot()['search']['busy'] else None,180)
            report['live_tools'].append({'tool':tool,'status':preview['status'],'records':len(preview['results']),'seconds':round(time.monotonic()-start_time,2),'limitations':preview['limitations']});save()
            check(tool+'_preview_does_not_insert',len(canvas()['document']['entities'])==before)
            if preview['results']:
                doc=canvas()['document'];old=doc['revision']
                action('research_canvas_insert',{'id':identifier,'revision':old,'token':preview['token'],'evidence_ids':[r['evidence_id'] for r in preview['results']]})
                doc=settled(old)['document'];count=len(doc['entities'])
                check(tool+'_explicit_insertion_has_evidence',bool(doc['evidence']) and any(n['evidence_ids'] for n in doc['entities']))
                action('research_canvas_insert',{'id':identifier,'revision':doc['revision'],'token':preview['token'],'evidence_ids':[r['evidence_id'] for r in preview['results']]})
                doc=settled(doc['revision'])['document'];check(tool+'_reinsertion_deduplicated',len(doc['entities'])==count)
            else:report.setdefault('external_blockers',[]).append({'tool':tool,'status':preview['status']})
        # A saved automatic result is a preview, never an implicit graph mutation.
        old=doc['revision'];before=len(doc['entities']);evidence_before={r['evidence_id'] for r in doc['evidence']}
        saved_id=snapshot()['search']['investigation_id']
        action('research_canvas_from_search',{'id':identifier,'revision':old,'investigation_id':saved_id})
        imported=settled()['preview']
        check('saved_search_preview_retains_scope_without_requests',imported['tool']=='saved_investigation' and imported['from_saved_data'] and imported['request_counts']['http_requests']==0)
        check('saved_search_preview_does_not_insert',len(canvas()['document']['entities'])==before)
        action('research_canvas_insert',{'id':identifier,'revision':old,'token':imported['token'],'evidence_ids':[r['evidence_id'] for r in imported['results']]})
        doc=settled(old)['document']
        check('saved_search_insert_deduplicates_existing_evidence',len(doc['entities'])==before and {r['evidence_id'] for r in doc['evidence']}==evidence_before)
        if args.gansar:
            previous_token=canvas()['preview']['token'];old=doc['revision']
            action('research_canvas_tool',{'id':identifier,'revision':old,'entity_id':ids[2],'tool':'blockchain_gansar','query':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','arguments':{'address':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','operation':'cached','mode':'quick','limit':5,'depth':0},'limit':10})
            reused=wait(lambda:r['preview'] if (r:=canvas()).get('preview',{}).get('token')!=previous_token and r.get('preview',{}).get('tool')=='blockchain_gansar' and not snapshot()['search']['busy'] else None,90)
            check('gansar_cached_repeat_is_explicit_and_makes_no_requests',reused['from_saved_data'] and reused['request_counts']['http_requests']==0 and bool(reused['results']))
            action('research_canvas_insert',{'id':identifier,'revision':old,'token':reused['token'],'evidence_ids':[r['evidence_id'] for r in reused['results']]})
            doc=settled(old)['document']
            report['cached_scope']={'requested_mode':'quick','requested_limit':5,'previous_nodes':before,'after_cached_nodes':len(doc['entities']),'preview_records':len(reused['results'])}
            count=len(doc['entities']);old=doc['revision']
            action('research_canvas_insert',{'id':identifier,'revision':old,'token':reused['token'],'evidence_ids':[r['evidence_id'] for r in reused['results']]})
            doc=settled(old)['document']
            check('gansar_same_cached_observations_do_not_duplicate_entities',len(doc['entities'])==count)
        if args.cancel:
            old_token=canvas()['preview']['token'];old=doc['revision']
            action('research_canvas_tool',{'id':identifier,'revision':old,'entity_id':ids[2],'tool':'blockchain_gansar','query':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','arguments':{'address':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','operation':'transactions','mode':'deep','limit':1000,'depth':0,'refresh':True},'limit':10})
            wait(lambda:snapshot()['search']['busy'],10)
            stopped=time.monotonic();action('search_stop');wait(lambda:not snapshot()['search']['busy'],5)
            check('native_stop_releases_ui_within_five_seconds',time.monotonic()-stopped<5)
            cancelled=wait(lambda:r['preview'] if (r:=canvas()).get('preview',{}).get('token')!=old_token else None,40)
            report['interrupted_operation']={'tool':'blockchain_gansar','status':cancelled['status'],'retained_records':len(cancelled['results']),'limitations':cancelled['limitations']}
            check('native_cancelled_outcome_is_explicit',cancelled['status']=='cancelled')
            check('cancelled_preview_does_not_mutate_canvas',canvas()['document']['revision']==old)
            token=cancelled['token'];action('research_canvas_tool',{'id':identifier,'revision':old,'entity_id':ids[0],'tool':'network_rdap','query':'66.249.67.41','limit':1})
            resumed=wait(lambda:r['preview'] if (r:=canvas()).get('preview',{}).get('token')!=token and not snapshot()['search']['busy'] else None,70)
            check('native_tool_can_run_after_cancel',resumed['tool']=='network_rdap' and resumed['status'] in ('complete','partial') and bool(resumed['results']))
        wait(lambda:'Развернуть полотно' in dom().get('text',''));click('Развернуть полотно')
        wait(lambda:'Вернуть в Поиск' in dom().get('text',''))
        def settled_metrics(document):
            m=metrics()
            if m.get('revision')!=str(document['revision']):return None
            c=m.get('canvas') or {};points=json.loads(c.get('qaNodes','[]'))
            for identifier in ids[:2]:
                p=document['view']['positions'][identifier];v=document['view']['viewport']
                node=next((n for n in points if n['id']==identifier),None)
                if not node or abs(node['x']-(p['x']*v['scale']+v['x']))>1 or abs(node['y']-(p['y']*v['scale']+v['y']))>1:return None
            return c
        drawn=wait(lambda:settled_metrics(doc));points=json.loads(drawn['qaNodes']);first=next(n for n in points if n['id']==ids[0]);second=next(n for n in points if n['id']==ids[1])
        before=canvas()['document'];old=before['revision'];position=before['view']['positions'][ids[0]]
        at=[drawn['x']+first['x'],drawn['y']+first['y']]
        action('input',{'kind':'drag','at':at,'to':[at[0]+35,at[1]+20]})
        doc=settled(old)['document'];check('actual_native_node_drag_committed',abs(doc['view']['positions'][ids[0]]['x']-position['x'])>10)
        drawn=wait(lambda:settled_metrics(doc));points=json.loads(drawn['qaNodes']);first=next(n for n in points if n['id']==ids[0]);second=next(n for n in points if n['id']==ids[1])
        root=next(n for n in doc['entities'] if n['id']==ids[0]);scale=doc['view']['viewport']['scale'];half=max(150 if root['attributes'].get('is_root') else 136,(252 if root['attributes'].get('is_root') else 220)*scale)/2
        old=doc['revision'];count=len(doc['relations'])
        action('input',{'kind':'drag','at':[drawn['x']+first['x']+half,drawn['y']+first['y']], 'to':[drawn['x']+second['x'],drawn['y']+second['y']]})
        doc=settled(old)['document'];check('actual_native_port_drag_creates_analyst_relation',len(doc['relations'])==count+1)
        group=next(n for n in doc['entities'] if n['type']=='entity_group' and n['label']=='Сеть QA')
        group_id=group['id'];original_view=doc['view']['viewport'];gp=doc['view']['positions'][group_id]
        doc=edit('view',{'view':{'collapsed':[group_id],'viewport':{'x':500-gp['x'],'y':250-gp['y'],'scale':1}}})
        def visible_group():
            m=metrics();c=m.get('canvas') or {};p=next((n for n in json.loads(c.get('qaNodes','[]')) if n['id']==group_id),None)
            return (c,p) if m.get('revision')==str(doc['revision']) and p and abs(p['x']-500)<1 and abs(p['y']-250)<1 else None
        drawn,point=wait(visible_group);old=doc['revision'];before=doc['view']['positions'];at=[drawn['x']+point['x'],drawn['y']+point['y']]
        action('input',{'kind':'drag','at':at,'to':[at[0]+30,at[1]+20]})
        doc=settled(old)['document'];after=doc['view']['positions'];dx=after[group_id]['x']-before[group_id]['x'];dy=after[group_id]['y']-before[group_id]['y']
        check('native_collapsed_group_drag_keeps_hidden_members_aligned',abs(dx)>10 and all(abs(after[i]['x']-before[i]['x']-dx)<1 and abs(after[i]['y']-before[i]['y']-dy)<1 for i in ids[:2]))
        doc=edit('view',{'view':{'collapsed':[],'viewport':original_view}})
        shot('canvas-before-restart');saved={key:doc[key] for key in ('entities','relations','annotations','view')}
        command('stop');process.wait(timeout=30);owned=None;start(1)
        click('Мои расследования');action('research_canvas_open',{'id':identifier});doc=wait(lambda:r.get('document') if not (r:=canvas()).get('busy') else None)
        check('restart_keeps_entities_relations_annotations_positions',all(doc[key]==value for key,value in saved.items()))
        check('reopened_sources_keep_provenance',all(row.get('evidence_id') for row in doc['evidence']))
        wait(lambda:'Развернуть полотно' in dom().get('text',''));click('Развернуть полотно')
        wait(lambda:'Вернуть в Поиск' in dom().get('text',''));shot('canvas-after-restart');report['passed']=True;save()
        if args.keep_open:
            print(json.dumps({'ready_for_native_dialog_review':True,'owned_pid':owned}),flush=True)
            while process.poll() is None and not (out/'qa-close.flag').exists():time.sleep(.5)
    except Exception as error:report.update(passed=False,error_type=type(error).__name__,error=str(error)[:250]);save();raise
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=30)
        if process:check('own_app_exit_zero',process.returncode==0)
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks'])}))


if __name__=='__main__':main()
