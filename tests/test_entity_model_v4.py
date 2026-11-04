from copy import deepcopy
import json
import pytest
from grangerpet.research_canvas import new_document,add_node,apply,validate,CanvasStore
from grangerpet.agent_journal import InvestigationJournal
from grangerpet.canvas_capabilities import capabilities,execution_payload
from grangerpet.crypto_targets import resolve_crypto_target
TON=resolve_crypto_target('UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd','ton')['canonical_address']
@pytest.mark.parametrize('kind,value,canonical',[
 ('nickname','solvnox','username'),('username','another_name','username'),
 ('public_profile','https://github.com/solvnox','public_profile'),('email','name@example.org','email'),
 ('phone','+14155552671','phone'),('ip','66.249.67.41','infrastructure_asset'),('domain','example.org','domain'),
 ('crypto_address',TON,'blockchain_address'),('transaction','manual-tx','transaction'),
 ('organization','Example Research','organization'),('image','local illustration','image'),
 ('location','43.2,76.9','coordinate'),('custom_entity','private label','custom_entity')])
def test_explicit_entity_type_value_label_survive_encrypted_reopen_and_json_import(tmp_path,kind,value,canonical):
 doc=new_document();node_id=add_node(doc,{'type':kind,'label':'Моя подпись','value':value,'chain':'ton'})
 node=doc['entities'][0];assert node['type']==canonical and node['label']=='Моя подпись'
 assert node['attributes']['original_identifier']==value
 assert node['attributes']['value']!=node['label']
 doc=apply(doc,'annotate',{'entity_id':node_id,'annotation':{'label':'Новая подпись','markdown':'Ёжик'}})
 store=CanvasStore(InvestigationJournal(tmp_path/'journal'));saved=store.save(doc,0);reopened=store.load(saved['id'])
 imported=validate(json.loads(json.dumps(reopened,ensure_ascii=False)))
 assert imported['entities']==doc['entities'] and imported['annotations']==doc['annotations']
 assert imported['entities'][0]['type']==canonical

def test_discovery_and_execution_share_typed_target_and_reject_stale_tool():
 doc=new_document();uid=add_node(doc,{'type':'username','label':'Display name','value':'solvnox'})
 node=doc['entities'][0];items={r['id']:r for r in capabilities(node)['tools']}
 for name in ('username_maigret','username_blackbird','username_snoop','username_social_analyzer'):
  assert items[name]['compatible'] and items[name]['arguments']['username']=='solvnox'
 assert not items['network_rdap']['compatible']
 assert execution_payload(node,{'tool':'username_maigret','query':'stale','arguments':{'mode':'full'}})['arguments']['username']=='solvnox'
 with pytest.raises(ValueError):execution_payload(node,{'tool':'network_rdap','query':'66.249.67.41'})
 with pytest.raises(ValueError):execution_payload(node,{'tool':'username_maigret','arguments':{'username':'stale'}})

def test_runtime_and_invalid_target_have_distinct_reasons():
 node={'type':'username','attributes':{'value':'wrong value'}}
 assert next(r for r in capabilities(node)['tools'] if r['id']=='username_maigret')['status']=='invalid_target'
 node['attributes']['value']='solvnox'
 item=next(r for r in capabilities(node,availability=[{'id':'username_maigret','available':False,'reason':'runtime absent'}])['tools'] if r['id']=='username_maigret')
 assert item['compatible'] and item['status']=='runtime_unavailable' and item['reason']=='runtime absent'

def test_location_matching_binds_both_coordinates_and_distinguishes_geocoding():
 doc=new_document();add_node(doc,{'type':'location','label':'Точка','value':'43.2,76.9'})
 node=doc['entities'][0];tools={row['id']:row for row in capabilities(node)['tools']}
 assert tools['map_overpass']['arguments']=={'coordinates':'43.2,76.9'}
 assert tools['map_wikimedia']['compatible'] and not tools['map_geocode']['compatible']
 assert tools['map_panoramax']['arguments']=={'latitude':43.2,'longitude':76.9}
 assert execution_payload(node,{'tool':'map_panoramax'})['arguments']=={'latitude':43.2,'longitude':76.9}
 with pytest.raises(ValueError):execution_payload(node,{'tool':'map_panoramax','arguments':{'latitude':43.2,'longitude':-1}})
