"""Reviewable personal-source plans; discovery alone never grants consent."""
import hashlib
import re
from urllib.parse import urlsplit


def personal_steps(calls,catalog):
    rows=[]
    for call in calls:
        meta=catalog.get(call['name'],{})
        kind=meta.get('kind');source=meta.get('source','')
        args=call['arguments']
        value=next((args[key] for key in ('email','phone','username','target','query')
                    if isinstance(args.get(key),str)),'')
        if not value or (kind not in ('email','phone','person','username') and
            not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+|\+\d{8,15}',value)):continue
        manifest=meta.get('manifest') or {}
        if manifest.get('network_requirements')=='none':continue
        contract=meta.get('source_contract') or manifest.get('source_contract') or {}
        provider=contract.get('provider_id') or ('maigret' if source=='maigret' else
            urlsplit(manifest.get('source_url','')).hostname or source or call['name'])
        rows.append({'fingerprint':call['fingerprint'],'target':hashlib.sha256(value.strip().casefold().encode('utf-8')).hexdigest(),
            'provider':provider,'tool':call['name'],'name':manifest.get('name') or call['name'],
            'value':value,'kind':kind or 'personal_identifier','region':contract.get('region',[]),
            'mode':manifest.get('execution_mode') or meta.get('execution_mode',''),
            'force_review':source=='maigret' or call['name']=='email_research'})
    return rows


def plan_review(steps,contacts,grants):
    providers={}
    for row in [*contacts,*steps]:providers.setdefault(row['target'],set()).add(row['provider'])
    return any(row['fingerprint'] not in grants and (row['force_review'] or len(providers[row['target']])>1) for row in steps)
