"""Model working context is a view; original user and source data survives."""
from copy import deepcopy
import json

from grangerpet.agent import AgentRunner
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.context import conversation_context, relevant_excerpt


def test_old_user_requirements_and_relevant_facts_survive_beyond_twenty_four_turns():
    history=[{'role':'user','text':'Не используй платные сервисы. Сохрани исходные ссылки.'},
             {'role':'model','text':'Принято.'},
             {'role':'user','text':'Код проекта Aurora — ORIGINAL-31.'},
             {'role':'model','text':'Это заявление пользователя; внешнее подтверждение отсутствует.'}]
    history.extend({'role':'user' if index%2==0 else'model','text':'Постороннее обсуждение '+str(index)}for index in range(70))
    history.append({'role':'user','text':'Вернись к Aurora и проверь исходный код.'})
    original=deepcopy(history)
    result=conversation_context(history,'Aurora исходный код')
    text=' '.join(row['text']for row in result)
    assert 'Не используй платные сервисы' in text and 'ORIGINAL-31' in text
    assert history==original and len(result)<=32


def test_working_context_is_bounded_and_keeps_full_current_request():
    history=[{'role':'user' if index%2==0 else'model','text':'Aurora '+str(index)+' filler '*1500}for index in range(100)]
    current='Текущий полный запрос. '+'x'*11000
    history.append({'role':'user','text':current})
    result=conversation_context(history,'Aurora')
    assert result[-1]['text']==current
    assert sum(len(row['text'])for row in result)<=18500  # Includes explicit archive-view labels.
    assert len(history)==101


def test_relevant_excerpt_finds_tail_facts_and_does_not_assert_unverified_identity():
    text='Historical source. '+('Unrelated text. '*700)+' Aurora verification marker TAIL-77; identity remains unverified.'
    excerpt=relevant_excerpt(text,'Aurora verification marker',1800)
    assert len(excerpt)<=1800 and 'TAIL-77' in excerpt and 'unverified' in excerpt


def test_unanswered_cancelled_questions_are_not_replayed_but_user_constraints_are_retained():
    rows=[{'role':'user','text':'Первый отменённый вопрос'},
          {'role':'user','text':'Не передавай персональные данные внешним сервисам.'},
          {'role':'user','text':'Новый вопрос'}]
    result=conversation_context(rows)
    assert all(row['text']!='Первый отменённый вопрос'for row in result)
    assert any('Не передавай' in row['text']for row in result)


def page():
    url='https://example.org/archive'
    return normalize_evidence({'id':url,'title':'Aurora','type':'web','platform':'Fixture','url':url,'status':'verified',
        'description':'Public source excerpt.','details':{'reading_method':'direct_http','content_text':'x'*7000+'TAIL-77 '+'z'*3000,
            'content_excerpt':'x'*2000},'sources':['web_read']},'web_read',url)


def test_evidence_get_can_retrieve_exact_tail_without_network_or_changing_evidence_id():
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    record=page()
    registry.evidence.add({'tool':'web_read','query':record['url'],'status':'complete','results':[record]})
    result=registry.execute('evidence_get',{'evidence_id':record['evidence_id'],'offset':6900,'length':500})
    runner=AgentRunner(object(),registry)
    runner._record={'goal':'Aurora'}
    payload=json.loads(runner._compact(result))
    row=payload['results'][0]
    assert 'TAIL-77' in row['page_content']['content_excerpt']
    assert row['page_content']['content_range']==[6900,7400]
    assert row['evidence_id']==record['evidence_id'] and len(result['results'][0]['details']['content_text'])>10000
    assert registry.execute('evidence_get',{'evidence_id':record['evidence_id'],'offset':-1})['status']=='invalid_arguments'
    assert registry.execute('evidence_get',{'evidence_id':record['evidence_id'],'length':True})['status']=='invalid_arguments'


def test_identical_content_uses_evidence_reference_but_changed_primary_data_is_not_deduplicated():
    runner=AgentRunner(object(),object());runner._record={'goal':'Aurora'}
    original=page()
    first=json.loads(runner._compact({'tool':'web_read','results':[original]}))['results'][0]
    repeated=json.loads(runner._compact({'tool':'web_read','results':[original]}))['results'][0]
    assert 'page_content'in first and repeated['same_content_as']==original['evidence_id']
    changed=deepcopy(original);changed['details']['content_text']+=' Changed observation.'
    assert 'page_content'in json.loads(runner._compact({'tool':'web_read','results':[changed]}))['results'][0]
    assert original['details']['content_text']==page()['details']['content_text']
