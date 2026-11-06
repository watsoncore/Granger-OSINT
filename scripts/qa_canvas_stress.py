"""Native V3 input/paint measurements; synthetic and supplied observations stay separate."""
import argparse
import base64
import io
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def synthetic_document(count, thumbnail):
    """Deterministic mixed semantic cards, explicitly synthetic, never evidence."""
    from grangerpet.evidence_graph import _id
    from grangerpet.research_canvas import new_document,validate
    if count not in (50,100,500,1000,5000):raise ValueError('Use documented stress sizes')
    d=new_document(f'SYNTHETIC QA · {count} objects')
    d['view']['ui']={'graph_mode':'manual','card_mode':'auto','inspector_open':False}
    kinds=('person','domain','blockchain_address','image','analyst_note','entity_group',
           'organization','nft','hypothesis','social_profile')
    for i in range(count):
        kind=kinds[i%len(kinds)];identifier=_id(kind,'synthetic-qa-'+str(i))
        attrs={'origin':'synthetic_fixture','member_count':0,'description':'Синтетическая карточка для измерения отрисовки'}
        if kind in ('image','nft','social_profile'):
            attrs['media']={'id':'synthetic_image_'+str(i),'kind':'local_attachment','state':'ready','thumbnail':thumbnail}
        if kind=='blockchain_address':attrs.update(chain='eth',address='0x'+format(i,'040x'))
        if kind=='analyst_note':attrs['markdown']='**СИНТЕТИЧЕСКАЯ ЗАМЕТКА**\n\nПроверка высоты карточки и переноса текста.'
        d['entities'].append({'id':identifier,'type':kind,'label':f'СИНТЕТИЧЕСКИЙ {kind} {i}',
            'attributes':attrs,'evidence_ids':[],'source':['Synthetic QA'],'verification_status':'inferred' if i%7==0 else 'unverified'})
        d['view']['positions'][identifier]={'x':i%20*340,'y':i//20*200}
        if i%17==0:d['view']['card_sizes'][identifier]={'width':360,'height':180}
        if i:d['relations'].append({'id':'rel_'+hashlib.sha256(str(i).encode()).hexdigest()[:24],
            'from_id':d['entities'][(i-1)//3]['id'],'to_id':identifier,'relation_type':'potentially_related',
            'direction':'directed','origin':'synthetic_fixture','verification_status':'inferred','evidence_ids':[]})
    return validate(d)


def evidence_digest(records):
    return hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()


def observed_document(path,tool='blockchain_gansar'):
    """Reuse a supplied receipt without claiming this script made live requests."""
    from copy import deepcopy
    from grangerpet.agent_evidence import validate_saved_evidence
    from grangerpet.evidence_graph import build
    from grangerpet.research_canvas import new_document,validate,add_node
    path=Path(path).resolve();raw=path.read_bytes()
    if len(raw)>24_000_000:raise ValueError('Observed receipt exceeds bounded QA input')
    receipt=json.loads(raw.decode('utf-8'))
    if (tool not in ('blockchain_gansar','username_maigret') or not isinstance(receipt,dict) or receipt.get('tool')!=tool
            or receipt.get('mock') is True or receipt.get('status') not in ('complete','partial')):
        raise ValueError('Expected a successful/partial saved Gansar result, never a synthetic/mock receipt')
    records=receipt.get('results')
    if not isinstance(records,list) or not records or len(records)>5000:raise ValueError('No bounded observed evidence')
    for record in records:validate_saved_evidence(record)
    graph=build(records,full=True,limit=5000,goal=receipt.get('query',''))
    d=new_document('OBSERVED Gansar · wallet projection')
    d.update(entities=graph['entities'],relations=graph['relations'],evidence=deepcopy(records))
    d['view']['ui']={'graph_mode':'wallet','card_mode':'auto','inspector_open':False}
    root=graph.get('root_id')
    if tool=='username_maigret':
        d['title']='OBSERVED Maigret · public profiles'
        root=add_node(d,{'type':'username','label':receipt['query'],'value':receipt['query']})
        for node in graph['entities']:
            if node['type']!='public_profile':continue
            d['relations'].append({'id':'rel_'+hashlib.sha256((root+'|'+node['id']).encode()).hexdigest()[:24],
                'from_id':root,'to_id':node['id'],'relation_type':'returned_for_query','direction':'directed',
                'evidence_ids':node['evidence_ids'],'verification_status':'source_reported','origin':'tool',
                'attributes':{'tool':tool,'identity_verified':False},'source_urls':[]})
        d['view']['ui'].update(graph_mode='socmint',username_root_id=root)
    for i,node in enumerate(d['entities']):
        d['view']['positions'][node['id']]={'x':i%12*340,'y':i//12*180}
    if root:d['view']['positions'][root]={'x':0,'y':0}
    provenance={'data_origin':'provided_observed_result','input_path':str(path),
        'input_sha256':hashlib.sha256(raw).hexdigest(),'source_tool':receipt['tool'],
        'source_status':receipt['status'],'source_obtained_at':receipt.get('obtained_at'),
        'source_diagnostics':deepcopy(receipt.get('source_diagnostics')),
        'evidence_count':len(records),'evidence_sha256':evidence_digest(records),
        'underlying_nodes':len(d['entities']),'edges':len(d['relations']),
        'aggregate_relations':[edge['id'] for edge in d['relations'] if edge.get('aggregate')],
        'underlying_transactions':sum(node['type']=='transaction' for node in d['entities']),
        'network_calls_by_stress_script':0}
    return validate(d),provenance


def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--counts',type=int,nargs='+',default=[50,100,500,1000,5000])
    p.add_argument('--observed-result',type=Path,help='Existing real source result.json; copied evidence, no new network requests')
    p.add_argument('--observed-profiles',type=Path,help='Separate actual Maigret receipt; never counted as new HTTP requests')
    p.add_argument('--observed-only',action='store_true',help='Only the separately supplied observation dataset')
    p.add_argument('--effects',choices=('full','reduced','off'),default='full')
    p.add_argument('--wallpaper',type=Path,help='Generated local QA image for the optional native wallpaper comparison')
    p.add_argument('--wallpaper-blur',type=int,choices=range(21),default=0)
    p.add_argument('--glow',type=int,choices=range(37))
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Use a fresh receipt directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_QA_VAULT='GrangerPet/QA/stress_'+namespace,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtWidgets import QApplication
    from grangerpet.config import Settings
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler,summarize
    app=QApplication.instance() or QApplication([])
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    preferences=Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True,ui_effects=args.effects)
    if args.wallpaper or args.glow is not None:
        from grangerpet.appearance import normalize_appearance
        appearance={'theme':'azure','effects':args.effects,'reducedMotion':True,'glow':args.glow if args.glow is not None else 12}
        if args.wallpaper:
            from grangerpet.credentials import open_bytes,seal_bytes
            from grangerpet.geoint.images import AttachmentStore,MAX_IMAGE_BYTES
            with args.wallpaper.open('rb') as stream:
                pixels=stream.read(MAX_IMAGE_BYTES+1)
            saved=AttachmentStore(profile/'wallpapers',seal=seal_bytes,open_sealed=open_bytes).import_bytes(pixels,'Synthetic QA wallpaper')
            appearance['wallpaper']={'source':'image','image':saved['id'],'dim':65,'blur':args.wallpaper_blur}
        preferences.workspace_appearance=normalize_appearance(json.dumps(appearance))
    (profile/'settings.json').write_text(json.dumps(preferences.to_dict()),encoding='utf-8')
    store=CanvasStore(InvestigationJournal(profile/'investigations'));cases=[]
    from PIL import Image
    pixels=io.BytesIO();Image.new('RGB',(64,64),'#497077').save(pixels,'PNG')
    thumbnail='data:image/png;base64,'+base64.b64encode(pixels.getvalue()).decode('ascii')
    if args.observed_only and not (args.observed_result or args.observed_profiles):raise ValueError('--observed-only requires observed input')
    for count in ([] if args.observed_only else args.counts):
        d=synthetic_document(count,thumbnail)
        start=time.perf_counter();saved=store.save(d,0)
        cases.append({'id':saved['id'],'data_origin':'synthetic_fixture','underlying_nodes':count,'edges':count-1,'encrypted_seed_write_ms':round((time.perf_counter()-start)*1000,2)})
    for path,tool in ((args.observed_result,'blockchain_gansar'),(args.observed_profiles,'username_maigret')):
        if not path:continue
        d,provenance=observed_document(path,tool)
        start=time.perf_counter();saved=store.save(d,0)
        cases.append({'id':saved['id'],**provenance,'encrypted_seed_write_ms':round((time.perf_counter()-start)*1000,2)})
    report={'origin':'frozen-EXE' if args.exe else 'native-source','data_origin':'synthetic_fixture_and_separate_provided_observations' if args.observed_result else 'synthetic_fixture','exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest() if args.exe else None,'cases':[],'checks':[],
        'effects':args.effects,'wallpaper':{'enabled':bool(args.wallpaper),'blur_px':args.wallpaper_blur,'glow':args.glow},
        'metric_semantics':'Paint timings are actual WebEngine Canvas draw durations. Active frame intervals exclude gaps >=100 ms; their reciprocal is not whole-session FPS. Event-to-paint begins at JS pointer handler. IPC pauses are excluded from that latency.'}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.2)
        raise TimeoutError('Own stress QA deadline')
    owned=None;process=None;monitor=ProcessSampler(args.exe)
    if not args.exe:monitor.source_images.add(str(Path(sys._base_executable).resolve()).casefold())
    def state():
        r=send_command('pet','status',timeout=8000)
        if r and owned and r.get('pid')!=owned:raise RuntimeError('Unrelated instance')
        return r
    def command(name,payload=None):
        r=send_command('pet',name,payload or {},timeout=12000)
        if not r or not r.get('ok'):
            report['ipc_failure']={'command':name,'action':(payload or {}).get('action'),'response':r,'parent_exit_code':process.poll() if process else None};save()
            raise RuntimeError('Own IPC command failed: '+name+'/'+str((payload or {}).get('action')))
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.15)
    def snapshot():
        name='state_'+uuid.uuid4().hex;path=out/(name+'.json')
        command('qa_desktop',{'action':'save_state','name':name})
        try:return json.loads(path.read_text(encoding='utf-8'))
        finally:
            try:path.unlink(missing_ok=True)
            except PermissionError:pass
    def dom():action('dom');return state()['desktop'].get('dom',{})
    def click(label):
        from scripts.qa_clean_release import research_labels
        labels=research_labels(label)
        def find():
            r=dom();return next((x for x in r.get('elements',[]) if (x.get('label') in labels or x.get('text') in labels) and x['width']>0 and 0<x['y']<r['height']-10),None)
        e=wait(find);action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(18,e['height']/2)]})
    def select_option(label,option):
        # Actual Radix keyboard path; own bounded input deliberately types ASCII.
        orders={'Раскладка полотна':['Вокруг кошелька','Входящие / исходящие','Кластеры контрагентов','Цепочка связей','Ручная','Иерархия','От выбранного','По типам','По связям','По времени'],
            'Представление полотна':['Кошельки и потоки','Движение средств','Контрагенты','Транзакции','Исследование связей','Все объекты']}
        click(label);click('Найти: '+label)
        action('input',{'kind':'key','key':'down'})
        for _ in range(orders[label].index(option)):action('input',{'kind':'key','key':'down'})
        action('input',{'kind':'key','key':'enter'})
    def metrics():
        old=snapshot().get('research_canvas',{}).get('metrics',{}).get('generation',0)
        # A concurrent durable commit replaces presentation state. A read-only
        # metric reply can therefore be superseded; request another observation.
        for _ in range(20):
            action('research_canvas_metrics')
            for _ in range(4):
                m=snapshot().get('research_canvas',{}).get('metrics',{})
                if m.get('generation',0)>old:return m
                time.sleep(.2)
        raise TimeoutError('Canvas metric observation superseded or unavailable')
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        started=time.perf_counter()
        with (out/'process.log').open('wb') as stream:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
        owned=wait(state,80)['pid'];wait(lambda:state()['desktop']['ready']);monitor.sample([process.pid],source_main_pids=([owned] if not args.exe else []))
        command('show_workspace',{'route':'search'});action('window',{'mode':'maximize'});click('Моё полотно')
        report['startup_to_canvas_seconds']=round(time.perf_counter()-started,3)
        for index,case in enumerate(cases):
            report['stage']={'case':case['underlying_nodes'],'phase':'open'};save()
            if index:wait(lambda:metrics().get('queue_pending',0)==0 and not snapshot().get('research_canvas',{}).get('busy'))
            start=time.perf_counter();action('research_canvas_open',{'id':case['id']})
            wait(lambda:s if not (s:=snapshot().get('research_canvas',{})).get('busy') and s.get('document',{}).get('id')==case['id'] else None)
            wait(lambda:metrics().get('canvas_id')==case['id'])
            if index==0:click('Развернуть')
            report['stage']['phase']='expand';save()
            # Progressive expansion remains bounded, and all original members stay saved.
            target=case['underlying_nodes'];synthetic=case['data_origin']=='synthetic_fixture'
            def rendered_model_count():
                current=metrics()
                if current.get('canvas_id')==case['id']:
                    return int((current.get('canvas') or {}).get('modelNodes',0))
            if synthetic and wait(rendered_model_count)<target:
                click('Показать все на полотне')
                wait(lambda:rendered_model_count()==target)
            current=metrics();c=current['canvas'];case['open_and_expand_seconds']=round(time.perf_counter()-start,3)
            if args.glow:
                visible=json.loads(c.get('qaNodes','[]'))
                candidate=next((node for node in visible if 90<node['x']<c['width']-90 and 135<node['y']<c['height']-65),None)
                if candidate:
                    action('input',{'kind':'click','at':[c['x']+candidate['x'],c['y']+candidate['y']]})
            report['stage']['phase']='gestures';save()
            samples=[]
            for i in range(12):
                at=[c['x']+c['width']*.45,c['y']+c['height']*.42]
                action('input',{'kind':'drag','at':at,'to':[at[0]+(34 if i%2==0 else -34),at[1]+12]})
                samples.append(monitor.sample([process.pid],source_main_pids=([owned] if not args.exe else [])))
            for delta in (-120,120,-120,120):action('input',{'kind':'wheel','at':[c['x']+c['width']/2,c['y']+c['height']/2],'delta':delta})
            wait(lambda:metrics().get('queue_pending',0)==0 and not snapshot().get('research_canvas',{}).get('busy'))
            final=metrics()['canvas'];frame=json.loads(final.get('frameMetrics','{}'))
            case['renderer']={k:final.get(k) for k in ('renderer','paintMs','drawnNodes','onScreenNodes','modelNodes','modelEdges','drawnImages','zoom')}
            for key,values in frame.items():
                if values:
                    ordered=sorted(values)
                    case[key]={'count':len(values),'median':round(statistics.median(values),3),
                        'p95':round(ordered[max(0,int(len(values)*.95)-1)],3),
                        'p99':round(ordered[max(0,int(len(values)*.99)-1)],3),'max':round(ordered[-1],3)}
            intervals=frame.get('active_intervals_ms',[])
            case['active_interval_reciprocal_fps']=round(1000/statistics.median(intervals),2) if intervals else None
            case['resources']=summarize(samples)
            if synthetic and target==5000:
                click('Показать всё')
                fitted=wait(lambda:m if (m:=metrics().get('canvas',{})) and float(m.get('zoom',1))<.38 else None)
                case['fit_overview']={k:fitted.get(k) for k in ('renderer','paintMs','drawnNodes','onScreenNodes','modelNodes','modelEdges','drawnEdges','zoom')}
                if int(fitted['modelNodes'])!=target:raise AssertionError('Fit overview dropped objects from the model')
                def fit_saved():
                    current=snapshot()['research_canvas']
                    return not current.get('busy') and abs(current['document']['view']['viewport']['scale']-float(fitted['zoom']))<.001
                wait(fit_saved)
                command('qa_snapshot',{'name':'synthetic-5000-fit'})
            if synthetic and target==1000:
                report['stage']['phase']='search-layouts';save()
                click('Настроить полотно');click('Поиск на полотне');action('input',{'kind':'text','text':'person 0'})
                wait(lambda:1<=int(metrics()['canvas']['drawnNodes'])<10)
                click('Поиск на полотне');action('input',{'kind':'key','key':'all','ctrl':True});action('input',{'kind':'key','key':'backspace'})
                wait(lambda:int(metrics()['canvas']['drawnNodes'])==target)
                report['checks'].append({'name':'native_search_retains_bounded_neighbor_context_and_restores_1000','passed':True})
                manual=snapshot()['research_canvas']['document']['view']['positions']
                for mode,label in [('hierarchical','Иерархия'),('radial','От выбранного'),('types','По типам'),('communities','По связям'),('timeline','По времени'),('manual','Ручная')]:
                    select_option('Раскладка полотна',label)
                    wait(lambda:not (r:=snapshot()['research_canvas']).get('busy') and r['document']['view']['layout']==mode)
                restored=snapshot()['research_canvas']['document']['view']['positions']
                report['checks'].append({'name':'native_six_layouts_restore_manual_positions','passed':restored==manual})
                if restored!=manual:raise AssertionError('Manual positions changed by reversible layout')
            if not synthetic:
                # Default wallet projection and explicit transaction drilldown
                # reuse the real saved graph. Evidence is compared before/after.
                original=snapshot()['research_canvas']['document']
                if evidence_digest(store.load(case['id'])['evidence'])!=case['evidence_sha256']:raise AssertionError('Seed evidence changed')
                case['wallet_default_projection']={'drawn_nodes':int(final['drawnNodes']),
                    'underlying_nodes':target,'underlying_transactions':case['underlying_transactions'],
                    'graph_mode':original['view'].get('ui',{}).get('graph_mode')}
                if case['aggregate_relations']:
                    relation=case['aggregate_relations'][0]
                    action('research_canvas_edit',{'id':original['id'],'revision':original['revision'],
                        'operation':'view','arguments':{'view':{'expanded_relations':[relation]}}})
                    wait(lambda:(r:=snapshot()['research_canvas']).get('document',{}).get('view',{}).get('expanded_relations')==[relation] and not r.get('busy'))
                    wait(lambda:int(metrics()['canvas']['drawnNodes'])>case['wallet_default_projection']['drawn_nodes'])
                    drilled=metrics()['canvas'];case['transaction_drilldown']={'relation_id':relation,
                        'activation':'production view mutation via QA IPC','drawn_nodes':int(drilled['drawnNodes']),
                        'paint_ms':float(drilled['paintMs']),'frame_metrics':json.loads(drilled.get('frameMetrics','{}'))}
                    changed=snapshot()['research_canvas']['document']
                    if evidence_digest(store.load(case['id'])['evidence'])!=case['evidence_sha256']:raise AssertionError('Drilldown changed original observations')
                elif case['underlying_transactions']:
                    # UTXO DTOs can intentionally omit pairwise from/to for a
                    # many-input/many-output transaction. Do not invent transfer
                    # edges or amounts; exercise the existing transaction view.
                    select_option('Представление полотна','Транзакции')
                    wait(lambda:(r:=snapshot()['research_canvas']).get('document',{}).get('view',{}).get('ui',{}).get('graph_mode')=='transactions' and not r.get('busy'))
                    drilled=metrics()['canvas'];case['transaction_drilldown']={'activation':'native searchable projection menu',
                        'aggregate_relation':'not_applicable_no_observed_pairwise_edges',
                        'drawn_nodes':int(drilled['drawnNodes']),'paint_ms':float(drilled['paintMs']),
                        'frame_metrics':json.loads(drilled.get('frameMetrics','{}'))}
                    changed=snapshot()['research_canvas']['document']
                    if evidence_digest(store.load(case['id'])['evidence'])!=case['evidence_sha256']:raise AssertionError('Transaction view changed original observations')
                report['checks'].append({'name':'provided_observation_evidence_unchanged','passed':True,'id':case['id']})
            report['cases'].append(case);save();print(json.dumps({'nodes':target,'paint':case.get('paint_ms'),'active_interval_reciprocal_fps':case['active_interval_reciprocal_fps']}),flush=True)
            command('qa_snapshot',{'name':('synthetic-' if synthetic else 'observed-')+str(target)})
        report['passed']=True;save()
    except Exception as error:report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=30)
        if process:
            report['parent_exit_code']=process.poll()
            time.sleep(.3);report['owned_processes_left']=monitor.sample([process.pid],source_main_pids=([owned] if owned and not args.exe else []))['process_count']
            if report['owned_processes_left']:report.update(passed=False,error='Owned QA processes remain after exit')
            save()
        monitor.close()


if __name__=='__main__':main()
