"""Local, provenance-bearing relations over existing validated evidence only.

No account discovery, identity inference, graph database or source execution.
An equal nickname on two platforms is deliberately two scoped identifiers.
"""
from copy import deepcopy
import hashlib
import math
import re
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit
from .engine.models import canonical_url

ENTITY_TYPES=('username','public_profile','organization','domain','email','public_post','phone','image',
    'geographic_candidate','coordinate','repository','infrastructure_asset','blockchain_address','transaction','service',
    'root_entity','telegram_channel','social_profile','github_profile','github_repository','website','source','asset','web3_identity')


def verification(value):
    return {'verified':'verified','source_reported':'source_reported','self_reported':'source_reported',
        'historical_source_reported':'source_reported','model_hypothesis':'inferred', 'inferred':'inferred',
        'unverified_label':'unverified','unverified_metadata':'unverified', 'unconfirmed':'unverified',
        'contradictory':'contradicted','contradicted':'contradicted'}.get(value, 'unverified')


def _wallet(chain, value):
    from .engine.blockchain_analytics import canonical_address
    return canonical_address(str(chain),value)


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
        if kind=='blockchain_address':
            originals=current['attributes'].setdefault('original_addresses',[])
            for value in (str(label),attributes.get('address')):
                if value and value not in originals:originals.append(value)
        if record and kind in ('asset','public_profile','repository','image','website','public_post'):
            from .public_media import media_reference
            media=media_reference(record)
            if media and kind not in ('source','domain','username'):current['attributes']['media']=media
        if record and record.get('url'):
            from .link_relevance import technical_url
            if technical_url(record['url']):current['attributes']['technical']=True
        current['verification_status'] = ('unverified' if current['attributes'].get('reference_only') or not current['evidence_ids'] else
            'inferred' if kind=='geographic_candidate' else 'source_reported')
        return identifier
    def edge(a,b,kind,record,status='source_reported',**attributes):
        nonlocal truncated
        if not a or not b or a not in nodes or b not in nodes: return None
        key=(a,b,kind,attributes.get('asset_key') or attributes.get('asset',''));eid=record.get('evidence_id') if record else None
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
        from .link_relevance import technical_url
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
            url=target.canonical_url or url,reference_only=reference,technical=technical_url(url))
    cap=5000 if full else 500
    for record in records[:cap]:
        if cancel_event and cancel_event.is_set():raise InterruptedError('Graph cancelled')
        if not isinstance(record,dict) or not str(record.get('evidence_id','')).startswith('ev_') or record.get('type')=='evidence_graph':continue
        from .agent_evidence import current_observation
        record=current_observation(record)
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
        elif kind in ('token_asset','nft_asset'):
            chain=details.get('chain') or 'ton'
            identity=details.get('asset_id') or details.get('contract') or record.get('id')
            current=node('asset',chain+'|'+_wallet(chain,identity),label,record,chain=chain,url=url,asset_type=kind,
                asset_id=identity,
                contract=details.get('contract'),amount=details.get('amount_decimal'),image_url=details.get('image_url'),
                ownership_status=details.get('ownership_status') or details.get('holding_status'),metadata_verified=False)
            wallet=details.get('target_address')
            collection=details.get('collection_address')
            if isinstance(collection,str) and collection:
                parent=node('asset',chain+'|collection|'+_wallet(chain,collection),details.get('collection') or collection,record,chain=chain,asset_type='nft_collection',collection=collection)
                # The item artwork belongs to the item, not to its collection.
                if parent:nodes[parent]['attributes'].pop('media',None)
                edge(current,parent,'source_reports_collection',record,'source_reported',metadata_verified=False)
            if wallet:
                owner=node('blockchain_address',chain+'|'+_wallet(chain,wallet),wallet,record,chain=chain,address=_wallet(chain,wallet),owner_verified=False)
                edge(owner,current,'source_reports_asset',record,'source_reported',ownership_verified=details.get('ownership_verified') is True,observed_at=details.get('collected_at'))
        elif kind=='contract_observation':
            chain=details.get('chain') or details.get('blockchain') or ''
            address=details.get('address') or details.get('target_address')
            current=node('infrastructure_asset',chain+'|contract|'+str(address),label,record,chain=chain,address=address,asset_type='blockchain_contract',url=url,
                observation={key:details[key] for key in ('source','status','code_verified','is_contract','deployer','proxy') if key in details},owner_verified=False)
            if address:
                wallet=node('blockchain_address',chain+'|'+_wallet(chain,address),address,record,chain=chain,address=address,owner_verified=False)
                edge(wallet,current,'has_contract_observation',record,'source_reported')
        elif kind=='web3_identity':
            chain=details.get('chain') or 'eth';wallet=details.get('address') or details.get('target_address')
            current=node('public_profile',str(record.get('id')),label,record,chain=chain,url=url,display_type='web3_identity',identity_verified=False)
            if wallet:
                owner=node('blockchain_address',chain+'|'+_wallet(chain,wallet),wallet,record,chain=chain,address=wallet,owner_verified=False)
                edge(owner,current,'has_public_web3_record',record,'source_reported',owner_verified=False)
        elif kind=='blockchain_counterparty':
            chain=details.get('chain') or '';address=details.get('address')
            if address:current=node('blockchain_address',chain+'|'+_wallet(chain,address),address,record,chain=chain,address=address,owner_verified=False)
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
                from .engine.blockchain_analytics import asset_identity, _date
                asset=str(details.get('asset') or 'unknown')
                asset_key,contract,identity_status=asset_identity(details,chain,record.get('evidence_id'))
                key=(wallets['from_address'],wallets['to_address'],asset_key)
                group=transfers.setdefault(key,{'records':[],'transactions':{},'amount':Decimal(0),'known':0,'unknown':0,
                    'asset':asset,'contract':contract,'identity_status':identity_status,'dates':[]})
                if str(event) not in group['transactions'] and details.get('success') is not False and details.get('status') not in ('failed','reverted','aborted'):
                    group['transactions'][str(event)]=current
                    if stamp:=_date(details.get('timestamp')):group['dates'].append(stamp)
                    try:
                        amount=Decimal(str(details.get('amount_decimal',details.get('amount'))))
                        if not amount.is_finite() or amount<0 or amount.adjusted()>60 or amount.adjusted()<-60:raise ValueError()
                    except (InvalidOperation,ValueError):group['unknown']+=1
                    else:
                        with localcontext() as context:context.prec=160;group['amount']+=amount
                        group['known']+=1
                group['records'].append(record)
        elif kind=='label' and details.get('address') and details.get('label'):
            chain=details.get('chain') or platform
            canonical=_wallet(chain,str(details['address']))
            wallet=node('blockchain_address',chain+'|'+canonical,details['address'],record,chain=chain,address=canonical,owner_verified=False)
            service=node('service',platform+'|'+details['label'],details['label'],record,label_is_source_claim=True)
            edge(wallet,service,'source_labels_address',record,'unverified_label')
            if wallet and details['label'] not in nodes[wallet]['attributes'].setdefault('labels',[]):nodes[wallet]['attributes']['labels'].append(details['label'])
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
    wallet_events={};wallet_peers={};wallet_assets={}
    for (a,b,asset_key),group in transfers.items():
        if cancel_event and cancel_event.is_set():raise InterruptedError('Graph cancelled')
        if not group['transactions']:continue
        for wallet,peer in ((a,b),(b,a)):
            wallet_events.setdefault(wallet,set()).update(group['transactions'].values())
            if wallet!=peer:wallet_peers.setdefault(wallet,set()).add(peer)
            wallet_assets.setdefault(wallet,set()).add(group['asset'])
        for record in group['records']:
            relation=edge(a,b,'transfers',record,'source_reported',asset=group['asset'],asset_key=asset_key)
            if relation is not None:relation['aggregate']={'count':len(group['transactions']),
                'amount':format(group['amount'],'f') if group['known'] else None,'asset':group['asset'],'asset_key':asset_key,
                'contract':group['contract'],'identity_status':group['identity_status'],
                'known_amount_count':group['known'],'unknown_amount_count':group['unknown'],
                'first_seen':min(group['dates']) if group['dates'] else None,'last_seen':max(group['dates']) if group['dates'] else None,
                'transaction_ids':list(group['transactions'].values()),'coverage':'observed_transactions_only','owner_verified':False}
    for wallet,events in wallet_events.items():
        nodes[wallet]['attributes'].update(transaction_count=len(events),counterparty_count=len(wallet_peers.get(wallet,())),assets=sorted(wallet_assets[wallet]))
    for record in records[:cap]:
        if not isinstance(record,dict) or record.get('type')!='blockchain_analytics':continue
        from .agent_evidence import current_observation
        record=current_observation(record);details=record.get('details') or {};data=details.get('data') or {}
        if not isinstance(data,dict):continue
        chain=str(details.get('chain') or '');target=details.get('target_address')
        if not chain or not isinstance(target,str):continue
        wallet=node('blockchain_address',chain+'|'+_wallet(chain,target),target,record,chain=chain,address=_wallet(chain,target),owner_verified=False)
        if wallet:
            nodes[wallet]['attributes'].update(transaction_count=data.get('unique_events'),
                resolved_transaction_count=len(wallet_events.get(wallet,())),counterparty_count=data.get('unique_counterparties'),
                unresolved_event_count=(data.get('directions') or {}).get('unresolved',0),
                metric_coverage='full_returned_sample_not_full_chain_history',metrics_source_evidence_id=record.get('evidence_id'),
                first_seen=data.get('first_seen'),last_seen=data.get('last_seen'))
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
