"""Actual mouse-driven node→worker→evidence→encrypted graph acceptance.

Only public solvnox and the known public TON fixture are queried. Profiles/logs
are automatically removed; optional own-window screenshots contain QA data only.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import NativeSession,isolated_environment,wait_for,process_image,QaFailure,validate_report_path,research_labels
TON='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
class Session(NativeSession):
 def __init__(self,executable,directory,source=False):
  super().__init__(executable,directory);self.source=source
  if source:self.executable=Path(sys._base_executable).resolve()
 def start(self,number,**kwargs):
  if not self.source:return super().start(number,**kwargs)
  self.owned_pid=None
  with (self.directory/f'process-{number}.log').open('wb') as stream:
   self.process=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
  self.owned_pid=wait_for(self.status,90)['pid'];wait_for(lambda:self.status().get('desktop',{}).get('ready'),60);self.show_workspace()
 def find(self,label,*,role=None):
  d=self.dom()
  elements=[e for e in d.get('elements',[]) if e['width']>0]
  labels=research_labels(label)
  if role:found=next((e for e in elements if e.get('role')==role and any(e.get('text','').startswith(value) for value in labels)),None)
  else:found=next((e for e in elements if e.get('label') in labels),None) or next((e for e in elements if e.get('text') in labels),None)
  return found,d
 def click(self,label,*,role=None):
  for attempt in range(28):
   e,d=self.find(label,role=role)
   if e and e.get('hit',True) and 0<=e['y']+min(16,e['height']/2)<d['height']:
    if e.get('disabled'):time.sleep(.15);continue
    self.action('input',{'kind':'click','at':[min(d['width']-5,e['x']+e['width']/2),e['y']+min(16,e['height']/2)]});return
   if not e:
    # A portal can appear after the trigger's pointer event has settled.
    # Scrolling the inspector cannot create a missing portal/input.
    time.sleep(.1);continue
   parent=(e or {}).get('scroll')
   at=[d['width']-65,d['height']-120] if not parent else [min(d['width']-10,max(10,parent['x']+parent['width']*.65)),min(d['height']-20,max(50,parent['y']+parent['height']*.6))]
   boundary=(parent['y']+15) if parent else 210
   # Keep each scroll smaller than the visible container. A fixed six-notch
   # jump oscillates past controls in the new split inspector/results dock.
   step=min(360,max(60,round((parent['height'] if parent else 600)*.4)))
   self.action('input',{'kind':'wheel','at':at,'delta':step if e and e['y']<boundary else -step})
  raise QaFailure('control_not_reached_'+label)
 def fill(self,label,text):
  self.click(label);self.action('input',{'kind':'key','key':'all','ctrl':True});self.action('input',{'kind':'text','text':text})
 def pick(self,label,option,search=None):
  for attempt in range(3):
   self.click(label)
   try:
    wait_for(lambda:e if (e:=self.find('Найти: '+label)[0]) and e.get('hit',True) else None,3)
    break
   except QaFailure:
    self.action('input',{'kind':'key','key':'escape'})
  else:raise QaFailure('picker_did_not_open_'+label)
  if search:
   self.fill('Найти: '+label,search)
   # Radix repositions its portal after filtering; observe the settled item
   # rather than clicking coordinates from the previous menu height.
   wait_for(lambda:e if (e:=self.find(option,role='menuitemradio')[0]) and e.get('hit',True) else None,8)
   time.sleep(.2)
  self.click(option,role='menuitemradio')
  wait_for(lambda:e if (e:=self.find(label)[0]) and option in e['text'] else None,8)
 def canvas(self):return self.snapshot().get('research_canvas',{})
 def document(self):return self.canvas().get('document',{})
 def settled(self):return wait_for(lambda:d if (d:=self.canvas()).get('document') and not d.get('busy') else None)['document']
 def metrics(self):
  previous=self.canvas().get('metrics',{}).get('generation',0);self.action('research_canvas_metrics')
  return wait_for(lambda:m if (m:=self.canvas().get('metrics',{})).get('generation',0)>previous else None)
 def select(self,identifier):
  # Center the actual stored node using the existing finite command, then click
  # its real canvas location; tool/config/run/insert remain mouse actions.
  doc=self.settled();p=doc['view']['positions'][identifier]
  self.action('research_canvas_edit',{'id':doc['id'],'revision':doc['revision'],'operation':'view','arguments':{'view':{'viewport':{'x':350-p['x'],'y':220-p['y'],'scale':1}}}})
  wait_for(lambda:self.document().get('revision',0)>doc['revision']);m=self.metrics()['canvas']
  filtered=False
  if not any(n['id']==identifier for n in json.loads(m['qaNodes'])):
   self.fill('Поиск на полотне',next(n['label'] for n in doc['entities'] if n['id']==identifier));m=self.metrics()['canvas'];filtered=True
  n=next(n for n in json.loads(m['qaNodes']) if n['id']==identifier)
  self.action('input',{'kind':'click','at':[m['x']+n['x'],m['y']+n['y']]})
  if filtered:self.fill('Поиск на полотне','')
 def create(self,kind,label,value,chain=None):
  if self.document().get('entities'):self.click('Объект')
  self.pick('Тип нового узла',{'username':'Никнейм','blockchain_address':'Криптокошелёк','domain':'Домен','infrastructure_asset':'IP / сеть'}[kind],kind)
  self.fill('Название узла',label);self.fill('Адрес нового объекта' if chain else 'Значение нового объекта',value)
  # TON's checksum/raw address unambiguously supplies its network in Auto mode.
  old=len(self.document().get('entities',[]));self.click('Добавить узел')
  doc=wait_for(lambda:d if len((d:=self.document()).get('entities',[]))>old else None)
  return next(n for n in doc['entities'] if n['label']==label)

def run(exe,report_path,shots=None,source=False,stress=False):
 from PySide6.QtCore import QCoreApplication
 from grangerpet.config import Settings,SettingsStore
 from grangerpet.agent_journal import InvestigationJournal
 from grangerpet.research_canvas import CanvasStore
 app=QCoreApplication.instance() or QCoreApplication([])
 result={'origin':'native-source-live' if source else 'frozen-live','mocked':False,'passed':False,'checks':[],'gateway_calls':0,'screenshots':[]}
 if not source:result['exe_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
 def save():
  if report_path:report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 def check(name,ok):
  result['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps(result['checks'][-1]),flush=True)
  if not ok:raise QaFailure(name)
 with tempfile.TemporaryDirectory(prefix='.granger-qa-v4-',dir=ROOT) as name:
  directory=Path(name)
  with isolated_environment(directory):
   SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
   s=Session(exe,directory,source);store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
   def shot(name):
    s.command('qa_snapshot',{'name':name});time.sleep(.3);p=directory/(name+'-search.png')
    if shots and p.exists():
     shots.mkdir(parents=True,exist_ok=True);target=shots/(name+'.png');target.write_bytes(p.read_bytes());result['screenshots'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
   def execute(tool):
    before=s.canvas().get('preview',{}).get('token');samples=[];result['last_form']=[{k:e.get(k) for k in ('label','value','type','disabled')} for e in s.dom().get('elements',[]) if e.get('label') and e.get('type') in ('text','number','textarea','select-one')];save();s.click('Выполнить → просмотр')
    started=time.monotonic()
    while time.monotonic()-started<150:
     snap=s.snapshot();c=snap.get('research_canvas',{});p=c.get('preview',{})
     progress=snap.get('search',{}).get('maigret_progress')
     if tool=='username_maigret' and progress:samples.append(progress)
     if p.get('token')!=before and p.get('tool')==tool and not snap['search']['busy']:
      check(tool+'_returns_actual_worker_results',p['status'] in ('complete','partial','timeout') and bool(p['results']))
      return p,samples
     if time.monotonic()-started>4 and not snap['search']['busy'] and not p.get('token')!=before:
      result['failed_ui_text']=s.dom().get('text','')[-6500:];save();raise QaFailure('tool_not_started_'+tool)
     if c.get('error'):raise QaFailure('canvas_execution_error_'+c['error'][:100])
     time.sleep(.25)
    raise QaFailure('worker_result_deadline_'+tool)
   try:
    s.start(0);s.click('Поиск');s.action('tools_refresh');wait_for(lambda:not s.snapshot().get('toolsChecking'),90)
    s.click('Моё полотно');s.click('Новое');wait_for(lambda:s.document().get('id'));s.click('Развернуть')
    user=s.create('username','solvnox','solvnox');owner=s.document()['id']
    check('mouse_created_username_keeps_type_and_machine_value',user['type']=='username' and user['attributes']['username']=='solvnox')
    s.select(user['id']);s.click('Действия');wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'))
    check('no_incompatible_default_tool',s.find('Инструмент узла')[0]['text']!='network_rdap')
    s.pick('Инструмент узла','Maigret','maigret');check('mouse_selected_maigret_prefills_username',s.find('Никнейм Maigret')[0]['value']=='solvnox');shot('username-maigret')
    s.pick('Режим Maigret','Свой охват','custom')
    s.fill('Сайты по имени','["GitHub","YouTube","TikTok","Wikipedia","WordPressOrg","GooglePlayStore"]')
    s.fill('Тайм-аут сайта, с','3');s.fill('Параллельные проверки','3');s.fill('Лимит времени, с','25')
    # Include mirrors=false via the real HTML select keyboard.
    s.click('Включать зеркала');s.action('input',{'kind':'key','key':'home'});s.action('input',{'kind':'key','key':'down'});s.action('input',{'kind':'key','key':'down'});s.action('input',{'kind':'key','key':'enter'})
    preview,samples=execute('username_maigret');check('actual_maigret_progress_seen',bool(samples) and max(p.get('checked',0) for p in samples)>0)
    shot('maigret-results')
    selected=preview['results'][:2];allrows=preview['results']
    # The first 100 are initially selected; uncheck all but the first two.
    for index in range(2,min(100,len(allrows))):
     controls=[e for e in s.dom()['elements'] if e.get('type')=='checkbox']
     e=controls[index]
     if not 45<e['y']<s.dom()['height']-28:break
     if e.get('checked'):s.action('input',{'kind':'click','at':[e['x']+5,e['y']+5]})
    s.click('Добавить выбранные ('+str(min(2,len(allrows)))+')')
    wait_for(lambda:len(s.document()['evidence'])>=len(selected));doc=s.settled();raw=store.load(owner)
    check('maigret_profiles_enrich_original_username_without_owner_claim',any(n['type']=='public_profile' for n in doc['entities']) and next(n for n in doc['entities'] if n['id']==user['id'])['type']=='username' and any(e['relation_type']=='returned_for_query' and e['from_id']==user['id'] and e['attributes'].get('owner_verified') is False for e in doc['relations']))
    result['maigret']={'result_count':len(allrows),'inserted_evidence':len(raw['evidence']),'progress_snapshots':len(samples),'coverage':s.snapshot()['search'].get('maigret_progress')};save()
    wallet=s.create('blockchain_address','dsdsd',TON,'ton');s.select(wallet['id']);s.click('Действия')
    wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'));check('switch_username_to_wallet_resets_tool',s.find('Инструмент узла')[0]['text']!='Maigret')
    s.pick('Инструмент узла','Gansar','gansar');address=s.find('Адрес кошелька или контракта')[0]['value']
    check('mouse_selected_gansar_uses_address_not_display_label',address.startswith('0:') and address!='dsdsd')
    s.pick('Операция Gansar','Обзор адреса','profile');shot('wallet-gansar')
    # Runtime budget remains the existing standard default; no private key used.
    preview,_=execute('blockchain_gansar');shot('gansar-results')
    count=len(preview['results']);s.click('Выбрать все ('+str(count)+')');s.click('Добавить выбранные ('+str(count)+')')
    wait_for(lambda:s.document().get('view',{}).get('ui',{}).get('crypto_root_id')==wallet['id']);doc=s.settled();raw=store.load(owner)
    check('gansar_insert_selects_wallet_projection_and_preserves_raw_evidence',doc['view']['ui']['graph_mode']=='wallet' and len(raw['evidence'])>=len(selected)+count)
    s.pick('Раскладка полотна','Вокруг кошелька','wallet')
    wait_for(lambda:s.document()['view']['layout']=='wallet');s.metrics();shot('crypto-graph')
    records=[row for row in raw['evidence'] if row.get('tool')=='blockchain_gansar' or row.get('provenance',{}).get('tool')=='blockchain_gansar']
    result['gansar']={'status':preview['status'],'preview_records':len(preview['results']),'inserted_records':count,'nodes':len(doc['entities']),'relations':len(doc['relations']),'canonical_address':address,'raw_evidence_sha256':hashlib.sha256(json.dumps(raw['evidence'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()};save()
    # Repeat insertion by actual button; membership/evidence must deduplicate.
    s.click('Результаты для добавления');s.click('Добавить выбранные ('+str(count)+')');s.settled()
    repeated=store.load(owner)
    def facts(nodes):
     import copy
     values=copy.deepcopy(nodes)
     for node in values:node['attributes'].pop('media',None)
     return values
    check('repeat_insert_deduplicates_evidence_and_nodes',facts(repeated['entities'])==facts(raw['entities']) and repeated['evidence']==raw['evidence'])
    wait_for(lambda:s.metrics().get('queue_pending',0)==0)
    repeated=store.load(owner);saved={k:repeated[k] for k in ('entities','relations','evidence','annotations','view')};s.stop();s.start(1);s.click('Поиск');s.click('Моё полотно');s.action('research_canvas_open',{'id':owner})
    wait_for(lambda:s.document().get('id')==owner);reopened=store.load(owner)
    check('real_exe_restart_preserves_types_values_evidence_positions',all((facts(reopened[k])==facts(v)) if k=='entities' else reopened[k]==v for k,v in saved.items()))
    shot('reopened')
    if not source:
     s.click('Развернуть')
     btc=s.create('blockchain_address','BTC QA','1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa','btc')
     s.select(btc['id']);s.click('Действия');wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'))
     s.pick('Инструмент узла','Gansar','gansar');btc_preview,_=execute('blockchain_gansar')
     btc_count=len(btc_preview['results']);s.click('Выбрать все ('+str(btc_count)+')');s.click('Добавить выбранные ('+str(btc_count)+')')
     wait_for(lambda:s.document()['view']['ui'].get('crypto_root_id')==btc['id'])
     btc_saved=store.load(owner)
     check('bitcoin_native_worker_parse_insert_provenance',next(n for n in btc_saved['entities'] if n['id']==btc['id'])['attributes']['chain']=='btc' and any(row['provenance'].get('query')==btc['attributes']['address'] for row in btc_saved['evidence']))
     result['bitcoin']={'status':btc_preview['status'],'records':btc_count,'provenance_retained':True}
     # Exercise genuine Full planning/cancellation, not a completed 6434-site claim.
     s.pick('Представление полотна','Все объекты','manual');s.select(user['id']);s.click('Действия');wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'));s.pick('Инструмент узла','Maigret','maigret');s.pick('Режим Maigret','Полный','full');s.click('Выполнить → просмотр')
     full=wait_for(lambda:snap['search']['maigret_progress'] if (snap:=s.snapshot()).get('search',{}).get('busy') and (snap['search'].get('maigret_progress') or {}).get('scheduled',0)>1000 else None,40)
     check('native_full_maigret_uses_original_database_not_ten_sites',full['scheduled']>1000)
     s.click('Остановить инструмент');wait_for(lambda:not s.snapshot()['search']['busy'],35)
     cancelled=s.snapshot();status=next(a['status'] for a in cancelled['activity'] if a['id']=='username_maigret')
     check('native_full_cancellation_settles_and_keeps_graph',status=='cancelled' and store.load(owner)['evidence']==btc_saved['evidence'])
     result['full_cancel']={'scheduled':full['scheduled'],'status':status,'coverage':cancelled['search'].get('maigret_progress')}
     s.pick('Представление полотна','Все объекты','manual')
     ip=s.create('infrastructure_asset','IP QA','66.249.67.41')
     domain=s.create('domain','Domain QA','example.org')
     # Email/phone use the same real picker with display labels from the server.
     def create_extra(kind,label,value):
      s.click('Объект');s.pick('Тип нового узла',{'email':'Email','phone':'Телефон'}[kind],kind);s.fill('Название узла',label);s.fill('Значение нового объекта',value);n=len(s.document()['entities']);s.click('Добавить узел')
      created=wait_for(lambda:d if len((d:=s.document())['entities'])>n else None)
      return next(x for x in created['entities'] if x['label']==label)
     email=create_extra('email','Email QA','research@example.org');phone=create_extra('phone','Phone QA','+14155552671')
     switches=[]
     for node,tool_id in [(ip,'network_rdap'),(user,'username_maigret'),(btc,'blockchain_gansar'),(domain,'domain_lookup'),(email,'email_holehe'),(phone,'phone_metadata')]:
      s.select(node['id']);s.click('Действия');wait_for(lambda:not s.find('Инструмент узла')[0].get('disabled'))
      check('node_switch_clears_stale_tool_'+node['type'],'Выберите' in s.find('Инструмент узла')[0]['text'])
      tool_meta=next(t for t in s.snapshot()['tools'] if t['id']==tool_id)
      if tool_meta['available']:
       s.pick('Инструмент узла',tool_meta['name'],tool_id);check('mouse_selects_typed_tool_'+node['type'],tool_meta['name'] in s.find('Инструмент узла')[0]['text'])
       if tool_id=='network_rdap':
        ip_preview,_=execute('network_rdap');check('ip_rdap_real_result_from_typed_node',bool(ip_preview['results']))
      switches.append({'entity_type':node['type'],'tool':tool_id,'runtime_available':tool_meta['available']})
     result['entity_switching']=switches
    if not source:
     s.stop()
     observed=directory/'observed-gansar.json'
     observed.write_text(json.dumps({'tool':'blockchain_gansar','status':result['gansar']['status'],'mock':False,'query':address,'results':records},ensure_ascii=False),encoding='utf-8')
     output=directory/'stress'
     with (directory/'stress.log').open('wb') as stream:
      completed=subprocess.run([sys.executable,str(ROOT/'scripts/qa_canvas_stress.py'),'--exe',str(exe),'--output',str(output),'--observed-result',str(observed)],cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
     data=json.loads((output/'report.json').read_text(encoding='utf-8')) if (output/'report.json').exists() else {}
     check('frozen_native_stress_50_100_500_1000_5000_and_real_crypto',completed.returncode==0 and data.get('passed') is True and data.get('exe_sha256')==result['exe_sha256'])
     result['performance']={'metric_semantics':data['metric_semantics'],'cases':[{key:case[key] for key in ('data_origin','underlying_nodes','edges','open_and_expand_seconds','paint_ms','event_to_paint_ms','resources') if key in case} for case in data['cases']]}
     if shots:
      for p in output.glob('observed-*-search.png'):
       target=shots/'observed-crypto.png';target.write_bytes(p.read_bytes());result['screenshots'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    result.pop('last_form',None);result.pop('failed_ui_text',None);result['passed']=True;save()
   except BaseException as error:
    result['failed_controls']=[{k:e.get(k) for k in ('label','text','role','disabled','hit','x','y','width','height','scroll')} for e in s.dom().get('elements',[]) if e.get('label','') in ('Инструмент узла','Найти: Инструмент узла') or e.get('role')=='menuitemradio']
    result.update(passed=False,error_type=type(error).__name__,failure_code=str(error)[:220]);save();raise
   finally:s.stop()
 result['temporary_profile_removed']=not directory.exists();result['selection_method']='Qt mouse on real menuitemradio and run/insert controls; viewport centering only uses finite QA action';save();return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--screenshots',type=Path);p.add_argument('--source',action='store_true');a=p.parse_args();validate_report_path(a.report)
 try:r=run(a.exe.resolve(),a.report,a.screenshots,a.source);print(json.dumps({'passed':r['passed'],'checks':len(r['checks'])}));return 0
 except Exception as error:
  print(json.dumps({'passed':False,'error_type':type(error).__name__,'failure_code':str(error)[:220] if isinstance(error,QaFailure) else 'native_acceptance_failed'}),flush=True);return 1
if __name__=='__main__':raise SystemExit(main())
