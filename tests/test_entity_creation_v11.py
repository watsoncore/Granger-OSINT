from grangerpet.research_canvas import new_document, apply, CanvasStore
from grangerpet.agent_journal import InvestigationJournal


def test_manual_creation_reports_identity_and_reveals_object_after_reopen(tmp_path):
    doc=new_document('Создание из аналитической проекции')
    doc['view']['ui']['graph_mode']='wallet'
    result={}
    doc=apply(doc,'node',{'type':'phone','value':'+12025550123','label':'Публичный контакт'},result=result)
    assert result['created'] is True
    identifier=result['entity_id']
    assert doc['view']['ui']['graph_mode']=='manual'
    doc=apply(doc,'group',{'ids':[identifier],'label':'Скрытая группа'})
    parent=next(node['id'] for node in doc['entities'] if node['type']=='entity_group')
    doc['view']['hidden']=[identifier,parent];doc['view']['removed']=[identifier];doc['view']['collapsed']=[parent]
    repeated={}
    doc=apply(doc,'node',{'type':'phone','value':'+12025550123','label':'Контакт'},result=repeated)
    assert repeated=={'entity_id':identifier,'created':False}
    assert identifier not in doc['view']['hidden']+doc['view']['removed']
    assert parent not in doc['view']['hidden']+doc['view']['collapsed']
    store=CanvasStore(InvestigationJournal(tmp_path/'investigations'))
    saved=store.save(doc,0);reopened=store.load(saved['id'])
    assert reopened['view']['ui']['graph_mode']=='manual'
    assert any(node['id']==identifier for node in reopened['entities'])
