"""Local, provenance-bearing relations over existing validated evidence only.

No account discovery, identity inference, graph database or source execution.
An equal nickname on two platforms is deliberately two scoped identifiers.
"""
from copy import deepcopy
import hashlib
import math
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from .engine.models import canonical_url

ENTITY_TYPES=('username','public_profile','organization','domain','email','public_post','phone','image',
    'geographic_candidate','coordinate','repository','infrastructure_asset','blockchain_address','transaction','service',
    'root_entity','telegram_channel','social_profile','github_profile','github_repository','website','source','asset')


def verification(value):
    return {'verified':'verified','source_reported':'source_reported','self_reported':'source_reported',
        'historical_source_reported':'source_reported','model_hypothesis':'inferred', 'inferred':'inferred',
        'unverified_label':'unverified','unverified_metadata':'unverified', 'unconfirmed':'unverified',
        'contradictory':'contradicted','contradicted':'contradicted'}.get(value, 'unverified')


def _wallet(chain, value):
    chain=str(chain)
    if chain.lower() == 'ton':
        from .validators.ton_address import parse_ton_address
        parsed = parse_ton_address(value)
        if parsed: return parsed['raw']
    return value.lower() if chain.lower() in ('eth','ethereum','bsc','polygon','arbitrum','optimism','avalanche') else value


def _id(kind,key):return 'ent_'+hashlib.sha256((kind+'\0'+str(key)).encode('utf-8')).hexdigest()[:24]


def build(records,*,limit=50,offset=0,entity_types=(),center='',cancel_event=None,full=False,goal=''):
    if not isinstance(records, list): raise ValueError('Graph records must be a list')
    if type(limit) is not int or not 1<=limit<=(5000 if full else 100) or type(offset) is not int or not 0<=offset<=10000:
        raise ValueError('Invalid graph page')
    if set(entity_types)-set(ENTITY_TYPES):raise ValueError('Unknown entity type')
    nodes={};edges={};used=set();transfers={};bad_fields=0;truncated=False
    def node(kind,key,label,record,**attributes):
        nonlocal truncated
        key=str(key);eid=record.get('evidence_id') if record else None;identifier=_id(kind,key)
        if identifier not in nodes and len(nodes)>=5000:
            truncated=True;return None
        if identifier not in nodes:
            nodes[identifier]={'id':identifier,'type':kind,'label':str(label)[:300],'source':[],
                'attributes':deepcopy(attributes),'evidence_ids':[]}
        current=nodes[identifier]
        if eid and eid not in current['evidence_ids']:current['evidence_ids'].append(eid)
        source=str(record.get('platform',''))[:160] if record else ''
        if source and source not in current['source']:current['source'].append(source)
        if eid:used.add(eid)
        if 'reference_only' in attributes:
            attributes['reference_only'] = current['attributes'].get('reference_only', True) and attributes['reference_only']
        if current['attributes'].get('display_type') == 'telegram_channel': attributes.pop('display_type', None)
        current['attributes'].update(deepcopy(attributes))
        current['verification_status'] = ('unverified' if current['attributes'].get('reference_only') or not current['evidence_ids'] else
            'inferred' if kind=='geographic_candidate' else 'source_reported')
        return identifier
    def edge(a,b,kind,record,status='source_reported',**attributes):
        nonlocal truncated
        if not a or not b or a not in nodes or b not in nodes: return None
        key=(a,b,kind,attributes.get('asset',''));eid=record.get('evidence_id') if record else None
        if key not in edges and len(edges)>=20000:
            truncated=True;return None
        if key not in edges:edges[key]={'id':'rel_'+hashlib.sha256(repr(key).encode()).hexdigest()[:24],
            'from_id':a,'to_id':b,'relation_type':kind,'direction':'directed',
            'evidence_ids':[],'verification_status':verification(status),'claim_kind':status,'attributes':{},'source_urls':[]}
        current=edges[key]
        current['attributes'].update(deepcopy(attributes))
        if eid and eid not in current['evidence_ids']:current['evidence_ids'].append(eid)
        if record and record.get('url') and record['url'] not in current['source_urls']:current['source_urls'].append(record['url'])
        if record and record.get('verification')=='contradictory':current['verification_status']='contradicted'
        return current
    def url_node(url,record,*,reference=False,label=''):
        from .entity_router import route
        target=route(url)
        if target is None:return None
        if target.platform=='telegram' and target.entity_type!='public_post':
            canonical='https://t.me/'+target.identifier
            return node('public_profile',canonical,label or target.identifier,record,url=canonical,platform='telegram',username=target.identifier,
                display_type='social_profile',identity_verified=False,reference_only=reference)
        if target.entity_type=='github_profile':
            return node('public_profile',target.canonical_url,label or target.identifier,record,url=target.canonical_url,
                platform='github',username=target.identifier,display_type='github_profile',identity_verified=False,reference_only=reference)
        if target.entity_type=='github_repository':
            return node('repository',target.canonical_url,label or target.identifier,record,url=target.canonical_url,
                platform='github',display_type='github_repository',reference_only=reference)
        if target.entity_type=='public_post':
            return node('public_post',target.canonical_url,label or target.canonical_url,record,url=target.canonical_url,platform=target.platform,reference_only=reference)
        return node('website',target.canonical_url or url,label or target.canonical_url or url,record,
            url=target.canonical_url or url,reference_only=reference)
    cap=5000 if full else 500
    for record in records[:cap]:
        if cancel_event and cancel_event.is_set():raise InterruptedError('Graph cancelled')
        if not isinstance(record,dict) or not str(record.get('evidence_id','')).startswith('ev_') or record.get('type')=='evidence_graph':continue
        details=record.get('details') or {};kind=record.get('type');url=record.get('url','');platform=str(record.get('platform',''))
        if not isinstance(details,dict) or not isinstance(url,str):bad_fields+=1;continue
        resource=url or str(record.get('id',''));label=record.get('title') or resource
        try:host=urlsplit(url).hostname if url else None
        except ValueError:bad_fields+=1;continue
        wrong=next((key for key in ('chain','label','domain','address','username','screen_name','login','from_address','to_address')
                    if key in details and details[key] is not None and not isinstance(details[key],str)),None)
        if wrong:bad_fields+=1;continue
        current=None
        if (kind in ('profile','community') or host=='t.me') and url:
            canonical=canonical_url(details.get('canonical_url','')) or canonical_url(url)
            if host=='t.me':
                from .entity_router import route
                target=route(canonical)
                if target and target.entity_type!='public_post':canonical='https://t.me/'+target.identifier
            display='telegram_channel' if details.get('object_type_verified') and details.get('entity_type')=='telegram_channel' else 'github_profile' if host=='github.com' else 'social_profile'
            current=node('public_profile',canonical,label,record,url=canonical,identity_verified=False,platform='telegram' if host=='t.me' else 'github' if host=='github.com' else platform,display_type=display,reference_only=False)
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
        elif kind=='repository' and url:current=node('repository',canonical_url(url),label,record,url=canonical_url(url),reference_only=False,display_type='github_repository' if host=='github.com' else 'repository')
        elif kind=='street_image' and url:
            current=node('image',url,label,record,url=url,reference_photo=True,license=details.get('license'),attribution=details.get('attribution'))
            lat,lon=details.get('latitude'),details.get('longitude')
            if type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat+lon) and abs(lat)<=90 and abs(lon)<=180:
                coordinate=node('coordinate',str(lat)+'|'+str(lon),f'{lat}, {lon}',record,latitude=lat,longitude=lon)
                edge(current,coordinate,'reference_source_reports_coordinate',record,'source_reported')
        elif kind=='domain':
            domain=details.get('domain') or details.get('query')
            if isinstance(domain,str) and domain and ' ' not in domain:current=node('domain',domain.lower(),domain,record)
        elif kind=='ip':current=node('infrastructure_asset',details.get('address') or label,label,record,asset_type='ip')
        elif kind=='transaction':
            chain=details.get('chain') or platform;tx=details.get('tx_hash') or record.get('id')
            event=details.get('event_id') or tx
            current=node('transaction',chain+'|'+str(event),str(tx),record,chain=chain,url=url,tx_hash=tx,
                amount=details.get('amount_decimal',details.get('amount')),asset=details.get('asset'),timestamp=details.get('timestamp'))
            wallets={}
            for field,relation in [('from_address','sent_from'),('to_address','sent_to')]:
                address=details.get(field)
                if isinstance(address,str) and address:
                    canonical=_wallet(chain,address)
                    wallet=node('blockchain_address',chain+'|'+canonical,address,record,chain=chain,address=canonical,url='https://tonviewer.com/'+address if chain=='ton' else '',owner_verified=False)
                    wallets[field]=wallet
                    edge(current,wallet,relation,record)
            if full and all(wallets.get(field) for field in ('from_address','to_address')):
                asset=str(details.get('asset') or 'unknown')[:40]
                key=(wallets['from_address'],wallets['to_address'],asset)
                group=transfers.setdefault(key,{'records':[],'transactions':{},'amount':Decimal(0),'known':0,'unknown':0})
                if str(event) not in group['transactions']:
                    group['transactions'][str(event)]=current
                    try:
                        amount=Decimal(str(details.get('amount_decimal',details.get('amount'))))
                        if not amount.is_finite() or amount<0 or amount.adjusted()>60 or amount.adjusted()<-60:raise ValueError()
                    except (InvalidOperation,ValueError):group['unknown']+=1
                    else:group['amount']+=amount;group['known']+=1
                group['records'].append(record)
        elif kind=='label' and details.get('address') and details.get('label'):
            chain=details.get('chain') or platform
            canonical=_wallet(chain,str(details['address']))
            wallet=node('blockchain_address',chain+'|'+canonical,details['address'],record,chain=chain,address=canonical,owner_verified=False)
            service=node('service',platform+'|'+details['label'],details['label'],record,label_is_source_claim=True)
            edge(wallet,service,'source_labels_address',record,'unverified_label')
            current=wallet
        elif kind=='balance' and full:
            chain=str(details.get('chain') or platform);address=details.get('target_address') or details.get('address')
            if isinstance(address,str):
                address=_wallet(chain,address)
                current=node('blockchain_address',chain+'|'+address,address,record,chain=chain,address=address,owner_verified=False)
                if current:nodes[current]['attributes'].setdefault('balances',{})[str(details.get('asset') or 'unknown')]=details.get('amount_decimal',details.get('amount'))
        elif kind=='email' and full:
            address=details.get('email') or details.get('address')
            if isinstance(address,str):current=node('email',address.casefold(),address,record,address=address)
        elif full and url:
            current=url_node(url,record,label=label)
        image_details=details.get('image') if isinstance(details.get('image'),dict) else {}
        attachment=details.get('attachment_id') or image_details.get('id')
        image=None
        if isinstance(attachment,str) and re.fullmatch(r'img_[a-f0-9]{64}',attachment):
            image=node('image',attachment,attachment,record,attachment_id=attachment)
        predictions=details.get('predictions') if isinstance(details.get('predictions'),list) else []
        for prediction in predictions[:20]:
            if not image or not isinstance(prediction,dict):continue
            lat,lon=prediction.get('latitude',prediction.get('lat')),prediction.get('longitude',prediction.get('lon'))
            if type(lat) not in (int,float) or type(lon) not in (int,float) or not math.isfinite(lat+lon) or not -90<=lat<=90 or not -180<=lon<=180:continue
            candidate=node('geographic_candidate',attachment+'|'+str(details.get('model_version') or platform)+'|'+str(lat)+'|'+str(lon),
                f'{lat}, {lon}',record,latitude=lat,longitude=lon,rank=prediction.get('rank'),raw_score=prediction.get('raw_score'),model=details.get('model_version'),calibrated_probability=False)
            edge(image,candidate,'has_geographic_hypothesis',record,'model_hypothesis')
        metadata=details.get('metadata') if isinstance(details.get('metadata'),dict) else {};gps=metadata.get('gps')
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
        if full and current:
            links=details.get('links') if isinstance(details.get('links'),list) else []
            for link in links[:100]:
                if not isinstance(link,dict) or not isinstance(link.get('url'),str):continue
                linked=canonical_url(link['url'])
                link_host=urlsplit(linked).hostname
                if not linked or link_host in ('telegram.org','desktop.telegram.org','apps.apple.com','play.google.com'):continue
                target=url_node(linked,record,reference=True,label=str(link.get('text') or '')[:150])
                if target==current:continue
                observed=details.get('reading_method') in ('direct_http','browser_dom') and bool(details.get('body_sha256'))
                edge(current,target,'publishes_link',record,'verified' if observed else 'source_reported',observed_url=linked,identity_inference=False)
            if host=='github.com' and kind=='repository':
                parts=urlsplit(url).path.strip('/').split('/')
                if len(parts)>=2:
                    namespace=url_node('https://github.com/'+parts[0],record,reference=True,label=parts[0])
                    edge(current,namespace,'repository_namespace',record,'source_reported',identity_inference=False)
            source_key=canonical_url(url) or str(record.get('resource_id') or record.get('evidence_id'))
            source=node('source',source_key,str(record.get('platform') or 'Локальное свидетельство'),record,url=url,
                obtained_at=(record.get('provenance') or {}).get('obtained_at') if isinstance(record.get('provenance'),dict) else None)
            edge(current,source,'supported_by',record,'source_reported')
    for (a,b,asset),group in transfers.items():
        if cancel_event and cancel_event.is_set():raise InterruptedError('Graph cancelled')
        for record in group['records']:
            relation=edge(a,b,'transfers',record,'source_reported',asset=asset)
            if relation is not None:relation['aggregate']={'count':len(group['transactions']),
                'amount':format(group['amount'],'f') if group['known'] else None,'asset':asset,
                'known_amount_count':group['known'],'unknown_amount_count':group['unknown'],
                'transaction_ids':list(group['transactions'].values()),'coverage':'observed_transactions_only','owner_verified':False}
    root_id=''
    if full and goal:
        from .entity_router import route_goal
        targets=route_goal(goal)
        scoped=[]
        for target in targets:
            if target.entity_type=='blockchain_address' and target.tools:
                identifier=node('blockchain_address',target.platform+'|'+target.identifier,target.identifier,None,chain=target.platform,address=target.identifier,owner_verified=False)
            elif target.entity_type=='image':identifier=node('image',target.identifier,target.identifier,None,attachment_id=target.identifier)
            elif target.entity_type=='domain':identifier=node('domain',target.identifier,target.identifier,None,domain=target.identifier)
            elif target.entity_type=='email':identifier=node('email',target.identifier,target.identifier,None,address=target.identifier)
            elif target.entity_type=='infrastructure_asset':identifier=node('infrastructure_asset',target.identifier,target.identifier,None,asset_type='ip',address=target.identifier)
            elif target.entity_type=='geographic_coordinates':identifier=node('coordinate',str(target.properties['latitude'])+'|'+str(target.properties['longitude']),target.identifier,None,**target.properties)
            elif target.canonical_url:identifier=url_node(target.canonical_url,None,reference=True)
            else:continue
            if identifier:scoped.append(identifier)
        if len(scoped)==1:root_id=scoped[0]
        else:
            root_id=node('root_entity',goal[:12000],'Исследование',None,scope_only=True)
            for identifier in scoped:edge(root_id,identifier,'investigates',None,'unverified',scope_only=True)
        if root_id:nodes[root_id]['attributes']['is_root']=True
    all_nodes=list(nodes.values());all_edges=list(edges.values())
    if center:
        adjacent={center}
        links=[e for e in all_edges if center in (e['from_id'],e['to_id'])]
        adjacent.update(v for e in links for v in (e['from_id'],e['to_id']))
        all_nodes=[n for n in all_nodes if n['id'] in adjacent];all_edges=links
    if entity_types:all_nodes=[n for n in all_nodes if n['type'] in entity_types or n['attributes'].get('display_type') in entity_types]
    selected=all_nodes[offset:offset+limit];selected_ids={n['id'] for n in selected}
    # Cross-page edges retain endpoint IDs; request the neighbor page to expand.
    page_edges=[e for e in all_edges if e['from_id'] in selected_ids or e['to_id'] in selected_ids]
    edge_limit=20000 if full else 100
    selected_edges=page_edges[:edge_limit]
    return {'entities':selected,'relations':selected_edges,'total_entities':len(all_nodes),'total_relations':len(all_edges),
        'next_offset':offset+len(selected) if offset+len(selected)<len(all_nodes) else None,'evidence_ids':sorted(used),
        'root_id':root_id,'source_records_examined':min(len(records),cap),'truncated_input':len(records)>cap or truncated,
        'relations_truncated':len(page_edges)>edge_limit,'invalid_fields':bad_fields,
        'warnings':['Граф отражает основания источников. Одинаковый никнейм, метка сервиса и model score не устанавливают общую личность.']+
            (['Достигнут предел графа; показана ограниченная часть сохранённых данных.'] if truncated or len(records)>cap else [])+
            (['Некорректные поля отдельных записей исключены из графа.'] if bad_fields else [])}
