from copy import deepcopy
import json
from grangerpet.canvas_state_patch import canvas_delta
from grangerpet.research_canvas import new_document,add_node


def test_pan_delta_does_not_serialize_nodes_evidence_or_unchanged_positions():
    doc=new_document();add_node(doc,{'type':'analyst_note','label':'A'})
    before={'document':doc,'state':'ready','types':[],'choices':[]}
    after=deepcopy(before);after['document']['revision']=1;after['document']['view']['viewport']['x']=500
    delta=canvas_delta(before,after)
    assert delta['document']=={'revision':1} and delta['view']=={'viewport':after['document']['view']['viewport']}
    assert delta['positions']=={} and 'entities' not in json.dumps(delta) and len(json.dumps(delta))<500


def test_drag_updates_only_changed_position_and_cannot_patch_another_canvas():
    doc=new_document();a=add_node(doc,{'type':'analyst_note','label':'A'});add_node(doc,{'type':'analyst_note','label':'B'})
    before={'document':doc};after=deepcopy(before);after['document']['view']['positions'][a]['x']+=60
    delta=canvas_delta(before,after);assert list(delta['positions'])==[a]
    after['document']['id']='a'*32
    assert canvas_delta(before,after) is None
