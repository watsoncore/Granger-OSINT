"""Local, provenance-bearing relations over existing validated evidence only.

No account discovery, identity inference, graph database or source execution.
An equal nickname on two platforms is deliberately two scoped identifiers.
"""
from copy import deepcopy
import hashlib
import math
from urllib.parse import urlsplit

ENTITY_TYPES=('username','public_profile','organization','domain','email','public_post','phone','image',
    'geographic_candidate','coordinate','repository','infrastructure_asset','blockchain_address','transaction','service')


def _id(kind,key):return 'ent_'+hashlib.sha256((kind+'\0'+str(key)).encode('utf-8')).hexdigest()[:24]


def build(records,*,limit=50,offset=0,entity_types=(),center='',cancel_event=None):
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or not 0<=offset<=10000:
        raise ValueError('Invalid graph page')
    if set(entity_types)-set(ENTITY_TYPES):raise ValueError('Unknown entity type')
    nodes={};edges={};used=set()
    def node(kind,key,label,record,**attributes):
        key=str(key);eid=record['evidence_id'];identifier=_id(kind,key)
        if identifier not in nodes:
            nodes[identifier]={'id':identifier,'type':kind,'label':str(label)[:300],'source':[],
                'attributes':deepcopy(attributes),'evidence_ids':[]}
        current=nodes[identifier]
        if eid not in current['evidence_ids']:current['evidence_ids'].append(eid)
        source=str(record.get('platform',''))[:160]
        if source not in current['source']:current['source'].append(source)
        used.add(eid)
        return identifier
    def edge(a,b,kind,record,verification='source_reported'):
        key=(a,b,kind);eid=record['evidence_id']
        if key not in edges:edges[key]={'from_id':a,'to_id':b,'relation_type':kind,'direction':'directed',
            'evidence_ids':[],'verification_status':verification}
        if eid not in edges[key]['evidence_ids']:edges[key]['evidence_ids'].append(eid)
    for record in records[:500]:
        if cancel_event and cancel_event.is_set():raise InterruptedError('Graph cancelled')
        if not isinstance(record,dict) or not str(record.get('evidence_id','')).startswith('ev_') or record.get('type')=='evidence_graph':continue
        details=record.get('details') or {};kind=record.get('type');url=record.get('url','');platform=str(record.get('platform',''))
        resource=url or str(record.get('id',''));label=record.get('title') or resource
        host=urlsplit(url).hostname if url else None
        current=None
        if kind in ('profile','community') and url:
            current=node('public_profile',url,label,record,url=url,identity_verified=False)
            username=details.get('login') or details.get('username') or details.get('screen_name')
            if isinstance(username,str) and username:
                scoped=node('username',platform+'|'+username,username,record,platform=platform)
                edge(current,scoped,'uses_public_identifier',record)
            company=details.get('company')
            if isinstance(company,str) and company.strip():
                org=node('organization',platform+'|'+company,company,record,statement='profile_field_not_independent_employment_verification')
                edge(current,org,'profile_mentions_organization',record,'self_reported')
        elif kind in ('post','publication') and url:
            current=node('public_post',url,label,record,url=url,published_at=details.get('created_at') or details.get('date_utc'))
            author=details.get('author')
            if isinstance(author,str) and author and author not in ('[deleted]','[removed]'):
                author_node=node('username',platform+'|'+author,author,record,platform=platform)
                edge(current,author_node,'source_attributes_authorship',record)
        elif kind=='repository' and url:current=node('repository',url,label,record,url=url)
        elif kind=='domain':
            domain=details.get('domain') or details.get('query')
            if isinstance(domain,str) and domain and ' ' not in domain:current=node('domain',domain.lower(),domain,record)
        elif kind=='ip':current=node('infrastructure_asset',details.get('address') or label,label,record,asset_type='ip')
        elif kind=='transaction':
            chain=details.get('chain') or platform;tx=details.get('tx_hash') or record.get('id')
            current=node('transaction',chain+'|'+str(tx),str(tx),record,chain=chain)
            for field,relation in [('from_address','sent_from'),('to_address','sent_to')]:
                address=details.get(field)
                if isinstance(address,str) and address:
                    wallet=node('blockchain_address',chain+'|'+address,address,record,chain=chain,owner_verified=False)
                    edge(current,wallet,relation,record)
        elif kind=='label' and details.get('address') and details.get('label'):
            chain=details.get('chain') or platform
            wallet=node('blockchain_address',chain+'|'+details['address'],details['address'],record,chain=chain,owner_verified=False)
            service=node('service',platform+'|'+details['label'],details['label'],record,label_is_source_claim=True)
            edge(wallet,service,'source_labels_address',record,'unverified_label')
            current=wallet
        attachment=details.get('attachment_id') or (details.get('image') or {}).get('id')
        image=None
        if isinstance(attachment,str) and attachment.startswith('img_'):
            image=node('image',attachment,attachment,record,attachment_id=attachment)
        for prediction in details.get('predictions',[])[:20]:
            if not image or not isinstance(prediction,dict):continue
            lat,lon=prediction.get('latitude'),prediction.get('longitude')
            if type(lat) not in (int,float) or type(lon) not in (int,float) or not math.isfinite(lat+lon) or not -90<=lat<=90 or not -180<=lon<=180:continue
            candidate=node('geographic_candidate',record['evidence_id']+'|'+str(prediction.get('rank'))+'|'+str(lat)+'|'+str(lon),
                f'{lat}, {lon}',record,latitude=lat,longitude=lon,rank=prediction.get('rank'),raw_score=prediction.get('raw_score'),model=details.get('model_version'),calibrated_probability=False)
            edge(image,candidate,'has_geographic_hypothesis',record,'model_hypothesis')
        metadata=details.get('metadata') or {};gps=metadata.get('gps')
        if image and isinstance(gps,dict):
            lat,lon=gps.get('latitude'),gps.get('longitude')
            if type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat+lon) and -90<=lat<=90 and -180<=lon<=180:
                coordinate=node('coordinate',str(lat)+'|'+str(lon),f'{lat}, {lon}',record,latitude=lat,longitude=lon,metadata_authenticity_verified=False)
                edge(image,coordinate,'metadata_reports_coordinate',record,'unverified_metadata')
        if host and current and nodes[current]['type']!='domain':
            domain=node('domain',host,host,record)
            edge(current,domain,'published_on_domain',record)
        contacts=details.get('contacts')
        domain=details.get('domain')
        if isinstance(domain,str) and isinstance(contacts,list):
            domain_id=node('domain',domain.lower(),domain,record)
            for contact in contacts[:50]:
                if not isinstance(contact,dict):continue
                value=contact.get('value');contact_type=contact.get('type') or contact.get('kind')
                if contact_type not in ('email','phone') or not isinstance(value,str) or not value:continue
                endpoint=node(contact_type,value.casefold() if contact_type=='email' else value,value,record,historical=True)
                edge(domain_id,endpoint,'historically_published_contact',record,'historical_source_reported')
    all_nodes=list(nodes.values());all_edges=list(edges.values())
    if center:
        adjacent={center}
        links=[e for e in all_edges if center in (e['from_id'],e['to_id'])]
        adjacent.update(v for e in links for v in (e['from_id'],e['to_id']))
        all_nodes=[n for n in all_nodes if n['id'] in adjacent];all_edges=links
    if entity_types:all_nodes=[n for n in all_nodes if n['type'] in entity_types]
    selected=all_nodes[offset:offset+limit];selected_ids={n['id'] for n in selected}
    # Cross-page edges retain endpoint IDs; request the neighbor page to expand.
    selected_edges=[e for e in all_edges if e['from_id'] in selected_ids or e['to_id'] in selected_ids][:200]
    return {'entities':selected,'relations':selected_edges,'total_entities':len(all_nodes),'total_relations':len(all_edges),
        'next_offset':offset+len(selected) if offset+len(selected)<len(all_nodes) else None,'evidence_ids':sorted(used),
        'source_records_examined':min(len(records),500),'truncated_input':len(records)>500,
        'warnings':['Граф отражает основания источников. Одинаковый никнейм, метка сервиса и model score не устанавливают общую личность.']}
