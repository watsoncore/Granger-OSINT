import threading
from grangerpet.research_workflows import email_research
from grangerpet.entity_router import route
from grangerpet.agent_tools import _SPECS
from grangerpet.tool_manifest import relevant_names


def test_email_workflow_queries_independent_sources_and_excludes_wrong_mentions():
    calls=[]
    def dns(name,args,**kwargs):
        calls.append((name,args));return {'status':'complete','results':[{'title':'MX','details':{'syntax_valid':True}}]}
    def public(name,query,**kwargs):
        calls.append((name,query))
        if name=='github_users':return {'status':'complete','results':[{'title':'candidate','details':{}}]}
        return {'status':'complete','results':[{'title':'contact: public@example.org','details':{}},{'title':'unrelated','details':{}}]}
    result=email_research({'email':'public@example.org'},dns_execute=dns,public_execute=public)
    assert result['status']=='complete' and len(result['results'])==3
    assert calls==[('mail_dns',{'email':'public@example.org'}),('github_users','"public@example.org" in:email'),('hn_search','"public@example.org"')]
    assert all(row['details']['mailbox_verified'] is False and row['details']['identity_match_verified'] is False for row in result['results'])
    assert result['source_attempts'][-1]['count']==1 and result['source_attempts'][-1]['returned_records']==2


def test_source_failure_is_partial_with_independent_success_and_no_registration_probe():
    def dns(*args,**kwargs):return {'status':'complete','results':[{'title':'DNS','details':{}}]}
    def public(*args,**kwargs):return {'status':'rate_limited','results':[],'error_code':'http_429'}
    result=email_research({'email':'public@example.org'},dns_execute=dns,public_execute=public)
    assert result['status']=='partial' and len(result['results'])==1
    assert [row['status'] for row in result['source_attempts']]==['complete','rate_limited','rate_limited']


def test_cancelled_and_invalid_email_never_contact_sources():
    def unavailable(*args,**kwargs):raise AssertionError('network not expected')
    stopped=threading.Event();stopped.set()
    assert email_research({'email':'public@example.org'},cancel_event=stopped,dns_execute=unavailable,public_execute=unavailable)['status']=='cancelled'
    assert email_research({'email':'bad'},dns_execute=unavailable,public_execute=unavailable)['status']=='invalid_arguments'


def test_default_routes_use_email_workflow_and_only_maigret_username_engine():
    assert route('public@example.org').tools[0]=='email_research'
    selected=relevant_names(_SPECS,'Исследуй публичные профили solvnox')
    assert 'username_maigret' in selected
    assert not {'username_blackbird','username_social_analyzer','username_snoop'}&selected
    assert 'username_blackbird' in relevant_names(_SPECS,'Проверь никнейм solvnox с Blackbird')
