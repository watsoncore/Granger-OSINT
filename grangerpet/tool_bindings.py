"""Bounded model bindings; discovery does not grant execution permissions."""
import re

MAX_BINDINGS=32
FIND_SCHEMA={'type':'object','properties':{
    'query':{'type':'string','maxLength':300},
    'names':{'type':'array','items':{'type':'string','maxLength':64},'maxItems':12},
    'offset':{'type':'integer','minimum':0,'maximum':1000}},'required':[],'additionalProperties':False}


def bind(tools,task,discovered=()):
    from .entity_router import route_goal
    priority=['capabilities_find',*reversed(list(discovered))]
    for target in route_goal(task or ''):priority.extend(target.tools)
    priority.extend(('evidence_get','evidence_graph','web_read','web_search','web_archive'))
    order={name:index for index,name in reversed(list(enumerate(priority)))}
    ranked=sorted(enumerate(tools),key=lambda pair:(order.get(pair[1]['function']['name'],1000+pair[0]),pair[0]))
    return [tool for _,tool in ranked[:MAX_BINDINGS]]


def matches(specs,query,names):
    """Rank real identifiers/categories/descriptions, without model assertions."""
    from .tool_manifest import manifest
    tokens=set(re.findall(r'[\w]+',query.casefold()))
    ranked=[]
    for index,spec in enumerate(specs):
        meta=manifest(spec)
        haystack=(spec.name+' '+spec.kind+' '+meta.category+' '+spec.description).casefold()
        score=(100 if spec.name in names else 0)+sum(1 for token in tokens if token in haystack)
        if not tokens and not names or score:ranked.append((-score,index,spec))
    return [spec for _,_,spec in sorted(ranked)]
