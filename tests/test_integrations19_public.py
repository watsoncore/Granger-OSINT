"""Explicit local fixtures; all external HTTP is mocked, no real people/keys."""
import json
import threading
import time

import httpx
import pytest

from grangerpet.integrations19 import public_tools as tools
from grangerpet import agent_browser


@pytest.fixture(autouse=True)
def clean_state():
    tools._CACHE.clear();tools._BACKOFF.clear()
    with agent_browser._DOMAIN_LOCK:agent_browser._DOMAIN_NEXT.clear()
    yield
    tools._CACHE.clear();tools._BACKOFF.clear()


async def resolver(*args):return ['93.184.216.34']


def client(handler):
    def factory(**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        return httpx.AsyncClient(**kwargs)
    return factory


def execute(name,args,handler):
    return tools.execute(name,args,deadline=time.monotonic()+5,client_factory=client(handler),resolver=resolver)


@pytest.mark.parametrize('tool,args',[
    ('mail_dns',{'email':'bad'}),('mail_dns',{'email':False}),('mail_dns',{'email':'a@example.org','token':'not-allowed'}),
    ('historical_contacts',{'domain':'localhost'}),('historical_contacts',{'domain':'127.0.0.1'}),
    ('historical_contacts',{'domain':'example.org/path'}),('historical_contacts',{'domain':'example.org','max_snapshots':True}),
    ('x_post',{'url':'https://x.com/jack/status/20?access_token=abc'}),('x_post',{'url':'https://not-x.example.org/jack/status/20'}),
    ('x_post',{'url':'https://x.com/jack/status/0'}),('arctic_posts',{'query':'unbounded'}),
    ('x_profile',{'username':'https://x.com/Fixture'}),('x_profile',{'username':'../Fixture'}),
    ('arctic_posts',{'author':'ok','limit':True}),('arctic_comments',{'subreddit':'ok','limit':21}),
    ('arctic_posts',{'author':'ok','after':'2025-02-30'}),('arctic_posts',{'author':'ok','after':'2025-02-10','before':'2025-02-01'}),
    ('arctic_comments',{'author':'../bad'}),('unknown',{}),
])
def test_untrusted_input_never_contacts_network(tool,args):
    def forbidden(*args):raise AssertionError('Validation must happen before HTTP')
    assert execute(tool,args,forbidden)['status']=='invalid_arguments'


@pytest.mark.parametrize('status,state',[(401,'auth_required'),(403,'blocked'),(429,'rate_limited'),(503,'rate_limited'),(400,'unavailable')])
def test_http_error_typed_and_no_fabricated_finding(status,state):
    count=[]
    def respond(request):count.append(request);return httpx.Response(status,headers={'Retry-After':'60'},json={'error':'fixture'})
    result=execute('x_post',{'url':'https://x.com/fixture/status/20'},respond)
    assert result['status']==state and not result['results']
    assert len(count)<3  # Common transport makes at most one 503 retry.
    if status in (401,403,429,503):
        again=execute('x_post',{'url':'https://x.com/fixture/status/21'},lambda r:pytest.fail('Backoff ignored'))
        assert again['status']==state


def test_private_dns_and_cross_origin_redirect_fail_closed():
    async def private(*args):return ['127.0.0.1']
    result=tools.execute('x_post',{'url':'https://x.com/fixture/status/20'},resolver=private,client_factory=client(lambda r:pytest.fail('Private target reached')))
    assert result['status']=='blocked'
    def redirect(request):
        if request.url.host=='api.fxtwitter.com':return httpx.Response(302,headers={'Location':'https://example.org/'})
        return httpx.Response(200,json={'code':200})
    result=execute('x_post',{'url':'https://x.com/fixture/status/20'},redirect)
    assert result['status']=='blocked' and not result['results']


@pytest.mark.parametrize('body',[b'not json',b'[]',b'{"code":200,"tweet":{"id":"20","text":false}}',b'<html>verify you are human</html>'])
def test_bad_provider_body_is_not_success(body):
    result=execute('x_post',{'url':'https://x.com/fixture/status/20'},lambda r:httpx.Response(200,content=body,headers={'Content-Type':'application/json'}))
    assert result['status'] not in ('complete','empty') and not result['results']


def test_dns_truthful_null_mx_and_policies_no_mailbox_claim(monkeypatch):
    requests=[]
    def respond(request):
        requests.append(request)
        kind=request.url.params['type'];name=request.url.params['name']
        records=[{'name':name,'type':15,'TTL':300,'data':'0 .'}] if kind=='MX' else [{'name':name,'type':16,'TTL':300,'data':'"v=DMARC1; p=reject"' if name.startswith('_dmarc.') else '"v=spf1 -all"'}]
        return httpx.Response(200,json={'Status':0,'Answer':records})
    monkeypatch.setattr(tools,'fetch_public',_without_rate(tools.fetch_public))
    result=execute('mail_dns',{'email':'Пример@example.org'},respond)
    # Existing email normalizer deliberately requires an ASCII local part.
    if result['status']=='invalid_arguments':result=execute('mail_dns',{'email':'fixture@example.org'},respond)
    assert result['status']=='complete' and len(requests)==3
    details=result['results'][0]['details']
    assert details['spf']==['v=spf1 -all'] and details['dmarc']==['v=DMARC1; p=reject']
    assert details['mailbox_existence_checked'] is False and details['messages_sent'] is False
    assert all(r.method=='GET' and r.url.host=='dns.google' and 'Authorization' not in r.headers for r in requests)


def _without_rate(original):
    async def call(*args,**kwargs):kwargs['rate_interval']=0;return await original(*args,**kwargs)
    return call


def arctic_item(**updates):
    return {'id':'abcd','author':'Fixture','subreddit':'Fixture','created_utc':1700000000,'title':'Русский заголовок',
        'selftext':'Проверяемый текст источника','body':'Комментарий','url':'https://example.org/','score':1,**updates}


@pytest.mark.parametrize('tool,text_field,query_param',[('arctic_posts','selftext','query'),('arctic_comments','body','body')])
def test_arctic_schema_dates_utf8_and_bounded_request(tool,text_field,query_param):
    seen=[]
    def respond(request):seen.append(request);return httpx.Response(200,json={'data':[arctic_item()]})
    result=execute(tool,{'author':'Fixture','query':'текст','after':'2020-01-01','before':'2025-01-01','limit':2},respond)
    assert result['status']=='complete' and len(result['results'])==1
    assert seen[0].url.params[query_param]=='текст' and seen[0].url.params['limit']=='2'
    assert 'permalink' not in seen[0].url.params['fields']
    details=result['results'][0]['details']
    assert details['historical_archive'] is True and details['published_at'].endswith('+00:00')
    assert details['text']==arctic_item()[text_field]


@pytest.mark.parametrize('updates',[{'created_utc':float('inf')},{'created_utc':-1},{'created_utc':1e60},{'title':[]},{'score':{}},{'id':'../bad'}])
def test_arctic_malformed_records_rejected(monkeypatch,updates):
    async def fake(*args,**kwargs):return {'data':[arctic_item(**updates)]}
    monkeypatch.setattr(tools,'_json',fake)
    result=tools.execute('arctic_posts',{'subreddit':'Fixture'})
    assert result['status']=='unavailable' and not result['results']


def test_single_post_fields_cache_and_no_media_download():
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'code':200,'tweet':{'id':'20','text':'Русский текст','author':{'screen_name':'Fixture','name':'Fixture'},
            'likes':3,'replies':1,'media':{'all':[{'type':'photo','url':'https://example.org/pic.jpg'},{'url':'http://127.0.0.1/a'}]}}})
    first=execute('x_post',{'url':'https://twitter.com/Fixture/status/20'},respond)
    assert first['status']=='complete' and len(requests)==1
    details=first['results'][0]['details']
    assert details['text']=='Русский текст' and len(details['media'])==1 and details['media'][0]['downloaded'] is False
    second=execute('x_post',{'url':'https://x.com/Fixture/status/20'},lambda r:pytest.fail('Cache should avoid new request'))
    assert second['obtained_at']==first['obtained_at'] and 'Кэш' in second['limitations'][-1]
    second['results'][0]['details']['text']='mutated'
    third=execute('x_post',{'url':'https://x.com/Fixture/status/20'},respond)
    assert third['results'][0]['details']['text']=='Русский текст'


def test_public_profile_is_metadata_not_account_ownership():
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'code':200,'user':{'id':'123','screen_name':'Fixture','name':'Имя',
            'description':'Публичное bio','location':'Заявленное место','joined':'2020','followers':2,'tweets':3,
            'avatar_url':'https://example.org/avatar.jpg'}})
    result=execute('x_profile',{'username':'@Fixture'},respond)
    assert result['status']=='complete' and len(requests)==1
    details=result['results'][0]['details']
    assert details['media_downloaded'] is False and details['description']=='Публичное bio'
    assert 'не устанавливает личность' in details['verification']


@pytest.mark.parametrize('user',[{'screen_name':'Different','id':'123'},{'screen_name':'Fixture','id':'../123'},
    {'screen_name':'Fixture','id':'123','followers':False}])
def test_profile_invalid_schema_fails_closed(user):
    result=execute('x_profile',{'username':'Fixture'},lambda r:httpx.Response(200,json={'code':200,'user':user}))
    assert result['status']=='unavailable' and not result['results']


def test_historical_contacts_bind_actual_snapshot_and_timestamp(monkeypatch):
    seen=[]
    def respond(request):
        seen.append(request)
        if request.url.path.startswith('/cdx/'):
            return httpx.Response(200,json=[['timestamp','original'],['20100102030405','https://example.org/contact'],['20100102030406','http://169.254.169.254/']])
        return httpx.Response(200,text='<p>Old [at] example [dot] org</p><a href="mailto:Other@example.org">mail</a><p>+1 202-555-0123</p><script>secret@example.org</script>',headers={'Content-Type':'text/html'})
    monkeypatch.setattr(tools,'fetch_public',_without_rate(tools.fetch_public))
    result=execute('historical_contacts',{'domain':'example.org','max_snapshots':1},respond)
    assert result['status']=='complete' and len(seen)==2
    details=result['results'][0]['details']
    assert details['historical_only'] and details['snapshots_fetched']==1 and details['snapshots_considered']==1
    values={c['value'] for c in details['contacts']}
    assert {'old@example.org','other@example.org','+12025550123'}<=values and 'secret@example.org' not in values
    assert all(c['timestamp']=='20100102030405' and '/20100102030405id_/' in c['snapshot_url'] for c in details['contacts'])


def test_archive_index_only_is_partial_with_no_contact_fabrication(monkeypatch):
    async def fake_json(*args,**kwargs):return [['timestamp','original'],['20100102030405','https://example.org/']]
    async def unavailable(*args,**kwargs):raise tools._FetchError('fixture_timeout',status='timeout')
    monkeypatch.setattr(tools,'_json',fake_json);monkeypatch.setattr(tools,'_request',unavailable)
    result=tools.execute('historical_contacts',{'domain':'example.org','max_snapshots':1})
    assert result['status']=='partial'
    assert result['results'][0]['details']['contacts']==[] and result['results'][0]['details']['snapshots_fetched']==0


def test_cancel_and_expired_deadline_do_no_network():
    event=threading.Event();event.set()
    for kwargs,state in [({'cancel_event':event},'cancelled'),({'deadline':time.monotonic()-1},'timeout')]:
        result=tools.execute('x_post',{'url':'https://x.com/Fixture/status/20'},client_factory=client(lambda r:pytest.fail('Cancelled request executed')),resolver=resolver,**kwargs)
        assert result['status']==state and not result['results']
