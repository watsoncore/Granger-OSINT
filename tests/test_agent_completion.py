"""MockTransport protocol tests for structured turns and real SSE parsing."""
import asyncio
import json
import threading

import httpx
import pytest

from grangerpet.ai import DeepSeekClient, AIError

MODEL='deepseek-v4-flash'
KEY='EXPLICIT-PRIVATE-TRANSPORT-FIXTURE'
TOOLS=[{'type':'function','function':{'name':'web_search','parameters':{'type':'object'}}}]


class Bytes(httpx.AsyncByteStream):
    def __init__(self,chunks):self.chunks=chunks;self.closed=False
    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(.005)
            yield chunk
    async def aclose(self):self.closed=True


def client(reply):
    return DeepSeekClient(KEY,client_factory=lambda **options:httpx.AsyncClient(transport=httpx.MockTransport(reply),**options))


def frame(content=None,finish=None,**delta):
    return ('data: '+json.dumps({'choices':[{'delta':{'content':content,**delta},'finish_reason':finish}]},ensure_ascii=False)+'\n\n').encode('utf-8')


def test_complete_turn_preserves_tool_protocol_and_excludes_transport_secrets():
    calls=[]
    def response(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':None,'reasoning_content':'Transient reasoning',
            'tool_calls':[{'id':'call_x','type':'function','function':{'name':'web_search','arguments':'{"query":"fixture"}'}}]}}]})
    result=client(response).complete_turn(MODEL,[{'role':'user','content':'Найди fixture'}],tools=TOOLS)
    assert result['message']['tool_calls'][0]['id']=='call_x'
    assert result['message']['reasoning_content']=='Transient reasoning'
    assert 'reasoning_content' not in result['metadata'] and KEY not in json.dumps(calls)


def test_complete_turn_sends_results_for_every_parallel_call():
    seen=[]
    def response(request):
        seen.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'Итог'}}]})
    toolcalls=[{'id':name,'type':'function','function':{'name':'web_search','arguments':'{}'}} for name in ('one','two')]
    history=[{'role':'user','content':'Найди'},{'role':'assistant','content':None,'tool_calls':toolcalls,'reasoning_content':'Keep for protocol'},
             {'role':'tool','tool_call_id':'one','content':'{"results":[]}'},{'role':'tool','tool_call_id':'two','content':'{"results":[]}'}]
    assert client(response).complete_turn(MODEL,history,tools=TOOLS)['message']['content']=='Итог'
    assert seen[0]['messages'][1]['reasoning_content']=='Keep for protocol'
    assert [m['tool_call_id'] for m in seen[0]['messages'] if m['role']=='tool']==['one','two']


def test_missing_parallel_result_is_rejected_before_http():
    requests=[];c=client(lambda r:requests.append(r))
    with pytest.raises(AIError):c.complete_turn(MODEL,[{'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'web_search','arguments':'{}'}}]}],tools=TOOLS)
    assert not requests


@pytest.mark.parametrize('arguments',[json.dumps({'query':KEY}),'{"query":"'+''.join('\\u%04x'%ord(c) for c in KEY)+'"}'])
def test_key_reflection_in_arguments_never_reaches_dispatcher(arguments):
    def response(request):return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[
        {'id':'x','type':'function','function':{'name':'web_search','arguments':arguments}}]}}]})
    with pytest.raises(AIError):client(response).complete_turn(MODEL,[{'role':'user','content':'Найди'}],tools=TOOLS)


def test_sse_utf8_content_is_cumulative_and_never_renders_reasoning():
    stream=Bytes([frame('Привет, '),frame(None,reasoning_content='PRIVATE-REASONING'),frame('Гермиона!'),frame('',finish='stop'),b'data: [DONE]\n\n'])
    seen=[];c=client(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream))
    assert c.stream_chat(MODEL,[{'role':'user','text':'Привет'}],on_text=seen.append)=='Привет, Гермиона!'
    assert seen[-1]=='Привет, Гермиона!' and stream.closed and 'PRIVATE-REASONING' not in ''.join(seen)


def test_sse_split_secret_never_appears_in_callbacks():
    pieces=[frame('x'*100+KEY[:10]),frame(KEY[10:]+'. '+'y'*100),frame('',finish='stop'),b'data: [DONE]\n\n']
    seen=[];c=client(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(pieces)))
    result=c.stream_chat(MODEL,[{'role':'user','text':'Привет'}],on_text=seen.append)
    assert KEY not in result and all(KEY not in value and KEY[:10] not in value for value in seen)


@pytest.mark.parametrize('pieces',[[frame('partial')],[b'data: not-json\n\n'],[frame('',finish='stop'),b'data: [DONE]\n\n']])
def test_invalid_or_empty_sse_is_never_success(pieces):
    c=client(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(pieces)))
    with pytest.raises(AIError):c.stream_chat(MODEL,[{'role':'user','text':'Тест'}],on_text=lambda _:None)


def test_stream_cancellation_closes_transport():
    cancel=threading.Event();stream=Bytes([frame('a'*150) for _ in range(100)])
    c=client(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream))
    threading.Timer(.04,cancel.set).start()
    with pytest.raises(AIError) as error:c.stream_chat(MODEL,[{'role':'user','text':'Тест'}],on_text=lambda _:None,cancel_event=cancel)
    assert error.value.code=='cancelled' and stream.closed
