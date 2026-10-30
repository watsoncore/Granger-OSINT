"""Encrypted scoped Gansar DTOs; no original vendor DB or plaintext cache."""
from pathlib import Path
import hashlib
import json
import re
import uuid

from .config import data_directory
from .credentials import CredentialsStore,protected_path
from .portable_vault import atomic_write

MAX_REPORT_BYTES=16_000_000


def merge_reports(previous,current,operation):
    """Retain complementary observations; this never asserts current ownership."""
    result=dict(previous or {})
    for key,value in current.items():
        old=result.get(key)
        if isinstance(value,list) and isinstance(old,list):
            merged={}
            for index,item in enumerate(old+value):
                if isinstance(item,dict):
                    item={**item}
                    when=(previous if index<len(old) else current).get('_observed_at')
                    if 'collected_at' not in item and when:item['collected_at']=when
                    identity=next(((field,str(item[field])) for field in ('event_id','asset_id','claim_id','tx_hash') if item.get(field)),None)
                    if key=='balances':identity=(item.get('chain'),item.get('address'),item.get('asset'),item.get('source'))
                    elif key=='tokens':identity=(item.get('chain'),item.get('address'),item.get('contract'),item.get('symbol'),item.get('source'))
                    elif key=='transactions':identity=(item.get('chain'),item.get('event_id') or item.get('tx_hash'),item.get('from_address'),item.get('to_address'),item.get('asset'),item.get('source'))
                    elif key=='source_health':identity=item.get('source')
                    identity=repr(identity) if identity else json.dumps({k:v for k,v in item.items() if k!='collected_at'},sort_keys=True,default=str)
                else:identity=json.dumps(item,sort_keys=True,default=str)
                merged[identity]=item
            result[key]=list(merged.values())
        elif isinstance(value,dict) and isinstance(old,dict):result[key]={**old,**value}
        elif value not in (None,'',[],{}):result[key]=value
    result['_operations']=sorted(set(previous.get('_operations',[]) if previous else [])|{operation})
    return result


def target_key(address,chain='auto'):
    from .validators.ton_address import parse_ton_address
    ton=parse_ton_address(address)
    value=ton['raw'] if ton else address.lower() if re.fullmatch(r'0x[a-fA-F0-9]{40}',address) else address
    return hashlib.sha256((chain+'\0'+value).encode('utf-8')).hexdigest()


class BlockchainStore:
    def __init__(self,directory=None):self.directory=Path(directory) if directory else data_directory()/'blockchain'
    def _path(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'bc_[a-f0-9]{32}',identifier):raise ValueError('Invalid blockchain dataset ID')
        return protected_path(self.directory/(identifier+'.dpapi'))
    def save(self,report,*,secrets=(),identifier=None):
        if not isinstance(report,dict) or not isinstance(report.get('target_address'),str):raise ValueError('Invalid blockchain dossier')
        raw=json.dumps({'version':1,'report':report},ensure_ascii=False,separators=(',',':'),allow_nan=False)
        for secret in secrets:
            if secret:raw=raw.replace(secret,'[скрытый ключ]')
        data=raw.encode('utf-8')
        if len(data)>MAX_REPORT_BYTES:raise ValueError('Blockchain dossier exceeds protected storage budget')
        identifier=identifier or 'bc_'+uuid.uuid4().hex
        atomic_write(self._path(identifier),CredentialsStore._protect(data))
        return identifier
    def load(self,identifier):
        path=self._path(identifier)
        if path.stat().st_size>MAX_REPORT_BYTES+65536:raise ValueError('Blockchain dossier exceeds storage budget')
        data=CredentialsStore._protect(path.read_bytes(),decrypt=True)
        if len(data)>MAX_REPORT_BYTES:raise ValueError('Blockchain dossier exceeds storage budget')
        value=json.loads(data.decode('utf-8'))
        if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('report'),dict):raise ValueError('Invalid saved blockchain dossier')
        report=value['report']
        if not isinstance(report.get('target_address'),str) or not isinstance(report.get('detected_chains'),list):raise ValueError('Invalid saved blockchain dossier')
        return report
