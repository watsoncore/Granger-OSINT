"""Local, provenance-bearing relations over existing validated evidence only.

No account discovery, identity inference, graph database or source execution.
An equal nickname on two platforms is deliberately two scoped identifiers.
"""
from copy import deepcopy
import hashlib
import ipaddress
import math
import re
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit
from .engine.models import canonical_url

ENTITY_TYPES=('username','public_profile','organization','domain','email','public_post','phone','image',
    'geographic_candidate','coordinate','repository','infrastructure_asset','blockchain_address','transaction','service',
    'root_entity','telegram_channel','social_profile','github_profile','github_repository','website','source','asset','web3_identity','entity_group')


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
    nodes={};edges={};used=set();transfers={};bad_fields=0;truncated=False;technical_exclusions=[]
    geo_candidates={};geo_references=[]
    from .entity_router import route_goal
    explicit_urls={canonical_url(target.canonical_url) for target in route_goal(goal) if target.canonical_url}
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
        if current['attributes'].get('reference_only') and attributes.get('reference_only') is False:current['label']=str(label)[:300]
        if 'reference_only' in attributes:
            attributes['reference_only'] = current['attributes'].get('reference_only', True) and attributes['reference_only']
        if current['attributes'].get('display_type') == 'telegram_channel': attributes.pop('display_type', None)
        current['attributes'].update(deepcopy(attributes))
        if kind=='blockchain_address':
            originals=current['attributes'].setdefault('original_addresses',[])
            for value in (str(label),attributes.get('address')):
                if value and value not in originals:originals.append(value)
        if (record and kind in ('asset','public_profile','repository','image','website','public_post','inventory_item')
                and (record.get('type')!='steam_item' or kind=='inventory_item')):
            from .public_media import media_reference
            media=media_reference(record)
            if media and kind not in ('source','domain','username'):current['attributes']['media']=media
        if record and record.get('url') and kind in ('source','service','website'):
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
        data=(record or {}).get('details') or {};origin=(record or {}).get('provenance') or {}
        field=attributes.get('observed_field') or {
            'sent_from':'from_address','sent_to':'to_address','source_labels_address':'label',
            'uses_public_identifier':'login/username/screen_name','has_geographic_hypothesis':'predictions',
            'metadata_reports_coordinate':'metadata.gps','transfers':'event_id,from_address,to_address,amount_decimal,asset',
            'source_reports_asset':'target_address,asset_id/contract','reference_source_reports_coordinate':'latitude,longitude',
            'repository_namespace':'url.path','source_attributes_authorship':'author','published_on_domain':'url.hostname',
            'supported_by':'evidence_id','profile_mentions_organization':'company'}.get(kind,kind)
        observation={'subject':a,'predicate':kind,'object':b,'source_url':(record or {}).get('url',''),
            'source_record_id':eid,'observed_text_or_field':attributes.get('observed_text') or field,'observed_field':field,
            'extraction_method':attributes.get('extraction_method') or data.get('reading_method') or data.get('acquisition') or origin.get('acquisition') or ('user_scope' if not record else 'structured_adapter_result'),
            'verification_status':current['verification_status'],'observed_at':data.get('retrieved_at') or data.get('collected_at') or origin.get('obtained_at') or (record or {}).get('obtained_at')}
        origins=current.setdefault('provenance',[])
        if observation not in origins:
            if len(origins)<100:origins.append(observation)
            else:current['provenance_truncated']=True
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
        if target.platform=='steam':
            return node('public_profile',target.canonical_url,label or target.identifier,record,url=target.canonical_url,
                platform='steam',display_type='social_profile',identity_verified=False,reference_only=reference)
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
        from .link_relevance import technical_url, unscoped_web_marker
        if unscoped_web_marker(record):
            technical_exclusions.append({'evidence_id':record.get('evidence_id'),'url':url,'reason':'unscoped_css_like_marker_requires_source_review'})
            continue
        if url and technical_url(url) and canonical_url(url) not in explicit_urls and kind not in ('ip','domain','threat_indicator'):
            technical_exclusions.append({'evidence_id':record.get('evidence_id'),'url':url,'reason':'site_navigation_or_media_metadata'})
            continue
        resource=url or str(record.get('id',''));label=record.get('title') or resource
        try:host=urlsplit(url).hostname if url else None
        except ValueError:bad_fields+=1;continue
        wrong=next((key for key in ('chain','label','domain','address','username','screen_name','login','from_address','to_address')
                    if key in details and details[key] is not None and not isinstance(details[key],str)),None)
        if wrong:bad_fields+=1;continue
        current=None
        if kind in ('steam_item','steam_inventory') and isinstance(details.get('steamid64'),str):
            owner_url=details.get('canonical_url') or 'https://steamcommunity.com/profiles/'+details['steamid64']
            owner=url_node(owner_url,record,reference=False)
            scope=details['steamid64']+'|'+str(details.get('appid'))+'|'+str(details.get('contextid'))
            game=node('steam_inventory',scope,'CS2 · инвентарь' if details.get('appid')==730 else 'Steam app '+str(details.get('appid')),
                record,display_type='steam_inventory',steamid64=details['steamid64'],appid=details.get('appid'),contextid=details.get('contextid'),url=owner_url+'/inventory/')
            edge(owner,game,'has_public_inventory',record,observed_field='steamid64,appid,contextid')
            current=game
            if kind=='steam_item' and isinstance(details.get('assetid'),str):
                category=str(details.get('category') or 'Не классифицировано')
                group=node('entity_group',scope+'|'+category,category,record,display_type='inventory_category',
                    grouped_type='inventory_item',scope=scope,grouping_only=True)
                edge(game,group,'contains_inventory_category',record,observed_field='tags.Type')
                attrs={key:deepcopy(details.get(key)) for key in ('steamid64','appid','contextid','assetid','classid','instanceid','amount',
                    'name','market_hash_name','category','rarity','quality','exterior','float_value','pattern_template','price','image_url')}
                current=node('inventory_item',scope+'|'+details['assetid'],details.get('name') or 'Предмет '+details['assetid'],record,
                    **attrs,display_type='inventory_item',parent_group_id=group,url=url,ownership_verified=False)
                if group and current:
                    members=nodes[group]['attributes'].setdefault('member_ids',[])
                    if current not in members:members.append(current)
                    nodes[group]['attributes']['member_count']=len(members)
                edge(group,current,'contains_inventory_item',record,observed_field='assets[].assetid + descriptions.tags')
                edge(owner,current,'owns_public_item',record,observed_field='public_inventory.assets[].assetid')
        elif (kind in ('profile','community') or host=='t.me' and kind not in ('post','publication')) and url:
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
            if platform=='steam' and current:
                nodes[current]['attributes'].update(steamid64=details.get('steamid64'),requested_profile=details.get('requested_profile'))
                if isinstance(details.get('aliases'),list):nodes[current]['attributes']['public_aliases']=deepcopy(details['aliases'][:20])
                for peer in details.get('friends',[])[:20] if isinstance(details.get('friends'),list) else []:
                    if not isinstance(peer,str):continue
                    friend=url_node(peer,record,reference=True)
                    if friend!=current:edge(current,friend,'public_friend_link',record,'source_reported',observed_field='friends[]')
        elif kind in ('post','publication') and url:
            current=node('public_post',url,label,record,url=url,published_at=details.get('created_at') or details.get('date_utc'),author=details.get('author'))
            author=details.get('author')
            if isinstance(author,str) and author and author not in ('[deleted]','[removed]'):
                author_node=node('username',platform+'|'+author,author,record,platform=platform)
                edge(current,author_node,'source_attributes_authorship',record)
        elif kind=='repository' and url:current=node('repository',canonical_url(url),label,record,url=canonical_url(url),reference_only=False,display_type='github_repository' if host=='github.com' else 'repository')
        elif kind=='geoint_candidate':
            lat,lon=details.get('latitude'),details.get('longitude');attachment=details.get('attachment_id')
            if isinstance(attachment,str) and type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat+lon) and abs(lat)<=90 and abs(lon)<=180:
                current=node('geographic_candidate',attachment+f'|{lat:.5f}|{lon:.5f}',details.get('region') or f'Гипотеза: {lat:.3f}, {lon:.3f}',record,
                    latitude=lat,longitude=lon,candidate_id=details.get('candidate_id'),attachment_id=attachment,
                    geographic_status=details.get('verification_status','model_candidate'),calibrated_probability=False,
                    raw_prediction_only=False,
                    region=details.get('region'),source_model=details.get('source_model'))
                geo_candidates[(attachment,details.get('candidate_id'))]=current
                if current and details.get('region'):nodes[current]['label']=details['region'][:300]
        elif kind in ('street_image','reference_image') and url:
            current=node('image',details.get('image_url') or url,label,record,url=url,reference_photo=True,
                license=details.get('license'),attribution=details.get('author') or details.get('attribution'),
                captured_at=details.get('captured_at'),image_url=details.get('image_url'),
                latitude=details.get('latitude'),longitude=details.get('longitude'),
                comparison_status=(details.get('comparison') or {}).get('status'),geolocation_verified=False)
            if kind=='reference_image':geo_references.append((current,details.get('attachment_id'),details.get('candidate_id'),record))
            lat,lon=details.get('latitude'),details.get('longitude')
            if type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat+lon) and abs(lat)<=90 and abs(lon)<=180:
                coordinate=node('coordinate',str(lat)+'|'+str(lon),f'{lat}, {lon}',record,latitude=lat,longitude=lon)
                edge(current,coordinate,'reference_source_reports_coordinate',record,'source_reported')
        elif kind=='domain':
            domain=details.get('domain') or details.get('query')
            if isinstance(domain,str) and domain and ' ' not in domain:current=node('domain',domain.lower(),domain,record)
            answers=details.get('answers',[])
            if not isinstance(answers,list):answers=[]
            if details.get('value'):answers=answers+[{'type':{'A':1,'AAAA':28,'CNAME':5,'NS':2,'MX':15}.get(details.get('record_type')),'data':details['value']}]
            for answer in answers[:30]:
                if not isinstance(answer,dict) or answer.get('type') not in (1,2,5,15,28):continue
                value=answer.get('data')
                if not isinstance(value,str):continue
                if answer['type'] in (1,28):
                    try:address=str(ipaddress.ip_address(value))
                    except ValueError:continue
                    linked=node('infrastructure_asset',address,address,record,asset_type='ip',address=address)
                    edge(current,linked,'resolves_to',record,'source_reported',observed_field='answers[].data')
                else:
                    name=value.split()[-1].rstrip('.').lower() if value.split() else ''
                    if not name or not re.fullmatch(r'[a-z0-9.-]+',name):continue
                    linked=node('domain',name,name,record)
                    edge(current,linked,{2:'uses_nameserver',5:'dns_alias_of',15:'uses_mail_exchange'}[answer['type']],record,'source_reported',observed_field='answers[].data')
        elif kind in ('ip','threat_indicator'):
            address=details.get('address') or details.get('query')
            if not isinstance(address,str):continue
            try:
                address=str(ipaddress.ip_network(address,strict=False) if '/' in address else ipaddress.ip_address(address))
            except ValueError:
                if not re.fullmatch(r'AS[1-9][0-9]{0,9}',address,re.I):continue
                address=address.upper()
            current=node('infrastructure_asset',address,address,record,address=address,
                asset_type='asn' if address.startswith('AS') else 'cidr' if '/' in address else 'ip')
            network_data=details.get('data') if isinstance(details.get('data'),dict) else {}
            prefix=details.get('prefix') or network_data.get('prefix')
            routed=current
            if isinstance(prefix,str):
                try:prefix=str(ipaddress.ip_network(prefix,strict=False))
                except ValueError:prefix=''
                if prefix and prefix!=address:
                    routed=node('infrastructure_asset',prefix,prefix,record,address=prefix,asset_type='cidr')
                    edge(current,routed,'within_announced_prefix',record,'source_reported',observed_field='prefix')
            asns=details.get('asns') or network_data.get('asns') or []
            for asn in asns[:20] if isinstance(asns,list) else []:
                holder=asn.get('holder') if isinstance(asn,dict) else None
                number=asn.get('asn') if isinstance(asn,dict) else asn
                if not re.fullmatch(r'[1-9][0-9]{0,9}',str(number)) or int(number)>4294967295:continue
                identifier='AS'+str(number)
                linked=node('infrastructure_asset',identifier,identifier,record,address=identifier,asset_type='asn',holder=holder)
                if linked!=routed:edge(routed,linked,'announced_by',record,'source_reported',observed_field='asns')
            registered=current
            if details.get('startAddress') and details.get('endAddress'):
                interval=str(details['startAddress'])+' — '+str(details['endAddress'])
                from .network_semantics import registration_match
                try:match=details.get('registration_match') or registration_match(address,details)
                except (ValueError,TypeError):match={}
                prefixes=match.get('returned_prefixes',[]) if isinstance(match,dict) else []
                label=prefixes[0] if len(prefixes)==1 else interval
                parent=match.get('match_type')=='matched_parent' if isinstance(match,dict) else False
                registered=node('infrastructure_asset',interval,label+(' · реестровый родитель' if parent else ' · реестровый диапазон'),record,
                    asset_type='registered_range',start=details['startAddress'],end=details['endAddress'],registration_match=match,
                    returned_prefixes=prefixes,requested_resource=address,not_bgp_prefix=True)
                relation='matched_parent_registration' if parent else 'overlaps_registered_range' if isinstance(match,dict) and match.get('match_type') in ('matched_subrange','overlap','mismatch') else 'within_registered_range'
                edge(current,registered,relation,record,'source_reported',observed_field='startAddress,endAddress')
            for entity in details.get('registry_entities',[]) if isinstance(details.get('registry_entities'),list) else []:
                if not isinstance(entity,dict) or not isinstance(entity.get('name'),str):continue
                from .network_semantics import registry_entity_type
                entity_type=registry_entity_type(entity)
                roles=entity.get('roles');roles=roles if isinstance(roles,list) else []
                identity=str(url).split('/ip/')[0]+'|'+entity['name']
                kind='organization' if entity_type=='organization' else 'registry_contact'
                entity_label=(entity.get('handle') or entity['name']) if entity_type=='maintainer' else entity['name']
                org=node(kind,identity,entity_label,record,registry_only=True,identity_verified=False,registry_entity_type=entity_type,
                    display_type='registry_'+entity_type if kind=='registry_contact' else 'organization',roles=roles,not_service_operator_attribution=True)
                relation='registered_to' if entity_type=='organization' and 'registrant' in roles else 'maintained_by' if entity_type=='maintainer' else 'registry_administered_by' if entity_type=='registry_authority' else 'has_registry_contact'
                edge(registered,org,relation,record,'source_reported',observed_field='registry_entities')
            geo=details.get('geoip')
            if isinstance(geo,dict):
                place=', '.join(str(geo[key]) for key in ('country_name','city') if geo.get(key))
                estimate=node('geoip_estimate',address+'|'+str(geo.get('provider')),place or 'GeoIP · неизвестно',record,
                    provider=geo.get('provider'),latitude=geo.get('latitude'),longitude=geo.get('longitude'),
                    location_kind='ip_database_estimate',accuracy_radius_km=None,exact_device_location_verified=False)
                edge(current,estimate,'geoip_estimates_location',record,'source_reported',observed_field='geoip',approximate=True)
            if details.get('record_type')=='PTR':
                for answer in details.get('answers',[]) if isinstance(details.get('answers'),list) else []:
                    name=answer.get('value') if isinstance(answer,dict) else None
                    if isinstance(name,str) and re.fullmatch(r'[a-zA-Z0-9.-]+',name):
                        host=node('domain',name.rstrip('.').lower(),name.rstrip('.'),record)
                        edge(current,host,'reverse_dns_reports',record,'source_reported',observed_field='answers[].value')
        elif kind in ('token_asset','nft_asset'):
            chain=details.get('chain') or 'ton'
            identity=details.get('asset_id') or details.get('contract') or record.get('id')
            current=node('asset',chain+'|'+_wallet(chain,identity),label,record,chain=chain,url=url,asset_type=kind,
                asset_id=identity,
                symbol=details.get('symbol') or details.get('name') or label,
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
            image=node('image',attachment,'Исходная фотография',record,attachment_id=attachment,original_image=True)
            # A reference's URL/preview belongs to the reference, never the original.
            if image:nodes[image]['attributes'].pop('media',None)
            if image and details.get('tool')=='image_understand':nodes[image]['attributes']['scene_description']=details.get('description')
            if current and kind=='geoint_candidate':edge(image,current,'has_geographic_hypothesis',record,'model_hypothesis',observed_field='latitude,longitude,verification_status')
        predictions=details.get('predictions') if isinstance(details.get('predictions'),list) else []
        for prediction in predictions[:20]:
            if not image or not isinstance(prediction,dict):continue
            lat,lon=prediction.get('latitude',prediction.get('lat')),prediction.get('longitude',prediction.get('lon'))
            if type(lat) not in (int,float) or type(lon) not in (int,float) or not math.isfinite(lat+lon) or not -90<=lat<=90 or not -180<=lon<=180:continue
            candidate=node('geographic_candidate',attachment+f'|{lat:.5f}|{lon:.5f}',
                f'Гипотеза: {lat:.3f}, {lon:.3f}',record,attachment_id=attachment,latitude=lat,longitude=lon,rank=prediction.get('rank'),raw_score=prediction.get('raw_score'),model=details.get('model_version'),calibrated_probability=False)
            if candidate and not nodes[candidate]['attributes'].get('candidate_id'):nodes[candidate]['attributes']['raw_prediction_only']=True
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
            from .link_relevance import substantive_link,technical_url
            navigation=deepcopy(details.get('navigation_links') or [])
            unclassified=[]
            for link in links[:100]:
                if not isinstance(link,dict) or not isinstance(link.get('url'),str):continue
                if not substantive_link(link):
                    (navigation if technical_url(link['url']) or link.get('content_region')=='navigation' else unclassified).append(deepcopy(link))
                    continue
                linked=canonical_url(link['url'])
                link_host=urlsplit(linked).hostname
                if not linked or link_host in ('telegram.org','desktop.telegram.org','apps.apple.com','play.google.com'):continue
                target=url_node(linked,record,reference=True,label=str(link.get('text') or '')[:150])
                if target==current:continue
                observed=details.get('reading_method') in ('direct_http','browser_dom') and bool(details.get('body_sha256'))
                edge(current,target,'publishes_link',record,'verified' if observed else 'source_reported',observed_url=linked,identity_inference=False,
                    observed_field='links.url',observed_text=link.get('text') or linked,extraction_method=link['extraction_method'],
                    content_region=link['content_region'],selector=link.get('selector'))
            if navigation:nodes[current]['attributes']['navigation_metadata']=navigation[:100]
            if unclassified:nodes[current]['attributes']['unclassified_links']=unclassified[:100]
            if host=='github.com' and kind=='repository':
                parts=urlsplit(url).path.strip('/').split('/')
                if len(parts)>=2:
                    namespace=url_node('https://github.com/'+parts[0],record,reference=True,label=parts[0])
                    edge(current,namespace,'repository_namespace',record,'source_reported',identity_inference=False)
            source_url=details.get('source_endpoint') if kind=='steam_item' and isinstance(details.get('source_endpoint'),str) else url
            source_key=canonical_url(source_url) or str(record.get('resource_id') or record.get('evidence_id'))
            source=node('source',source_key,str(record.get('platform') or 'Локальное свидетельство'),record,url=source_url,
                obtained_at=(record.get('provenance') or {}).get('obtained_at') if isinstance(record.get('provenance'),dict) else None)
            edge(current,source,'supported_by',record,'source_reported')
    for reference,attachment,candidate_id,record in geo_references:
        candidate=geo_candidates.get((attachment,candidate_id))
        if candidate:edge(candidate,reference,'reference_for_candidate',record,'unverified',observed_field='candidate_id,image_url',geolocation_verified=False)
        comparison=(record.get('details') or {}).get('comparison') or {}
        if comparison.get('status')=='complete':
            original=_id('image',attachment)
            edge(original,reference,'locally_compared_with',record,'model_hypothesis',observed_field='comparison',
                match_count=comparison.get('match_count'),geolocation_verified=False)
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
            elif target.entity_type in ('infrastructure_asset','network_range','autonomous_system'):
                identifier=node('infrastructure_asset',target.identifier,target.identifier,None,
                    asset_type='asn' if target.entity_type=='autonomous_system' else 'cidr' if target.entity_type=='network_range' else 'ip',address=target.identifier)
            elif target.entity_type=='geographic_coordinates':identifier=node('coordinate',str(target.properties['latitude'])+'|'+str(target.properties['longitude']),target.identifier,None,**target.properties)
            elif target.platform=='steam':
                identifier=next((key for key,n in nodes.items() if n['attributes'].get('requested_profile')==target.canonical_url),None)
                identifier=identifier or url_node(target.canonical_url,None,reference=True)
            elif target.canonical_url:identifier=url_node(target.canonical_url,None,reference=True)
            else:continue
            if identifier:scoped.append(identifier)
        if not scoped:scoped=[identifier for identifier,value in nodes.items() if value['attributes'].get('original_image')]
        if len(scoped)==1:root_id=scoped[0]
        else:
            root_id=node('root_entity',goal[:12000],'Исследование',None,scope_only=True)
            for identifier in scoped:edge(root_id,identifier,'investigates',None,'unverified',scope_only=True)
        if root_id:nodes[root_id]['attributes']['is_root']=True
    asset_labels={value['attributes'].get('chain','')+'|'+_wallet(value['attributes'].get('chain',''),value['attributes'].get('contract') or value['attributes'].get('asset_id')):
        value['attributes'].get('symbol') or value['label'] for value in nodes.values() if value['type']=='asset'}
    for relation in edges.values():
        aggregate=relation.get('aggregate')
        if not aggregate:continue
        aggregate['asset_label']=asset_labels.get(aggregate['asset_key']) or aggregate['asset']
        a,b=relation['from_id'],relation['to_id']
        if root_id and a!=b and root_id in (a,b):
            peer=b if a==root_id else a
            nodes[peer]['attributes'].setdefault('flow_summaries',[]).append({
                'direction':'from_target' if a==root_id else 'to_target','count':aggregate['count'],
                'amount':aggregate['amount'],'asset':aggregate['asset_label'],'asset_key':aggregate['asset_key'],
                'unknown_amount_count':aggregate['unknown_amount_count']})
    for value in nodes.values():
        if value['attributes'].get('flow_summaries'):value['attributes']['flow_summaries'].sort(key=lambda flow:-flow['count'])
    if full and root_id:
        buckets={}
        for identifier,value in list(nodes.items()):
            if identifier==root_id or value['attributes'].get('technical'):continue
            kind=value['type'];attrs=value['attributes'];url=attrs.get('url') or ''
            if kind not in ('public_post','website','repository','asset','blockchain_address'):continue
            parts=urlsplit(url);host=parts.hostname or attrs.get('chain') or ''
            if kind=='public_post':scope=(attrs.get('author') or parts.path.strip('/').split('/')[0]) if host=='t.me' else attrs.get('author') or host
            elif kind=='repository':scope=parts.path.strip('/').split('/')[0]
            elif kind=='asset':scope=attrs.get('collection') or attrs.get('asset_type') or 'assets'
            elif kind=='blockchain_address':scope='Остальные контрагенты'
            else:scope=host
            if host:buckets.setdefault((kind,host,str(scope)),[]).append(identifier)
        names={'public_post':'Публикации','website':'Страницы','repository':'Репозитории','asset':'Активы','blockchain_address':'Контрагенты'}
        for (kind,host,scope),members in buckets.items():
            if kind=='blockchain_address':
                members=sorted(members,key=lambda identifier:-(nodes[identifier]['attributes'].get('transaction_count') or 0))[8:]
            if len(members)<12:continue
            group=node('entity_group',kind+'|'+host+'|'+scope,f'{names[kind]} · {scope or host}',None,
                member_ids=members,member_count=len(members),grouped_type=kind,scope=scope,grouping_only=True)
            if not group:continue
            nodes[group]['evidence_ids']=list(dict.fromkeys(eid for member in members for eid in nodes[member]['evidence_ids']))[:150]
            edge(root_id,group,'groups_observations',None,'unverified',grouping_only=True,observed_field='member_ids',extraction_method='local_presentation_grouping')
            for member in members:
                nodes[member]['attributes']['parent_group_id']=group
                edge(group,member,'group_contains',None,'unverified',grouping_only=True,observed_field='member_ids',extraction_method='local_presentation_grouping')
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
        'technical_exclusions':technical_exclusions,
        'relations_truncated':len(page_edges)>edge_limit,'invalid_fields':bad_fields,
        'warnings':['Граф отражает основания источников. Одинаковый никнейм, метка сервиса и model score не устанавливают общую личность.']+
            (['Достигнут предел графа; показана ограниченная часть сохранённых данных.'] if truncated or len(records)>cap else [])+
            (['Некорректные поля отдельных записей исключены из графа.'] if bad_fields else [])}
