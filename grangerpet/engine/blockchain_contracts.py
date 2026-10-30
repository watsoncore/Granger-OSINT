"""Shared typed Gansar operations; usable by the headless vendor interpreter."""
from decimal import Decimal, InvalidOperation
import re

CHAINS=('btc','doge','eth','bsc','polygon','arbitrum','optimism','avalanche','tron','ton','solana')
EVM=frozenset(('eth','bsc','polygon','arbitrum','optimism','avalanche'))
OPERATIONS=('profile','balances','assets','transactions','nft','identity','contracts','labels','attribution','trace','cached')
MODES={
    'quick':{'seconds':45,'transactions':50,'requests':60,'pages':2,'items':40,'depth':0,'wallets':1},
    'standard':{'seconds':90,'transactions':200,'requests':160,'pages':6,'items':120,'depth':1,'wallets':4},
    'deep':{'seconds':240,'transactions':1000,'requests':500,'pages':20,'items':500,'depth':2,'wallets':10},
}
INPUT_SCHEMA={'type':'object','properties':{
    'address':{'type':'string','minLength':1,'maxLength':200},
    'operation':{'type':'string','enum':list(OPERATIONS)},
    'chain':{'type':'string','enum':['auto',*CHAINS]},
    'mode':{'type':'string','enum':list(MODES)},
    'limit':{'type':'integer','minimum':1,'maximum':1000},
    'depth':{'type':'integer','minimum':0,'maximum':3},
    'scope':{'type':'string','enum':['auto','wallet','item','collection','trace']},
    'refresh':{'type':'boolean'},
    'section':{'type':'string','enum':['all','balances','assets','transactions','nft','identity','contracts','labels','attribution']},
    },'required':['address'],'additionalProperties':False}


def policy(args,default_mode='standard'):
    mode=args.get('mode',default_mode)
    if mode not in MODES:raise ValueError('Unsupported research mode')
    result={**MODES[mode],'mode':mode}
    if 'limit' in args:result['transactions']=max(1,min(MODES[mode]['transactions'],int(args['limit'])))
    if 'depth' in args:result['depth']=max(0,min(3,int(args['depth'])))
    return result


def reason(status,details='',*,error_code='',budget_exhausted=False):
    """Use actual structured status/detail; never infer success from row count."""
    text=str(details).casefold();code=str(error_code).casefold()
    if budget_exhausted or 'budget' in code or 'budget exhausted' in text:return 'REQUEST_BUDGET_EXHAUSTED'
    if status in ('disabled','adapter_disabled'):return 'ADAPTER_DISABLED'
    if status in ('auth_required','missing_optional_api_key') or 'api key' in text or 'key required' in text:return 'MISSING_OPTIONAL_API_KEY'
    if status=='unsupported' or 'unsupported chain' in text:return 'NO_ADAPTER'
    if re.search(r'(?<!\d)403(?!\d)',text) or status in ('forbidden','http_403'):return 'HTTP_403'
    if re.search(r'(?<!\d)429(?!\d)',text) or status in ('rate_limited','http_429'):return 'HTTP_429'
    if status=='timeout' or 'timed out' in text or 'timeout' in text:return 'SOURCE_TIMEOUT'
    if 'robots' in text:return 'ROBOTS_RESTRICTED'
    if any(word in text for word in ('getaddrinfo','name resolution','dns failure')):return 'DNS_FAILURE'
    if status in ('empty','no_results'):return 'EMPTY_RESULT'
    if status=='partial':return 'PARTIAL_RESULT'
    if status=='experimental':return 'EXPERIMENTAL_SOURCE'
    if status in ('ok','complete','completed','success'):return 'OBSERVED'
    if status in ('skipped','not_run'):return 'NOT_EXECUTED'
    if status in ('unavailable','network_error'):return 'SOURCE_UNAVAILABLE'
    return 'TOOL_ERROR'


def exact(value):
    if value is None:return None
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or len(str(value))>512:return None
        return format(amount,'f')
    except (InvalidOperation,ValueError,TypeError):return None


def diagnostics(report,transport=None):
    rows=[]
    for row in report.get('source_health',[]):
        if not isinstance(row,dict):continue
        status=str(row.get('status') or 'unavailable')
        details=str(row.get('details') or '')[:800]
        rows.append({'provider':str(row.get('source') or 'unknown')[:100],
            'status':status,'reason_code':reason(status,details),'details':details,
            'timeout_seconds':row.get('timeout_seconds'),'partial':row.get('partial',status=='partial')})
    # Gansar may append capability-health rows; count provider execution only
    # from its actual source.start events, not the number of health rows/URLs.
    transport=transport if isinstance(transport,dict) else {}
    attempted=sorted(set(transport.get('providers_started',[])))
    return {'providers_attempted':len(attempted),'provider_ids':attempted,'health':rows,
        'http_requests':transport.get('requests_used'),'http_statuses':transport.get('http_statuses',{}),
        'request_budget':transport.get('request_budget'),'budget_exhausted':bool(transport.get('budget_exhausted')),
        'provider_count_complete':transport.get('finished') is True,'engine_error':transport.get('engine_error'),
        'retry_after':transport.get('retry_after',[])}
