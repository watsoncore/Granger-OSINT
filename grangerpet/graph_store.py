"""Atomic encrypted UI positions for an existing investigation; no new database."""
from __future__ import annotations
from copy import deepcopy
import json
import math
import re
from pathlib import Path

from .credentials import CredentialsStore
from .portable_vault import atomic_write
from .evidence_graph import ENTITY_TYPES

MAX_VIEW_BYTES = 3_000_000
ENTITY_ID = re.compile(r'ent_[a-f0-9]{24}')
RELATION_ID = re.compile(r'rel_[a-f0-9]{24}')


def _number(value, low=-10_000_000, high=10_000_000):
    if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Invalid graph coordinate')
    return value


def validate_view(value):
    if not isinstance(value,dict): raise ValueError('Graph view must be an object')
    allowed={'version','mode','positions','tree_positions','viewport','tree_viewport','selected_id',
        'selected_relation','expanded','expanded_relations','collapsed','filters','query','layout_algorithm','inspector_width','inspector_hidden'}
    if set(value)-allowed or value.get('version',1)!=1: raise ValueError('Unsupported graph view')
    result=deepcopy(value)
    result['version']=1
    if result.get('mode','overview') not in ('overview','tree','graph','evidence','geo'):raise ValueError('Invalid graph mode')
    if 'layout_algorithm'in result and result['layout_algorithm']!='semantic_cards':raise ValueError('Invalid graph algorithm')
    if 'inspector_width'in result:_number(result['inspector_width'],260,560)
    if 'inspector_hidden'in result and type(result['inspector_hidden']) is not bool:raise ValueError('Invalid graph inspector')
    for key in ('positions','tree_positions'):
        positions=result.get(key,{})
        if not isinstance(positions,dict) or len(positions)>5000:raise ValueError('Invalid graph positions')
        for identifier,position in positions.items():
            if not isinstance(identifier,str) or not ENTITY_ID.fullmatch(identifier) or not isinstance(position,dict) or set(position)-{'x','y','pinned'}:
                raise ValueError('Invalid graph position')
            _number(position.get('x'));_number(position.get('y'))
            if 'pinned' in position and type(position['pinned']) is not bool:raise ValueError('Invalid graph pin')
    for key in ('viewport','tree_viewport'):
        if key in result:
            viewport=result[key]
            if not isinstance(viewport,dict) or set(viewport)!={'x','y','scale'}:raise ValueError('Invalid graph viewport')
            _number(viewport['x']);_number(viewport['y']);_number(viewport['scale'],.001,10)
    for key,pattern in (('selected_id',ENTITY_ID),('selected_relation',RELATION_ID)):
        if key in result and (not isinstance(result[key],str) or result[key] and not pattern.fullmatch(result[key])):raise ValueError('Invalid graph selection')
    for key in ('expanded','collapsed'):
        rows=result.get(key,[])
        if not isinstance(rows,list) or len(rows)>5000 or any(not isinstance(row,str) or not ENTITY_ID.fullmatch(row) for row in rows):raise ValueError('Invalid graph branches')
    rows=result.get('expanded_relations',[])
    if not isinstance(rows,list) or len(rows)>5000 or any(not isinstance(row,str) or not RELATION_ID.fullmatch(row) for row in rows):raise ValueError('Invalid expanded relations')
    if 'query' in result and (not isinstance(result['query'],str) or len(result['query'])>200):raise ValueError('Invalid graph filter query')
    if 'filters' in result:
        filters=result['filters']
        if not isinstance(filters,dict) or set(filters)-{'types','statuses','include_background','show_sources','show_transactions'}:raise ValueError('Invalid graph filters')
        for key,options in (('types',set(ENTITY_TYPES)),('statuses',{'verified','source_reported','inferred','unverified','contradicted'})):
            if key in filters and (not isinstance(filters[key],list) or len(filters[key])>40 or any(not isinstance(item,str) or item not in options for item in filters[key])):raise ValueError('Invalid graph filters')
        for key in ('include_background','show_sources','show_transactions'):
            if key in filters and type(filters[key]) is not bool:raise ValueError('Invalid graph filter')
    return result


class GraphViewStore:
    def __init__(self,journal):self.journal=journal
    def _path(self,identifier):
        self.journal._identifier(identifier)
        return self.journal.directory/(identifier+'.graph.dpapi')
    def load(self,identifier):
        path=self._path(identifier)
        if not path.exists():return {'version':1,'mode':'overview','positions':{},'expanded':[],'collapsed':[]}
        if path.stat().st_size>MAX_VIEW_BYTES+65536:raise ValueError('Graph view exceeds storage limit')
        data=CredentialsStore._protect(path.read_bytes(),decrypt=True)
        if len(data)>MAX_VIEW_BYTES:raise ValueError('Graph view exceeds storage limit')
        return validate_view(json.loads(data.decode('utf-8')))
    def active(self):
        path=self.journal.directory/'current-search.dpapi'
        if not path.exists():return ''
        if path.stat().st_size>4096:raise ValueError('Invalid active investigation pointer')
        value=json.loads(CredentialsStore._protect(path.read_bytes(),decrypt=True).decode('utf-8'))
        if not isinstance(value,dict) or value.get('version')!=1:raise ValueError('Invalid active investigation pointer')
        return self.journal._identifier(value.get('id'))
    def select(self,identifier):
        self.journal._identifier(identifier)
        path=self.journal.directory/'current-search.dpapi'
        atomic_write(path,CredentialsStore._protect(json.dumps({'version':1,'id':identifier}).encode('utf-8')))
    def save(self,identifier,view):
        path=self._path(identifier)
        value=validate_view(view)
        encoded=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        if len(encoded)>MAX_VIEW_BYTES:raise ValueError('Graph view exceeds storage limit')
        # This is a new v1 sidecar. Never migrate or replace an unknown version
        # without preserving its original protected bytes for rollback.
        if path.exists():
            try:previous=self.load(identifier)
            except (ValueError,UnicodeError):
                previous={}
                backup=path.with_name(path.name+'.recovery-backup')
                if not backup.exists():atomic_write(backup,path.read_bytes())
                if backup.read_bytes()!=path.read_bytes():raise ValueError('Graph recovery backup verification failed')
            if value.get('layout_algorithm')=='semantic_cards' and previous.get('layout_algorithm')!='semantic_cards':
                backup=path.with_name(path.name+'.layout-v1-backup')
                if not backup.exists():atomic_write(backup,path.read_bytes())
        atomic_write(path,CredentialsStore._protect(encoded))
        return value
