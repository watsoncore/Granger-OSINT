"""Source-bearing technical profiles selected from saved network observations."""
from collections import defaultdict
import ipaddress
import re


def profiles(records):
    result = {}
    seen = {}
    for row in records:
        if not isinstance(row,dict): continue
        data=row.get('details'); data=data if isinstance(data,dict) else {}
        if row.get('type') not in ('ip','domain','threat_indicator'): continue
        resource=data.get('address') or data.get('domain') or data.get('query')
        if not isinstance(resource,str): continue
        if row.get('type')=='domain':
            from .agent_web import _domain
            try: resource=_domain(resource)
            except (ValueError,UnicodeError): continue
            kind='domain'
        else:
            try:
                resource=str(ipaddress.ip_network(resource,strict=False) if '/' in resource else ipaddress.ip_address(resource))
            except ValueError:
                if not re.fullmatch(r'AS[1-9][0-9]{0,9}',resource,re.I): continue
                resource=resource.upper()
            kind='network'
        profile=result.setdefault(resource,{'resource':resource,'kind':kind,'facts':[],'conflicts':[]})
        def add(label,value):
            if value is None or value=='' or value==[]: return
            if isinstance(value,list): value='; '.join(str(v) for v in value)[:3000]
            elif isinstance(value,dict): return  # Raw structures stay in evidence, not prose.
            if label=='BGP-префикс':
                try:value=str(ipaddress.ip_network(str(value),strict=False))
                except ValueError:pass
            origin={'url':row.get('url'),'observed_at':data.get('source_observed_at') or data.get('obtained_at') or row.get('date')}
            key=(resource,label,str(value))
            if key in seen:
                if origin not in seen[key]['sources']:seen[key]['sources'].append(origin)
                return
            fact={'label':label,'value':value,**origin,'sources':[origin]}
            seen[key]=fact;profile['facts'].append(fact)
        add('Реестровое имя',data.get('name'))
        if data.get('startAddress') and data.get('endAddress'):
            add('Регистрационный диапазон',str(data['startAddress'])+' — '+str(data['endAddress']))
            from .network_semantics import registration_match
            try:match=data.get('registration_match') or registration_match(resource,data)
            except (ValueError,TypeError):match=None
            if isinstance(match,dict):
                add('Возвращённые RDAP-префиксы',match.get('returned_prefixes'))
                add('Соответствие RDAP запросу',{'matched_parent':'Возвращён родительский диапазон; это не точный запрошенный префикс',
                    'matched_subrange':'Возвращена часть запрошенного диапазона','matched_exact':'Точное совпадение диапазона',
                    'containing_range':'Возвращён реестровый диапазон, содержащий IP','overlap':'Диапазоны пересекаются частично',
                    'mismatch':'Ответ не соответствует запрошенному диапазону'}.get(match.get('match_type')))
        add('Страна регистрации',data.get('country'))
        for entity in data.get('registry_entities',[]) if isinstance(data.get('registry_entities'),list) else []:
            if not isinstance(entity,dict):continue
            from .network_semantics import registry_entity_type
            kind=registry_entity_type(entity)
            roles=entity.get('roles');roles=roles if isinstance(roles,list) else []
            if kind=='organization' and 'registrant' in roles:add('Организация-регистрант реестрового объекта',entity.get('name'))
            elif kind=='maintainer':add('Реестровый maintainer',entity.get('handle') or entity.get('name'))
            elif kind=='registry_authority':add('Администратор реестра / RIR',entity.get('name'))
            elif kind=='registry_reference':add('Ссылка на объект реестра',entity.get('name'))
            elif kind=='registry_contact':add('Контакт реестрового объекта',entity.get('name'))
        geo=data.get('geoip')
        if isinstance(geo,dict):
            for label,field in (('Страна','country_name'),('Регион','region'),('Город','city')):add('GeoIP · '+label,geo.get(field))
            if type(geo.get('latitude')) in (int,float) and type(geo.get('longitude')) in (int,float):
                add('GeoIP · приблизительная точка',f"{geo['latitude']:.2f}, {geo['longitude']:.2f}; радиус точности не предоставлен")
            add('GeoIP · квалификация','Оценка базы по IP; не физическое местоположение человека/устройства и не страна регистрации')
        add('BGP-префикс',data.get('prefix'))
        for asn in data.get('asns',[]) if isinstance(data.get('asns'),list) else []:
            if isinstance(asn,(str,int)):add('Origin ASN','AS'+str(asn).removeprefix('AS'))
        nested=data.get('data')
        if isinstance(nested,dict):
            add('BGP-префикс',nested.get('prefix'))
            add('Название AS',nested.get('holder'))
            for asn in nested.get('asns',[]) if isinstance(nested.get('asns'),list) else []:
                if isinstance(asn,dict):
                    if asn.get('asn'):add('Origin ASN','AS'+str(asn['asn']))
                    add('Название AS',asn.get('holder'))
            if data.get('dataset')=='routing-history' and isinstance(nested.get('by_origin'),list):
                for observation in nested['by_origin'][:10]:
                    if isinstance(observation,dict):
                        for prefix in observation.get('prefixes',[])[:10] if isinstance(observation.get('prefixes'),list) else []:
                            if not isinstance(prefix,dict):continue
                            timelines=prefix.get('timelines',[])
                            if not isinstance(timelines,list):continue
                            starts=[v['starttime'] for v in timelines if isinstance(v,dict) and isinstance(v.get('starttime'),str)]
                            ends=[v['endtime'] for v in timelines if isinstance(v,dict) and isinstance(v.get('endtime'),str)]
                            add('История маршрутов','AS'+str(observation.get('origin','?'))+' · '+str(prefix.get('prefix','?'))+
                                (' · окно '+min(starts)+' — '+max(ends)+' UTC' if starts and ends else '')+'; интервалов наблюдения: '+str(len(timelines)))
            if data.get('dataset')=='routing-status':
                last=nested.get('last_seen')
                if isinstance(last,dict):add('Последний BGP-снимок',str(last.get('time') or 'дата неизвестна')+' UTC · '+str(last.get('prefix') or '')+' · AS'+str(last.get('origin') or '?'))
                visibility=nested.get('visibility')
                if isinstance(visibility,dict):
                    for family,value in visibility.items():
                        if isinstance(value,dict) and type(value.get('total_ris_peers')) is int and value['total_ris_peers']>0:
                            add('Видимость '+str(family).upper(),str(value.get('ris_peers_seeing','?'))+' из '+str(value['total_ris_peers'])+' RIS-пиров')
        answers=data.get('answers')
        if isinstance(answers,list):
            for answer in answers[:30]:
                if not isinstance(answer,dict):continue
                record_type='PTR' if data.get('record_type')=='PTR' else {1:'A',2:'NS',5:'CNAME',6:'SOA',15:'MX',16:'TXT',28:'AAAA',257:'CAA'}.get(answer.get('type'),data.get('query_type','DNS'))
                add(record_type+(' · DMARC' if str(data.get('query_name','')).startswith('_dmarc.') else ''),answer.get('value',answer.get('data')))
            if not answers and type(data.get('response_code')) is int:
                add('DNS '+str(data.get('record_type') or data.get('query_type')), 'NXDOMAIN' if data['response_code']==3 else 'Нет записей; код ответа '+str(data['response_code']))
        if data.get('record_type') and data.get('value'):add('DNS '+str(data['record_type']),data['value'])
        if type(data.get('matched')) is bool:
            label='Spamhaus DROP' if row.get('platform')=='spamhaus_drop' else 'Feodo Tracker'
            add(label,'Найдено совпадение в опубликованном наборе' if data['matched'] else 'Совпадений в проверенном наборе нет; безопасность не установлена')
        if isinstance(data.get('observed_names'),list):add('Имена в CT (исторические)',data['observed_names'])
        if data.get('objectClassName')=='domain':
            add('RDAP-статус',data.get('status'));add('NS по реестру',data.get('nameservers'))
        for event in data.get('events',[]) if isinstance(data.get('events'),list) else []:
            if isinstance(event,dict):add('RDAP · '+{'registration':'Регистрация','last changed':'Изменение','expiration':'Истечение','last update of RDAP database':'Обновление базы'}.get(event.get('eventAction'),'Событие реестра'),event.get('eventDate'))
    for profile in result.values():
        by_label=defaultdict(set)
        for fact in profile['facts']:by_label[fact['label']].add(str(fact['value']))
        # Only genuinely single-valued registration fields; multiple ASN/DNS
        # observations are normal and are never called ownership conflicts.
        profile['conflicts']=[{'field':label,'values':sorted(values)} for label,values in by_label.items()
            if label in ('Реестровое имя','Страна регистрации','Регистрационный диапазон','GeoIP · Страна','GeoIP · Город','GeoIP · Регион') and len(values)>1]
    return [p for p in result.values() if p['facts']]


def markdown(items):
    lines=[]
    def cell(value):return re.sub(r'\s+',' ',str(value)).replace('|','\\|')
    for profile in items:
        lines += ['### '+('Доменный профиль' if profile['kind']=='domain' else 'Сетевой профиль')+' · '+profile['resource'],
            '', '| Наблюдение | Значение | Источник |', '| --- | --- | --- |']
        for fact in profile['facts']:
            origins=fact.get('sources') or [{'url':fact.get('url')}]
            urls=list(dict.fromkeys(origin.get('url') for origin in origins if isinstance(origin,dict) and isinstance(origin.get('url'),str) and origin['url'].startswith(('http://','https://'))))
            link=', '.join('[Источник'+(' '+str(index+1) if len(urls)>1 else '')+']('+url+')' for index,url in enumerate(urls)) or 'Сохранённое наблюдение'
            lines.append('| '+cell(fact['label'])+' | '+cell(fact['value'])+' | '+link+' |')
        for conflict in profile['conflicts']:
            lines += ['', '**Расхождение источников:** '+cell(conflict['field'])+' — '+'; '.join(cell(v) for v in conflict['values'])+'. Даты и источники сохранены; причина требует проверки.']
        lines += ['', 'Регистрация диапазона, оператор сервиса и пользователь устройства — разные сущности. IP-данные не устанавливают физическое местонахождение человека.', '']
    return '\n'.join(lines)
