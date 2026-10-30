"""Project actual Gansar DTOs into Granger findings without a second collector."""
from datetime import datetime,timezone
import hashlib
import json

if __package__:
    from .blockchain_contracts import exact,diagnostics
    from .blockchain_analytics import analyze_transactions,canonical_address
else:
    from blockchain_contracts import exact,diagnostics
    from blockchain_analytics import analyze_transactions,canonical_address


def _items(value):return [row for row in value if isinstance(row,dict)] if isinstance(value,list) else []
def _dict(value):return value if isinstance(value,dict) else {}


def finding_fields(value):
    """Retain source/event references; raw provider bodies live in the dossier."""
    if isinstance(value,dict):return {key:finding_fields(item) for key,item in value.items() if key not in ('raw','raw_payload','response_body')}
    if isinstance(value,list):return [finding_fields(item) for item in value[:50]]
    return value


def compact_observation(value,depth=0,budget=None):
    """A bounded finding projection; the complete vendor DTO is stored separately."""
    budget=budget if budget is not None else [2000]
    budget[0]-=1
    if budget[0]<0 or depth>6:return '[см. полный сохранённый dossier]'
    if isinstance(value,dict):return {key:compact_observation(item,depth+1,budget) for key,item in list(value.items())[:50]}
    if isinstance(value,list):return [compact_observation(item,depth+1,budget) for item in value[:30]]
    if isinstance(value,str):return value[:1500]
    return value


def normalize_dossier(report,*,operation='profile',max_transactions=200,transport=None,max_records=2000):
    if not isinstance(report,dict) or not isinstance(report.get('target_address'),str):raise ValueError('Invalid Gansar report')
    target=report['target_address'];chains=report.get('detected_chains',[]);rows=[]
    observed=report.get('_observed_at') or datetime.now(timezone.utc).isoformat()
    def add(kind,identifier,title,details,*,chain='',url='',description='',status='source_reported',source='Gansar'):
        if len(rows)>=max_records:return
        details=finding_fields(details)
        rows.append({'id':kind+':'+str(identifier),'type':kind,'title':str(title)[:300],
            'platform':'Блокчейн · '+(chain.upper() or 'Gansar'),'url':str(url or ''),
            'description':str(description)[:1600],'status':status,'sources':['blockchain','Gansar',str(source)],
            'details':{**details,'target_address':target,'chain':chain,'acquisition':'public_blockchain_observation',
                'capability':'blockchain_gansar','source_record':True,
                'identity_verified':False,'collected_at':details.get('collected_at') or observed}})
    health=diagnostics(report,transport)
    counts={key:len(report.get(key,[])) if isinstance(report.get(key),list) else 0
        for key in ('balances','transactions','tokens','ton_assets','counterparties','contract_observations')}
    add('blockchain_summary','|'.join(chains)+'|'+target,'Сводка blockchain-исследования',
        {'detected_chains':chains,'counts':counts,'source_diagnostics':health,'coverage':_dict(report.get('coverage')),
         'operation':operation,'input_resolution':_dict(report.get('input_resolution')),
         'warnings':report.get('warnings',[])[:20],'errors':report.get('errors',[])[:20]},
        description='Сети: '+', '.join(chains)+f". Балансы: {counts['balances']}; токены: {counts['tokens']}; NFT/TON-активы: {counts['ton_assets']}; транзакции: {counts['transactions']}. "
            +f"Коллекторов запущено: {health['providers_attempted']}; HTTP-запросов: {health['http_requests'] if health['http_requests'] is not None else 'неизвестно'}. "
            +'Источники: '+'; '.join(row['provider']+': '+row['status']+' ('+row['reason_code']+')' for row in health['health'][:12])+'. Полнота не определяется числом карточек.')
    include=lambda *names:operation in ('profile','all') or operation in names
    if include('transactions','trace') and report.get('transactions'):
        network=chains[0] if len(chains)==1 else ''
        analysis=analyze_transactions(_items(report.get('transactions')),target,network)
        # Compute ALL returned transfers before normal row pagination; only the
        # model-facing peer ranking is bounded, totals still cover the full DTO.
        analysis['counterparties']=analysis['counterparties'][:30]
        analysis['peer_ranking_bounded']=analysis['unique_counterparties']>30
        add('blockchain_analytics',network+'|'+target,'Анализ полученной транзакционной выборки',
            {'data':analysis,'computation':'local_decimal_aggregation','input_coverage':'full_returned_gansar_dto'},
            chain=network,description=f"Уникальных событий: {analysis['unique_events']}; контрагентов: {analysis['unique_counterparties']}. Полная история сети не установлена.")
    if include('balances','assets'):
        for row in _items(report.get('balances')):
            amount=exact(row.get('amount_decimal',row.get('amount')))
            add('balance',f"{row.get('chain')}|{row.get('address',target)}|{row.get('asset')}",str(row.get('asset'))+' · '+(amount or 'неизвестно'),
                {**row,'amount_decimal':amount},chain=row.get('chain',''),url=row.get('url'),source=row.get('source'),
                description='Наблюдаемый баланс; отсутствие ответа не означает нулевой баланс.')
        for row in _items(report.get('tokens')):
            amount=exact(row.get('amount_decimal',row.get('amount')))
            raw=_dict(row.get('raw'));media=next((raw.get(k) for k in ('image_url','image','logo','logo_url','icon') if isinstance(raw.get(k),str)),'')
            detail={**{k:v for k,v in row.items() if k!='raw'},'amount_decimal':amount,
                'metadata':{k:raw[k] for k in ('decimals','token_id','token_standard','image_url','image','logo','logo_url','price','price_usd','price_timestamp','price_source') if k in raw},
                'image_url':media,'metadata_verified':False}
            add('token_asset',f"{row.get('chain')}|{target}|{row.get('contract') or row.get('symbol')}",
                str(row.get('name') or row.get('symbol') or 'Токен'),detail,chain=row.get('chain',''),url=row.get('url'),source=row.get('source'),
                description=f"Количество: {amount if amount is not None else 'неизвестно'}; статус: {row.get('holding_status','unknown')}. Тикер/название не подтверждают подлинность.")
    if include('assets','nft'):
        for row in _items(report.get('ton_assets')):
            detail={k:v for k,v in row.items() if k!='raw'};detail['metadata_verified']=False
            raw=_dict(row.get('raw'))
            collection=raw.get('collection_address') or _dict(raw.get('collection')).get('address')
            if isinstance(collection,str):detail['collection_address']=collection
            add('nft_asset' if row.get('type') in ('nft','collectible','gift','domain','username') else 'token_asset',
                'ton|'+canonical_address('ton',row.get('asset_id')),row.get('title') or row.get('name') or row.get('asset_id'),detail,
                chain='ton',url=row.get('evidence_url') or row.get('external_url'),source=row.get('source'),
                description=f"Тип: {row.get('type')}; владение: {row.get('ownership_status','unknown')}; свежая on-chain проверка: {row.get('ownership_verified') is True}. Метаданные не подтверждают подлинность.")
    if include('transactions','trace'):
        for row in _items(report.get('transactions'))[:max_transactions]:
            amount=exact(row.get('amount_decimal',row.get('amount')))
            detail={k:v for k,v in row.items() if k!='raw'};detail['amount_decimal']=amount
            raw=_dict(row.get('raw'))
            detail['event_semantics']={k:raw[k] for k in ('type','action_index','event_id','asset_type','token_contract','token_id','method','opcode') if k in raw}
            add('transaction',f"{row.get('chain')}|{row.get('event_id') or row.get('tx_hash')}",row.get('tx_hash') or 'Blockchain event',detail,
                chain=row.get('chain',''),url=row.get('url'),source=row.get('source'),
                description=f"{row.get('from_address') or '?'} → {row.get('to_address') or '?'}; {amount if amount is not None else 'сумма неизвестна'} {row.get('asset') or ''}; направление: {row.get('direction','unknown')}.")
    if include('trace','transactions','attribution'):
        for row in _items(report.get('counterparties')):
            add('blockchain_counterparty',f"{row.get('chain')}|{target}|{row.get('address')}",row.get('address') or 'Контрагент',row,
                chain=row.get('chain',''),description=f"Наблюдаемых взаимодействий: {row.get('tx_count','unknown')}. Общий владелец не установлен.")
    if include('labels','attribution'):
        for row in _items(report.get('labels')):
            add('label',f"{row.get('chain')}|{row.get('address')}|{row.get('source')}|{row.get('label')}",row.get('label') or 'Метка источника',
                {**row,'owner_verified':False},chain=row.get('chain',''),url=row.get('url'),source=row.get('source'),status='unconfirmed',
                description='Метка источника; не доказательство личности или контроля адреса.')
    if include('contracts','attribution'):
        for row in _items(report.get('contract_observations')):
            identifier=hashlib.sha256(json.dumps(row,sort_keys=True,default=str).encode()).hexdigest()[:24]
            add('contract_observation',identifier,'Наблюдение контракта',row,chain=row.get('blockchain',''),url=row.get('source_url'),source=row.get('source'),
                description='Публичная проверка кода/развёртывания или состояния. Название контракта не устанавливает владельца.')
    if include('identity'):
        profile=_dict(report.get('ens_profile'))
        if profile:
            add('web3_identity','ens|'+target,'ENS · '+str(report.get('ens_name') or report.get('reverse_ens') or target),
                {'provider':'ethereum_ens','address':report.get('ens_resolved_address') or target,'name':report.get('ens_name') or report.get('reverse_ens'),
                 'forward_address':report.get('ens_resolved_address'),'reverse_valid':report.get('ens_reverse_valid'),
                 'avatar_url':report.get('avatar'),'profile':profile,'text_records':_dict(report.get('text_records')),
                 'record_claim_status':'self_published_profile_record','owner_verified':False},chain='eth',
                description='Forward/reverse resolution и публичные записи. Имя не устанавливает личность человека.')
        for outcome in _items(_dict(report.get('public_address_context')).get('outcomes')):
            for claim in _items(outcome.get('claims')):
                key=claim.get('claim_id') or hashlib.sha256(json.dumps(claim,sort_keys=True,default=str).encode()).hexdigest()[:24]
                add('web3_identity',str(outcome.get('source'))+'|'+str(key),str(claim.get('object_type') or claim.get('relation') or outcome.get('source')),
                    {**claim,'provider':outcome.get('source'),'source_status':outcome.get('status'),'owner_verified':False},
                    chain=outcome.get('chain',''),url=claim.get('source_url') or outcome.get('source_url'),source=outcome.get('source'),
                    description='Публичное source-scoped утверждение. Аттестация, имя или роль не устанавливают личность.')
    if include('attribution','trace'):
        for key in ('wallet_migration','behavioral_fingerprint','wallet_timeline','asset_paths','counterparty_ranking','activity_chains','service_detections',
                    'ton_activity_intelligence','tron_activity_intelligence','dogecoin_activity_intelligence','ton_service_intelligence','attribution_intelligence'):
            value=report.get(key)
            if value:
                add('blockchain_analysis',target+'|'+key,key,{'analysis_type':key,'data':compact_observation(value),'inference_not_identity':True,'projection_bounded':True},
                    description='Аналитическая проекция существующего Gansar по собранным наблюдениям. Гипотезы не являются независимым подтверждением.',status='hypothesis')
    if include('assets','nft','contracts','attribution'):
        for key in ('financial_summary','nft_intelligence','bitcoin','dogecoin','bsc','tron','solana','telegram_identities','risk_flags'):
            value=report.get(key)
            if value:
                add('blockchain_context',target+'|'+key,key,{'section':key,'data':compact_observation(value),'projection_bounded':True},
                    description='Структурированные сведения существующего Gansar; полный исходный DTO сохранён отдельно. Риск-флаг или публичная метка не устанавливают личность.',status='unconfirmed' if key in ('risk_flags','telegram_identities') else 'source_reported')
    return rows
