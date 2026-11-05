"""Small ordered view updates over the existing Qt state channel."""


def canvas_delta(previous,current):
    if not isinstance(previous,dict) or not isinstance(current,dict):return None
    old=previous.get('document');new=current.get('document')
    if not old or not new or old['id']!=new['id']:return None
    state={k:v for k,v in current.items() if k!='document' and (k not in previous or previous[k]!=v)}
    document={k:v for k,v in new.items() if k!='view' and (k not in old or old[k]!=v)}
    view={k:v for k,v in new['view'].items() if k!='positions' and (k not in old['view'] or old['view'][k]!=v)}
    before=old['view']['positions'];after=new['view']['positions']
    positions={k:v for k,v in after.items() if k not in before or before[k]!=v}
    return {'canvas_id':new['id'],'base_revision':old['revision'],
        'state':state,'state_removed':[k for k in previous if k not in current],
        'document':document,'document_removed':[k for k in old if k not in new],
        'view':view,'view_removed':[k for k in old['view'] if k not in new['view']],
        'positions':positions,'positions_removed':[k for k in before if k not in after]}
