"""Real native graph interaction, public observations, and bounded fresh workers.

All profiles/DTO copies are private temporary fixtures. Public receipts contain
only counts, hashes, camera telemetry and captures of the owned QA window.
"""
from __future__ import annotations
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_v4_investigation import Session,TON
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure,validate_report_path


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def node_input_point(canvas,identifier):
    nodes=json.loads(canvas.get('qaNodes','[]'))
    target=next((node for node in nodes if node['id']==identifier),None)
    if target is None:raise QaFailure('node_missing_from_visible_geometry')
    offsets=((0,0),(-.3,-.28),(.3,-.28),(-.3,.28),(.3,.28),(0,-.32),(0,.32))
    for horizontal,vertical in offsets:
        x=target['x']+horizontal*target['width']
        y=target['y']+vertical*target['height']
        if not 10<x<canvas['width']-10 or not 10<y<canvas['height']-10:continue
        if any(other['id']!=identifier and abs(x-other['x'])<=other['width']/2+5
                and abs(y-other['y'])<=other['height']/2+5 for other in nodes):continue
        return [canvas['x']+x,canvas['y']+y]
    raise QaFailure('node_geometry_fully_occluded')


def read_observations(path,tool,query):
    from grangerpet.agent_evidence import normalize_evidence,validate_saved_evidence
    raw=Path(path).read_bytes()
    if len(raw)>32_000_000:raise ValueError('Observed input exceeds bounded QA receipt')
    receipt=json.loads(raw.decode('utf-8'))
    if receipt.get('mock') is True or receipt.get('status') not in ('complete','partial','timeout'):
        raise ValueError('Only successful/partial real observations may seed QA')
    rows=receipt.get('results')
    if not isinstance(rows,list) or not rows or len(rows)>5000:raise ValueError('Missing or unbounded observed results')
    records=[]
    for row in rows:
        value=deepcopy(row) if row.get('evidence_id') else normalize_evidence(row,tool,query)
        validate_saved_evidence(value);records.append(value)
    return records,{'file':Path(path).name,'sha256':hashlib.sha256(raw).hexdigest(),'records':len(records),'source_status':receipt['status'],'data_origin':'reused_real_public_observations','network_calls_for_reuse':0}


def observed_documents(directory):
    from grangerpet.evidence_graph import build
    from grangerpet.research_canvas import add_node,new_document,validate
    ton,ton_receipt=read_observations(directory/'ton-observed-private.json','blockchain_gansar',TON)
    pool={row['evidence_id']:row for row in ton};receipts=[ton_receipt]
    for name in ('gansar-eth-live-raw.json','gansar-solana-live-raw.json','gansar-tron-live-raw.json'):
        path=directory/name
        if not path.is_file():continue
        source=json.loads(path.read_text(encoding='utf-8'));query=(source.get('gansar_report') or {}).get('target_address') or ''
        rows,receipt=read_observations(path,'blockchain_gansar',query);receipts.append(receipt)
        pool.update({row['evidence_id']:row for row in rows[:600]})
        if len(pool)>800:break
    records=list(pool.values());graph=build(records,full=True,limit=5000,goal=TON)
    if len(graph['entities'])<600:raise ValueError('Observed large investigation has fewer than600 real objects')
    crypto=new_document('PUBLIC OBSERVATIONS · V5 crypto600')
    crypto.update(entities=graph['entities'],relations=graph['relations'],evidence=records,
        executions=[{'tool':'blockchain_gansar','status':'partial','limitations':['Reused bounded public observations; not fresh HTTP'] }])
    root=graph['root_id']
    crypto['view']['ui']={'graph_mode':'wallet','crypto_root_id':root,'initial_layout':'wallet','inspector_open':False}
    crypto['view']['positions']={node['id']:{'x':i%12*340,'y':i//12*180} for i,node in enumerate(crypto['entities'])}
    crypto['view']['positions'][root]={'x':0,'y':0}
    profiles,profile_receipt=read_observations(directory/'maigret-socmint-observed-live-raw.json','username_maigret','solvnox')
    social=new_document('PUBLIC OBSERVATIONS · V5 SOCMINT')
    username=add_node(social,{'type':'username','label':'solvnox','value':'solvnox'})
    projected=build(profiles,full=True,limit=5000)
    social['entities']+=projected['entities'];social['relations']+=projected['relations'];social['evidence']=profiles
    for node in projected['entities']:
        if node['type']!='public_profile':continue
        social['relations'].append({'id':'rel_'+hashlib.sha256((username+'|'+node['id']+'|returned_for_query').encode()).hexdigest()[:24],
            'from_id':username,'to_id':node['id'],'relation_type':'returned_for_query','direction':'directed',
            'evidence_ids':node['evidence_ids'],'verification_status':'source_reported','origin':'tool',
            'attributes':{'tool':'username_maigret','identity_verified':False,'owner_verified':False},'source_urls':[]})
    for i,node in enumerate(social['entities']):social['view']['positions'].setdefault(node['id'],{'x':i%8*320,'y':i//8*170})
    social['view']['ui']={'graph_mode':'socmint','username_root_id':username,'initial_layout':'hierarchical','inspector_open':False}
    social['executions']=[{'tool':'username_maigret','status':'partial','limitations':['Reused26 actual public profiles; not fresh HTTP']}]
    return validate(crypto),validate(social),{'crypto':receipts,'socmint':profile_receipt}


class V5Session(Session):
    def status(self):
        started=time.monotonic()
        value=super().status()
        if value or self.owned_pid is None:return value
        # A read-only status request can time out while the owned renderer
        # applies a large durable snapshot. Every retry still verifies PID and
        # image path through NativeSession. Keep the delay in the QA receipt.
        self.status_timeouts=getattr(self,'status_timeouts',0)+1
        for _ in range(2):
            time.sleep(.15)
            value=super().status()
            if value:
                elapsed=(time.monotonic()-started)*1000
                self.status_recovery_ms=max(getattr(self,'status_recovery_ms',0),elapsed)
                return value
        return None

    def fill(self,label,text):
        self.click(label);self.action('input',{'kind':'key','key':'all','ctrl':True})
        if not text:self.action('input',{'kind':'key','key':'backspace'});return
        for start in range(0,len(text),180):self.action('input',{'kind':'text','text':text[start:start+180]})

    def metrics(self):
        # Durable layout/viewport ACKs replace the published state. Reissue a
        # read-only request if its response was superseded by a save.
        previous=self.canvas().get('metrics',{}).get('generation',0)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            self.action('research_canvas_metrics')
            for _ in range(4):
                value=self.canvas().get('metrics',{})
                if value.get('generation',0)>previous:return value
                time.sleep(.15)
        raise QaFailure('v5_metrics_response_superseded_or_missing')

    def idle(self):
        return wait_for(lambda:m if not self.canvas().get('busy') and (m:=self.metrics()).get('queue_pending',0)==0 else None,45)

    def open_document(self,identifier):
        self.qa_step='wait_idle_before_open'
        self.idle();self.action('research_canvas_open',{'id':identifier})
        self.qa_step='wait_durable_document_open'
        wait_for(lambda:self.document().get('id')==identifier and not self.canvas().get('busy'))
        self.qa_step='wait_rendered_canvas'
        wait_for(lambda:m if (m:=self.metrics()).get('canvas_id')==identifier and m.get('canvas') else None)
        self.ensure_expanded()
        self.qa_step='wait_initial_layout_ack'
        wait_for(lambda:self.document()['view'].get('ui',{}).get('initial_layout','')=='',30)
        self.idle();time.sleep(.4)
        self.qa_step=''

    def ensure_expanded(self):
        self.qa_step='wait_graph_toolbar'
        toolbar=wait_for(lambda:('expand' if self.find('Развернуть')[0] else 'expanded' if self.find('Встроить')[0] else None),15)
        if toolbar=='expand':
            self.qa_step='expand_rendered_canvas'
            self.click('Развернуть')
            wait_for(lambda:self.find('Встроить')[0])
            self.metrics()
        self.qa_step=''

    def visible_node(self,identifier):
        canvas=self.metrics()['canvas']
        return next((node for node in json.loads(canvas.get('qaNodes','[]')) if node['id']==identifier and 0<node['x']<canvas['width'] and 0<node['y']<canvas['height']),None)

    def choose_index(self,address):
        self.fill('Поиск в аналитическом индексе',address)
        self.click('Исследовать '+address);self.idle()

    def viewport_patch(self,value):
        # Explicit finite QA command controls the initial test zoom only;
        # page/fit/pan/selection/layout controls remain real mouse actions.
        doc=self.settled();self.action('research_canvas_edit',{'id':doc['id'],'revision':doc['revision'],'operation':'view','arguments':{'view':{'viewport':value}}})
        wait_for(lambda:self.document()['revision']>doc['revision']);self.idle()


def run(exe,observed_dir,report,shots,*,source=False,observed_only=False,dpi=True,hold_first=False):
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    result={'schema':'granger-v5-native/1','origin':'native-source' if source else 'frozen-Windows-EXE','passed':False,
        'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[], 'captures':[],
        'fresh_network_requested':not observed_only,'gateway_calls':0,'dpi_cases':[]}
    validate_report_path(report);validate_report_path(shots)
    report.parent.mkdir(parents=True,exist_ok=True);shots.mkdir(parents=True,exist_ok=True)
    def save():report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,ok):
        result['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps(result['checks'][-1]),flush=True)
        if not ok:raise QaFailure(name)
    with tempfile.TemporaryDirectory(prefix='.granger-qa-v5-',dir=ROOT) as folder:
        directory=Path(folder)
        with isolated_environment(directory):
            os.environ['QT_SCALE_FACTOR']='1'
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            crypto,social,receipts=observed_documents(observed_dir)
            crypto=store.save(crypto,0);social=store.save(social,0);result['observed_inputs']=receipts
            result['observed_counts']={'crypto_nodes':len(crypto['entities']),'crypto_edges':len(crypto['relations']),'crypto_evidence':len(crypto['evidence']),'socmint_profiles':sum(node['type']=='public_profile' for node in social['entities']),'socmint_raw_nodes':len(social['entities'])}
            saved_evidence={doc['id']:digest(doc['evidence']) for doc in (crypto,social)}
            s=V5Session(exe,directory,source)
            def capture(name):
                s.command('qa_snapshot',{'name':name})
                raw=directory/(name+'-search.png')
                wait_for(lambda:raw.is_file() and raw.stat().st_size>0,8)
                target=shots/(name+'.png');target.write_bytes(raw.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
            def opening(number=0):
                s.start(number)
                s.action('route',{'route':'search'})
                s.click('Моё полотно')
            try:
                result['phase']='crypto_open';save()
                opening();s.open_document(crypto['id'])
                root=crypto['view']['ui']['crypto_root_id'];s.click('Вписать полотно');s.idle()
                canvas=s.metrics()['canvas'];check('observed_crypto600_root_visible_readable',len(crypto['entities'])>=600 and bool(s.visible_node(root)) and int(canvas.get('drawnLabels',0))>=2)
                result['dpi_cases'].append({'requested_qt_scale':1,'observed_native_dpr':s.status().get('dpr'),
                    'canvas_width':canvas['width'],'canvas_height':canvas['height'],'system_settings_changed':False})
                capture('crypto-overview')
                if hold_first:
                    report.with_suffix('.ready.json').write_text(json.dumps({'owned_pid':s.owned_pid,'qa_directory':str(directory),'document_id':crypto['id']}),encoding='utf-8')
                    deadline=time.monotonic()+180
                    while time.monotonic()<deadline and not report.with_suffix('.continue').exists():time.sleep(.25)
                labels=lambda:[e['label'] for e in s.dom()['elements'] if str(e.get('label') or '').startswith('Исследовать ')]
                result['phase']='counterparty_index';save()
                page1=labels();check('counterparty_page_has_accessible_rows',0<len(page1)<=8)
                page_revision=s.document()['revision']
                s.click('Следующая страница объектов');s.idle();check('real_counterparty_pagination_changes_objects',labels()!=page1)
                check('counterparty_page_preserves_durable_layout_revision',s.document()['revision']==page_revision)
                capture('counterparty-page2')
                flow=next(edge for edge in crypto['relations'] if edge.get('aggregate') and root in (edge['from_id'],edge['to_id']) and edge['from_id']!=edge['to_id'])
                peer_id=flow['to_id'] if flow['from_id']==root else flow['from_id'];peer=next(node for node in crypto['entities'] if node['id']==peer_id)
                address=peer['attributes']['address'];before_search=s.document()
                s.fill('Поиск в аналитическом индексе',address);s.idle()
                after_search=s.document()
                check('full_address_filter_preserves_saved_camera_and_positions',after_search['view']['viewport']==before_search['view']['viewport'] and after_search['view']['positions']==before_search['view']['positions'])
                s.click('Исследовать '+address);s.idle()
                check('full_address_index_search_and_selection',address in s.dom()['text'])
                capture('counterparty-selected')
                result['phase']='transaction_drill';save()
                flow_control=next((e for e in s.dom()['elements'] if e.get('text','').startswith(('↙ К центральному кошельку','↗ От центрального кошелька'))),None)
                if not flow_control:raise QaFailure('counterparty_financial_flow_control_missing')
                s.click(flow_control['text']);s.click('Показать транзакции');s.idle()
                check('selected_flow_exposes_original_transactions',flow['id'] in s.document()['view']['expanded_relations'])
                capture('flow-drill')
                transaction_ids=set(flow['aggregate']['transaction_ids'])
                transaction_controls={f"Исследовать транзакцию {node['attributes'].get('tx_hash') or node['label']}":node
                    for node in crypto['entities'] if node['id'] in transaction_ids}
                choice=next((e['label'] for e in s.dom()['elements'] if e.get('label') in transaction_controls),None)
                if not choice:raise QaFailure('exact_flow_transaction_control_missing')
                transaction=transaction_controls[choice];s.click(choice);s.click('Сведения');s.idle()
                if 'from_address' not in s.dom()['text'] and s.find('Технические свойства')[0]:s.click('Технические свойства')
                attrs=transaction['attributes'];details=s.dom()['text']
                check('transaction_inspector_has_exact_hash_sender_recipient',all(attrs.get(key) and str(attrs[key]) in details for key in ('tx_hash','from_address','to_address')))
                wallet_card=s.visible_node(root)
                transaction_card=s.visible_node(transaction['id'])
                separate=wallet_card and transaction_card and (
                    abs(wallet_card['x']-transaction_card['x']) >= (wallet_card['width']+transaction_card['width'])/2
                    or abs(wallet_card['y']-transaction_card['y']) >= (wallet_card['height']+transaction_card['height'])/2
                )
                check('transaction_and_root_have_separate_visible_cards',separate)
                capture('transaction-selected')
                evidence_tab=next((e['text'] for e in s.dom()['elements'] if e.get('text','').startswith('Основания · ')),None)
                if not evidence_tab:raise QaFailure('transaction_evidence_tab_missing')
                s.click(evidence_tab)
                original_urls={row['url'] for row in crypto['evidence'] if row['evidence_id'] in transaction['evidence_ids'] and row.get('url')}
                check('transaction_source_links_preserve_original_evidence',bool(original_urls) and any(url in s.dom()['text'] for url in original_urls))
                capture('transaction-provenance')
                s.choose_index(address);s.click(flow_control['text']);s.click('Свернуть транзакции');s.idle()
                check('native_flow_collapse_removes_only_presentation',flow['id'] not in s.document()['view']['expanded_relations'])
                # Semantic zoom is deliberately18%, matching the reported V4
                # failure; screenshot and telemetry verify real far labels.
                result['phase']='semantic_zoom';save()
                s.fill('Поиск в аналитическом индексе','');s.click('К центру');s.idle()
                s.action('input',{'kind':'click','at':node_input_point(s.metrics()['canvas'],root)});s.idle()
                current=s.document()['view']['viewport'];s.viewport_patch({**current,'scale':.18})
                far=s.metrics()['canvas'];check('far18_percent_uses_named_semantic_marks',far.get('semanticZoom')=='far' and int(far.get('drawnLabels',0))>0 and bool(s.visible_node(root)))
                capture('semantic-far18')
                clusters=[cluster for cluster in json.loads(far.get('qaFarClusters','[]')) if 0<cluster['x']<far['width'] and 0<cluster['y']<far['height']]
                if clusters:
                    cluster=clusters[0];s.action('input',{'kind':'click','at':[far['x']+cluster['x'],far['y']+cluster['y']]});s.idle()
                    check('far_cluster_click_zooms_to_original_members',float(s.metrics()['canvas']['zoom'])>.18)
                s.click('К центру');s.idle()
                for _ in range(10):
                    if s.metrics()['canvas'].get('semanticZoom')=='close':break
                    s.click('Увеличить масштаб полотна');s.idle()
                check('near_zoom_shows_full_cards',s.metrics()['canvas'].get('semanticZoom')=='close')
                capture('semantic-near')
                s.click('Вписать полотно');s.idle()
                result['phase']='camera_motion';save()
                from scripts.qa_v5_motion import capture_motion,find_pan_path
                for zoom_steps in range(4):
                    try:
                        find_pan_path(s.metrics()['canvas'])
                        break
                    except QaFailure as error:
                        if str(error)!='motion_no_free_pan_corridor' or zoom_steps==3:raise
                        s.click('Уменьшить масштаб полотна');s.idle()
                motion=capture_motion(s,shots,'crypto-pan')
                motion['zoom_out_steps_to_clear_pan_path']=zoom_steps
                result['motion']=motion;check('native_pan_camera_no_snapback',motion['passed'])
                # Real node drag, followed by actual layout menu changes.
                result['phase']='manual_positions';save()
                s.pick('Раскладка полотна','Ручная','manual');s.idle()
                s.click('К центру');s.idle();card=s.visible_node(root)
                if not card:raise QaFailure('root_not_visible_for_drag')
                before_drag=s.document()['view']['positions'][root]
                start=node_input_point(s.metrics()['canvas'],root)
                s.action('input',{'kind':'drag','at':start,'to':[start[0]+45,start[1]+30]});s.idle()
                manual=deepcopy(s.document()['view'])
                check('native_node_drag_persisted_in_manual_layout',manual['positions'][root]!=before_drag and root in manual['manual_position_ids'])
                s.pick('Раскладка полотна','Вокруг кошелька','wallet');s.idle();s.pick('Раскладка полотна','Ручная','manual');s.idle()
                restored=s.document()['view'];check('native_manual_wallet_manual_preserves_positions_camera',restored['positions']==manual['positions'] and restored['viewport']==manual['viewport'])
                for mode,label in [('flow','Входящие / исходящие'),('radial','От выбранного'),('communities','По связям'),('timeline','По времени'),('wallet','Вокруг кошелька')]:
                    s.pick('Раскладка полотна',label,mode);s.idle();check('native_layout_'+mode,s.document()['view']['layout']==mode)
                result['phase']='socmint';save()
                s.open_document(social['id']);s.click('Вписать полотно');s.idle()
                social_metrics=s.metrics()['canvas'];check('socmint_root_profiles_without_technical_multiplication',int(social_metrics.get('modelNodes',0))<=10 and int(social_metrics.get('drawnLabels',0))>=2)
                capture('socmint-profiles')
                social_first=labels();s.click('Следующая страница объектов');s.idle();check('socmint_public_profile_pages',labels()!=social_first)
                first_profile=next(node for node in social['entities'] if node['type']=='public_profile')
                s.choose_index(first_profile['attributes']['url']);capture('socmint-profile-selected')
                check('socmint_profile_url_and_identity_caution',first_profile['attributes']['url'] in s.dom()['text'] and 'Совпадение username не доказывает общего владельца' in s.dom()['text'])
                s.idle();saved_docs={doc['id']:store.load(doc['id']) for doc in (crypto,social)}
                result['phase']='restart';save()
                s.stop();opening(1);s.open_document(crypto['id'])
                check('real_restart_preserves_observed_evidence_positions_types',all(store.load(identifier)['view']==doc['view'] and store.load(identifier)['entities']==doc['entities'] and digest(store.load(identifier)['evidence'])==saved_evidence[identifier] for identifier,doc in saved_docs.items()))
                capture('crypto-reopened')
                if not observed_only:
                    result['phase']='fresh_workers';save()
                    live_workers(s,store,result,check,capture,observed_dir)
                if dpi:
                    result['phase']='qt_scale_and_viewports';save()
                    for number,scale in enumerate((1.25,1.5),2):
                        s.stop();os.environ['QT_SCALE_FACTOR']=str(scale);opening(number);s.open_document(crypto['id']);s.click('Вписать полотно');s.idle()
                        measure=s.metrics()['canvas'];capture('crypto-dpi'+str(round(scale*100)))
                        measured=s.status().get('dpr');check('qt_scale_'+str(round(scale*100))+'_root_readable',bool(s.visible_node(root)) and int(measure.get('drawnLabels',0))>=2)
                        result['dpi_cases'].append({'requested_qt_scale':scale,'observed_native_dpr':measured,'canvas_width':measure['width'],'canvas_height':measure['height'],'system_settings_changed':False})
                        s.command('qa_window_mode',{'mode':'windowed'});time.sleep(.6);s.click('Вписать полотно');s.idle();capture('crypto-windowed'+str(round(scale*100)))
                        result['dpi_cases'][-1]['windowed_canvas']={key:s.metrics()['canvas'][key] for key in ('width','height')}
                    s.action('window',{'mode':'maximize'})
                    s.click('Встроить')
                    compact=wait_for(lambda:s.find('Поиск в аналитическом индексе')[0])['width']
                    s.click('Плотность интерфейса')
                    comfortable=wait_for(lambda:control if (control:=s.find('Поиск в аналитическом индексе')[0]) and control['width']>compact+5 else None)['width']
                    result['density']={'compact_index_input_css_px':compact,'comfortable_index_input_css_px':comfortable}
                    check('native_density_changes_index_geometry',comfortable>compact)
                result['phase']='complete';result['passed']=True;save()
            except BaseException as error:
                result.update(passed=False,error_type=type(error).__name__,failure_code=str(error)[:180] if isinstance(error,QaFailure) else 'native_v5_acceptance_failed');save()
                if getattr(s,'qa_step',''):result['failure_step']=s.qa_step;save()
                try:capture('failed-v5-native')
                except Exception:pass
                raise
            finally:
                result['ipc_status_observations']={'timed_out_requests':getattr(s,'status_timeouts',0),'longest_successful_recovery_ms':round(getattr(s,'status_recovery_ms',0),2)}
                save();s.stop()
    result['temporary_profile_removed']=not directory.exists();save();return result


def new_native_project(s):
    if s.find('Встроить')[0]:s.click('Встроить')
    old_id=s.document()['id'];s.click('Новое')
    created=wait_for(lambda:doc if (doc:=s.document()).get('id') and doc['id']!=old_id else None)
    wait_for(lambda:s.metrics().get('canvas_id')==created['id']);s.ensure_expanded()


def live_workers(session,store,result,check,capture,observed_dir):
    s=session
    def insert_all(preview):
        count=len(preview['results'])
        select_label=f'Выбрать все ({count})'
        insert_label=f'Добавить выбранные ({count})'
        for attempt in range(3):
            s.click(select_label)
            try:
                wait_for(lambda:(control:=s.find(insert_label)[0]) and not control.get('disabled'),4)
                break
            except QaFailure:
                if attempt==2:raise QaFailure('live_select_all_did_not_reach_requested_count')
        identifier=s.document()['id']
        s.click(insert_label)
        ids={row['evidence_id'] for row in preview['results']}
        wait_for(lambda:ids <= {row['evidence_id'] for row in store.load(identifier)['evidence']},45)
        s.idle()
        return count
    s.action('tools_refresh');wait_for(lambda:not s.snapshot().get('toolsChecking'),90)
    wallets=(('ton',TON),('btc','1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'))
    for network,address in wallets:
        result['phase']='fresh_'+network
        new_native_project(s)
        wallet=s.create('blockchain_address','V5 native public '+network.upper(),address,network)
        s.select(wallet['id']);s.click('Действия')
        wait_for(lambda:(e:=s.find('Инструмент узла')[0]) and not e.get('disabled'))
        s.pick('Инструмент узла','Gansar','gansar');s.pick('Операция Gansar','Обзор адреса','profile')
        started=time.monotonic();s.click('Выполнить → просмотр');deadline=started+180
        while time.monotonic()<deadline:
            state=s.snapshot();preview=state['research_canvas'].get('preview',{})
            if preview.get('tool')=='blockchain_gansar' and not state['search']['busy'] and not preview.get('running'):
                if not preview.get('results'):raise QaFailure('fresh_'+network+'_native_final_empty')
                break
            time.sleep(.25)
        else:raise QaFailure('fresh_'+network+'_native_deadline_or_empty')
        count=insert_all(preview)
        wait_for(lambda:s.document()['view']['ui'].get('initial_layout','')=='',30)
        s.idle();s.click('Вписать полотно');s.idle()
        saved=store.load(s.document()['id'])
        result['fresh_'+network]={'status':preview['status'],'records':count,'raw_evidence_count':len(saved['evidence']),
            'request_counts':preview.get('request_counts',{}),'worker_and_insert_seconds':round(time.monotonic()-started,2)}
        check('fresh_'+network+'_native_worker_parse_insert_readable',preview['status'] in ('partial','complete','timeout')
            and saved['view']['ui'].get('crypto_root_id')==wallet['id'] and wallet['attributes'].get('chain')==network
            and len(saved['evidence'])==count and bool(s.visible_node(wallet['id'])))
        capture('fresh-'+network+'-live')
    result['phase']='fresh_maigret'
    new_native_project(s)
    user=s.create('username','solvnox','solvnox');s.select(user['id']);s.click('Действия');wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'))
    s.pick('Инструмент узла','Maigret','maigret');s.pick('Режим Maigret','Свой охват','custom')
    sites=json.loads((observed_dir/'maigret-native-sites.json').read_text(encoding='utf-8'))
    s.fill('Сайты по имени',json.dumps(sites));s.fill('Тайм-аут сайта, с','5');s.fill('Параллельные проверки','4');s.fill('Лимит времени, с','70')
    s.click('Выполнить → просмотр');deadline=time.monotonic()+110;stream_seen=False;progress_seen=False
    while time.monotonic()<deadline:
        state=s.snapshot();preview=state['research_canvas'].get('preview',{})
        if preview.get('tool')=='username_maigret' and preview.get('results') and state['search']['busy']:stream_seen=True
        if (state['search'].get('maigret_progress') or {}).get('checked',0):progress_seen=True
        if preview.get('tool')=='username_maigret' and not state['search']['busy'] and not preview.get('running'):
            if not preview.get('results'):raise QaFailure('fresh_maigret_native_final_empty')
            break
        time.sleep(.2)
    else:raise QaFailure('fresh_maigret_native_deadline_or_empty')
    count=insert_all(preview);wait_for(lambda:s.document()['view']['ui'].get('initial_layout','')=='',30);capture('fresh-maigret-live')
    check('fresh_maigret_streamed_findings_before_completion',stream_seen and progress_seen)
    inserted=s.document()
    check('fresh_maigret_native_profiles_inserted',any(node['type']=='public_profile' for node in inserted['entities'])
        and inserted['view']['ui']['graph_mode']=='socmint' and inserted['view']['ui'].get('username_root_id')==user['id']
        and inserted['view']['layout']=='hierarchical' and bool(s.visible_node(user['id'])))
    result['fresh_maigret']={'status':preview['status'],'records':count,'sites_requested':len(sites),'progress_seen':progress_seen,'findings_while_worker_running':stream_seen}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--observed-dir',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--screenshots',type=Path,required=True);parser.add_argument('--source',action='store_true');parser.add_argument('--observed-only',action='store_true');parser.add_argument('--skip-dpi',action='store_true');parser.add_argument('--hold-first',action='store_true')
    args=parser.parse_args();validate_report_path(args.report)
    try:
        result=run(args.exe.resolve(),args.observed_dir.resolve(),args.report.resolve(),args.screenshots.resolve(),source=args.source,observed_only=args.observed_only,dpi=not args.skip_dpi,hold_first=args.hold_first)
        print(json.dumps({'passed':result['passed'],'checks':len(result['checks'])}),flush=True);return 0
    except Exception as error:
        if args.source:
            import traceback
            traceback.print_exc(file=sys.stderr)
        print(json.dumps({'passed':False,'error_type':type(error).__name__,'failure_code':str(error)[:180] if isinstance(error,QaFailure) else 'native_v5_acceptance_failed'}),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
