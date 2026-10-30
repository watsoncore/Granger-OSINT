"""Call the actual Gansar core in the existing isolated source worker only."""
import asyncio
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import time

if __package__:
    from .blockchain_contracts import CHAINS,EVM,policy,diagnostics
    from .blockchain_rows import normalize_dossier
else:
    from blockchain_contracts import CHAINS,EVM,policy,diagnostics
    from blockchain_rows import normalize_dossier


async def execute_gansar(query,options):
    import httpx
    from unittest.mock import patch
    from app.aggregator.analyzer import analyze_address
    from app.models.report import AddressReport
    from app.utils.detect import detect_candidates
    from app.utils.http import close_shared_clients
    from app.attribution import datasets
    from app.attribution import investigation_planner as planner
    args=query.get('options',{}).get('blockchain',{})
    args=args if isinstance(args,dict) else {}
    chosen=policy(args,options.get('research_mode','standard'))
    operation=args.get('operation','profile');target=query['text'].strip()
    end=time.monotonic()+min(chosen['seconds'],max(1,float(query.get('timeout',chosen['seconds']))-2))
    selected=args.get('chain','auto')
    if selected not in ('auto',*CHAINS):raise ValueError('Unsupported blockchain')
    if operation=='nft' and (selected not in ('auto','ton') or target.lower().startswith('0x')):
        return {'source':'blockchain','status':'unavailable','error_code':'nft_chain_not_implemented','results':[],
            'message':'Глубокая NFT-инвентаризация в исходном Gansar реализована для TON. Для EVM доступны фактически полученные transfer observations в profile/transactions; полной NFT-инвентаризации нет.'}
    ledger={'requests_used':0,'request_budget':chosen['requests'],'http_statuses':{},'providers_started':[],
        'provider_results':{},'finished':False,'budget_exhausted':False}
    latest=None;seen={};observed=datetime.now(timezone.utc).isoformat();last_snapshot=0;snapshot_bytes=0
    publish=options.get('_emit')
    def emit(row):
        if callable(publish):publish(row)
    def progress(row):
        if not isinstance(row,dict):return
        source=row.get('source');stage=row.get('stage','')
        if source and stage in ('source.start','source.result','request_started') and source not in ledger['providers_started']:ledger['providers_started'].append(source)
        if source and stage=='source.result':ledger['provider_results'][source]=row.get('status','unknown')
        emit({'event':'stage',**{k:v for k,v in row.items() if k in ('stage','source','status','transactions','assets','requests')},
            'providers_attempted':len(ledger['providers_started']),'http_requests':ledger['requests_used']})
    def snapshot(model,force=False):
        nonlocal latest,last_snapshot,snapshot_bytes
        latest=model.model_dump(mode='json') if hasattr(model,'model_dump') else model
        if not isinstance(latest,dict):raise ValueError('Invalid Gansar snapshot')
        if not force and time.monotonic()-last_snapshot<8:return
        last_snapshot=time.monotonic();latest['_observed_at']=observed
        import json
        size=len(json.dumps(latest,ensure_ascii=False,default=str).encode('utf-8'))
        if force or snapshot_bytes+size<=24_000_000:
            snapshot_bytes+=size
            emit({'event':'gansar_snapshot','report':latest,'source_diagnostics':diagnostics(latest,ledger)})
        for row in normalize_dossier(latest,operation=operation,max_transactions=chosen['transactions'],transport=ledger):
            import json
            fingerprint=json.dumps(row,sort_keys=True,default=str)
            if seen.get(row['id'])!=fingerprint:
                seen[row['id']]=fingerprint;emit({'event':'result','result':row})
    original=httpx.AsyncClient.send
    original_planner=planner.run_investigation_planner
    async def bounded_planner(report,sources,source_manager,**kwargs):
        if chosen['depth']==0:return kwargs.get('context',{})
        kwargs.update(max_http_requests=min(80,chosen['requests']//4),max_seconds=min(45,max(1,end-time.monotonic())),max_neighbors=chosen['wallets'])
        return await original_planner(report,sources,source_manager,**kwargs)
    async def measured_send(client,request,**kwargs):
        if time.monotonic()>=end:raise httpx.TimeoutException('Granger request deadline reached',request=request)
        if ledger['requests_used']>=chosen['requests']:
            ledger['budget_exhausted']=True
            raise httpx.RequestError('Granger request budget exhausted',request=request)
        ledger['requests_used']+=1
        response=await original(client,request,**kwargs)
        status=str(response.status_code);ledger['http_statuses'][status]=ledger['http_statuses'].get(status,0)+1
        if response.status_code==429:
            ledger.setdefault('retry_after',[]).append({'host':request.url.host,'value':str(response.headers.get('retry-after',''))[:80]})
        return response
    try:
        # Read bundled public catalogue only. Never consume the original
        # project's output/attribution_catalogue.json or refresh it implicitly.
        with patch.object(datasets,'DEFAULT_LOCAL_SNAPSHOT',Path.cwd()/'unused-local-catalogue.json'),patch.object(httpx.AsyncClient,'send',measured_send),patch.object(planner,'run_investigation_planner',bounded_planner),patch.object(planner,'MAX_HOPS',chosen['depth']),patch.object(planner,'MAX_HISTORY_ROWS',min(200,chosen['transactions'])):
            if operation=='nft' or target.lower().endswith('.ton'):
                from app.ton_nft.service import investigate_ton_nft,report_to_address_report
                from app.ton_nft.models import NFTIntelligenceReport
                saved=query.get('options',{}).get('_gansar_nft_resume')
                resume=NFTIntelligenceReport.model_validate(saved) if isinstance(saved,dict) else None
                if resume and args.get('scope','auto') not in ('auto',resume.scope):resume=None
                budget={'max_seconds':max(1,end-time.monotonic()),'max_requests':chosen['requests'],'max_pages':chosen['pages'],
                    'max_items':chosen['items'],'max_events':chosen['transactions']*3,'request_timeout':15,
                    'page_size':min(100,chosen['items']),'trace_depth':min(chosen['depth'],3),'max_wallets':chosen['wallets'],
                    'retries':0,'concurrency':2,'requests_per_second':1.0}
                nft=await investigate_ton_nft(target,mode='deep' if chosen['mode']=='deep' else 'standard',
                    scope=args.get('scope','auto'),
                    resume=resume is not None,investigation_id=resume.investigation_id if resume else None,_resume_report=resume,
                    store_path=Path.cwd()/'granger-nft.sqlite3',budget=budget,use_api_keys=False,
                    priority_scheduling=True,on_progress=progress,
                    on_checkpoint=lambda item:snapshot(report_to_address_report(item,include_owner_snapshot=False)))
                latest=report_to_address_report(nft,include_owner_snapshot=False).model_dump(mode='json')
            elif operation=='identity':
                reports=[]
                if target.lower().endswith('.eth') or any(chain in EVM for chain in detect_candidates(target)):
                    from app.sources.ethereum_ens import EthereumEnsSource
                    from app.sources.web3_identity import LensPublicSource
                    from app.sources.basenames import BaseNamesSource
                    from app.sources.eas_public import EasAttestationSource
                    from app.aggregator.analyzer import _merge
                    sources=[EthereumEnsSource(20)]
                    if target.lower().startswith('0x'):sources += [LensPublicSource(12),BaseNamesSource(15),EasAttestationSource(8)]
                    aggregate=AddressReport(target_address=target,detected_chains=['eth'])
                    for source in sources:
                        if time.monotonic()>=end:break
                        progress({'stage':'source.start','source':source.name})
                        try:
                            report=await asyncio.wait_for(source.fetch(target),max(.1,end-time.monotonic()))
                            aggregate=_merge(aggregate,report)
                            if source.name=='ethereum_ens' and report.ens_resolved_address:aggregate.target_address=report.ens_resolved_address
                            snapshot(aggregate)
                            progress({'stage':'source.result','source':source.name,'status':'completed'})
                        except asyncio.TimeoutError:progress({'stage':'source.result','source':source.name,'status':'timeout'})
                    latest=aggregate.model_dump(mode='json')
                else:return {'source':'blockchain','status':'unsupported','error_code':'unsupported_identity_network','results':[],
                    'message':'ENS/Lens/Basenames/EAS не применимы к этому формату. TON DNS исследуется через .ton/NFT operation.'}
            else:
                seed=None
                if target.lower().endswith('.eth'):
                    from app.sources.ethereum_ens import EthereumEnsSource
                    progress({'stage':'source.start','source':'ethereum_ens'})
                    seed=await EthereumEnsSource(20).resolve_name(target)
                    if not seed.ens_resolved_address or not seed.ens_profile.get('forward_verified'):
                        snapshot(seed,True)
                        return {'source':'blockchain','status':'partial','results':normalize_dossier(latest,operation='identity',transport=ledger),
                            'gansar_report':latest,'source_diagnostics':diagnostics(latest,ledger),'message':'ENS forward resolution не подтверждено; адрес не подставлялся.'}
                    target=seed.ens_resolved_address
                candidates=detect_candidates(target)
                if not candidates or selected!='auto' and selected not in candidates and not (selected in EVM and 'eth' in candidates):
                    return {'source':'blockchain','status':'invalid_arguments','error_code':'unsupported_chain_or_invalid_address','results':[],
                        'message':'Формат или checksum не соответствует поддерживаемой сети.'}
                saved=query.get('options',{}).get('_gansar_trace_resume')
                seed_report=AddressReport.model_validate(saved) if isinstance(saved,dict) else None
                report,_=await asyncio.wait_for(analyze_address(target,timeout_seconds=15,max_txs=chosen['transactions'],
                    selected_chains=[selected] if selected!='auto' else None,include_experimental=chosen['mode']!='quick',
                    deadline=asyncio.get_running_loop().time()+max(.1,end-time.monotonic()),continuous=False,
                    defer_graph=True,ens_seed=seed,initial_report=seed_report,progress=progress,on_checkpoint=snapshot,checkpoint_interval=2),max(.1,end-time.monotonic()))
                latest=report.model_dump(mode='json')
    except (asyncio.TimeoutError,TimeoutError):
        ledger['timeout']=True
    except Exception as error:
        import traceback
        ledger['engine_error']={'type':type(error).__name__,'frames':[frame.name for frame in traceback.extract_tb(error.__traceback__)[-8:]]}
    finally:
        await close_shared_clients()
    ledger['finished']=not ledger.get('timeout')
    if not latest:return {'source':'blockchain','status':'timeout' if ledger.get('timeout') else 'unavailable',
        'error_code':'source_timeout' if ledger.get('timeout') else 'no_gansar_report','results':[],
        'source_diagnostics':diagnostics({},ledger),'message':'Gansar не вернул пригодный DTO в установленный срок.'}
    snapshot(latest,True)
    rows=normalize_dossier(latest,operation=operation,max_transactions=chosen['transactions'],transport=ledger)
    health=diagnostics(latest,ledger)
    usable=len(rows)>1
    failures=ledger.get('engine_error') or ledger.get('timeout') or ledger['budget_exhausted'] or any(r['status'] not in ('ok','empty','skipped') for r in health['health'])
    return {'source':'blockchain','status':'partial' if failures and usable else 'complete' if usable else 'empty' if not failures else 'unavailable',
        'results':rows,**({'gansar_report':latest} if not callable(publish) else {}),'source_diagnostics':health,'requests_used':ledger['requests_used'],
        'message':'Получены фактические Gansar observations. Полнота/ошибки каждого провайдера сохранены отдельно.',
        'engine_error':ledger.get('engine_error'),
        'error_code':'request_budget_exhausted' if ledger['budget_exhausted'] else 'source_timeout' if ledger.get('timeout') else 'gansar_engine_error' if ledger.get('engine_error') else ''}
