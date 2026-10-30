"""Existing journal/runner state shared by manual search and investigation views."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json

from .agent_evidence import utc_now, redact
from .credentials import CredentialError
from .investigation import InvestigationEvidence, new_investigation
from .graph_store import GraphViewStore
from .tool_contracts import sanitize_outcome


def _json(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class InvestigationWorkspace:
    def __init__(self,journal):
        self.journal=journal
        self.views=GraphViewStore(journal)
        self.manual=None
        self.active_id=''
        try:
            identifier=self.views.active()
            if identifier:
                snapshot=self.load(identifier)
                self.active_id=identifier
                if snapshot.get('mode')=='manual':self.manual=snapshot
        except (OSError,ValueError,CredentialError):
            # The original protected pointer/journal is not rewritten.
            self.recovery_error='saved_graph_unavailable'

    def load(self,identifier,live=None):
        self.journal._identifier(identifier)
        if isinstance(live,dict) and live.get('id')==identifier:
            snapshot=deepcopy(live)
            if snapshot.get('goal'):
                return snapshot
        else:snapshot=None
        try:
            checkpoint=self.journal.load_checkpoint(identifier)
            value={**deepcopy(checkpoint['record']), 'evidence':deepcopy(checkpoint.get('evidence',[])),
                'executions':deepcopy(checkpoint.get('executions',[]))}
            if value.get('status')=='running':value.update(status='interrupted',stop_reason='interrupted')
        except (OSError,ValueError):value=self.journal.load(identifier)
        if snapshot is not None:
            value.update(snapshot)
            if not value.get('goal'):
                try:value['goal']=self.journal.load_checkpoint(identifier)['record'].get('goal','')
                except (OSError,ValueError):value.setdefault('validation_warnings',[]).append({'code':'original_goal_unavailable'})
        return value

    def select(self,identifier):
        self.journal._identifier(identifier)
        self.views.select(identifier)
        self.active_id=identifier

    def manual_result(self,query,outcome,arguments,registry,conversation_id):
        secrets=tuple(getattr(registry,'_redactions',()))
        safe=sanitize_outcome(outcome,secrets)
        query=redact(query,secrets)
        arguments=redact(arguments,secrets)
        if self.manual and self.manual.get('manual_query')==query:
            old=self.journal.load_checkpoint(self.manual['id'])
            record=deepcopy(old['record'])
            state={key:deepcopy(value) for key,value in old.items() if key not in ('record','version','id','evidence','executions')}
            store=InvestigationEvidence();store.restore(old.get('evidence',[]),old.get('executions',[]))
        else:
            record,state=new_investigation('Ручная проверка публичных сведений: '+query,conversation_id)
            store=InvestigationEvidence()
            state['messages']=[{'role':'system','content':'Сохранённые реальные результаты ручного инструмента Granger-OSINT.'},
                {'role':'user','content':record['goal']}]
            state['protocol_archive']=deepcopy(state['messages'])
        name=safe['tool'];now=utc_now()
        record.update(mode='manual',manual_query=query,status='paused',stop_reason='manual_result',resumable=True,
            updated_at=now,finished_at=now,tool_calls=record.get('tool_calls',0)+1,
            checkpoint_revision=record.get('checkpoint_revision',0)+1)
        record['calls'].append({'tool':name,'arguments':deepcopy(arguments),'origin':'manual','tool_call_id':safe.get('invocation_id','')})
        store.add(safe)
        fingerprint=hashlib.sha256((name+'\0'+_json(registry.canonical_arguments(name,arguments))).encode()).hexdigest()
        state['call_cache'][fingerprint]={'outcome':safe,'resume_count':record.get('resume_count',0)}
        state['tried_queries'].append({'tool':name,'arguments':deepcopy(arguments),'status':safe['status'],'obtained_at':now})
        state['completed_steps'].append({'step':record.get('steps',0),'calls':[{'tool':name,'status':safe['status'],
            'evidence_ids':[row['evidence_id'] for row in store.records()]}]})
        state['registry_state']=registry.checkpoint_state()
        checkpoint={**state,'version':1,'id':record['id'],'record':record,'evidence':store.records(),'executions':store.executions()}
        self.journal.save_checkpoint(checkpoint)
        snapshot={**record,'evidence':store.records(),'executions':store.executions()}
        self.journal.save(snapshot)
        self.select(record['id'])
        self.manual=snapshot
        return snapshot
