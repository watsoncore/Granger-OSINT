"""One typed-node target contract shared by discovery and execution."""
import ipaddress
import re
from .crypto_targets import node_gansar_capability,CHAIN_OPTIONS

_KINDS={'username':{'username'},'nickname':{'username'},'email':{'email'},'phone':{'phone'},
    'ip':{'ip'},'domain':{'domain','web'},'website':{'web'},'image':{'image'},
    'blockchain_address':{'blockchain'},'contract':{'blockchain'},'nft_asset':{'blockchain'},
    'nft':{'blockchain'},'collection':{'blockchain'},'organization':{'dork'},'coordinate':{'coordinates'}}

def target_value(node,spec):
    attrs=node.get('attributes',{});kind=node.get('type');kinds=set(_KINDS.get(kind,set()))
    if kind=='infrastructure_asset' and attrs.get('asset_type') in ('ip','ipv4','ipv6','network_range','autonomous_system'):kinds={'ip','network'}
    if kind in ('public_profile','social_profile','github_profile'):
        kinds={'web','username'}
        if attrs.get('platform') in ('telegram','vk','tiktok','instagram','github','steam'):kinds.add(attrs['platform'])
    if spec.kind not in kinds:return None,'unsupported_entity','Инструмент не принимает этот тип объекта.'
    if spec.kind=='coordinates':
        if spec.name=='map_geocode':return None,'unsupported_entity','Геокодер принимает топоним; для координат выберите поиск рядом с точкой.'
        value=attrs.get('coordinates') or attrs.get('value')
    elif spec.kind=='image':value=attrs.get('attachment_id')
    elif spec.kind=='web':value=attrs.get('url') or ('https://'+str(attrs.get('value')) if kind=='domain' and attrs.get('value') else None)
    elif spec.kind=='username':value=attrs.get('username') or (attrs.get('value') if kind in ('username','nickname') or not attrs.get('url') else None)
    else:value=attrs.get(spec.argument) or attrs.get('value') or attrs.get('address')
    if not isinstance(value,str) or not value.strip():return None,'invalid_target','У объекта нет машинного идентификатора для этого инструмента.'
    value=value.strip()
    try:
        if spec.kind=='username':
            value=value.removeprefix('@')
            if not re.fullmatch(r'[\w.-]{1,64}',value):raise ValueError()
        elif spec.kind=='ip':
            if value.upper().startswith('AS') and spec.name in ('network_rdap','network_routing'):pass
            elif '/' in value and spec.name in ('network_rdap','network_routing'):ipaddress.ip_network(value,strict=False)
            else:ipaddress.ip_address(value)
        elif spec.kind=='email':
            from .engine.router import normalize_email
            value=normalize_email(value)
        elif spec.kind=='phone':
            from .engine.router import normalize_phone
            value=normalize_phone(value)
        elif spec.kind=='domain':
            from .engine.router import _domain
            value=_domain(value)
        elif spec.kind=='web':
            from .engine.router import _url
            value=_url(value)[2]
        elif spec.kind=='image' and not re.fullmatch(r'img_[a-f0-9]{64}',value):raise ValueError()
        elif spec.kind=='coordinates':
            from .entity_router import route
            target=route(value)
            if not target or target.entity_type!='geographic_coordinates':raise ValueError()
            value=target.identifier
    except (ValueError,TypeError):return None,'invalid_target','Машинное значение объекта не соответствует формату инструмента.'
    return value,'ready','Тип и машинный идентификатор совместимы.'

def capabilities(node,chain='auto',availability=None):
    from .agent_tools import _SPECS
    from .tool_manifest import manifest
    crypto=node_gansar_capability(node,chain);tools=[]
    states={row.get('id',row.get('name')):row for row in (availability or [])}
    for spec in _SPECS:
        arguments=None
        if spec.name=='blockchain_gansar':
            compatible=crypto['compatible'];status='configuration_required' if compatible and crypto['requires_network'] else 'ready' if compatible else 'unsupported_entity' if crypto.get('error_code')=='incompatible_node_type' else 'invalid_target'
            reason=crypto['reason'] or ('Выберите EVM-сеть.' if crypto['requires_network'] else 'Поддерживаемый криптографический идентификатор.')
            if compatible:arguments={'address':crypto['canonical_address'],'chain':crypto['chain'] if not crypto['requires_network'] else 'auto','operation':'profile'}
        else:
            value,status,reason=target_value(node,spec);compatible=value is not None
            if compatible:
                if spec.name=='map_panoramax':
                    latitude,longitude=map(float,value.split(','));arguments={'latitude':latitude,'longitude':longitude}
                else:arguments={spec.argument:value}
        state=states.get(spec.name,{});available=state.get('available')
        if compatible and available is False:
            status='temporarily_unavailable' if state.get('state') in ('timeout','error','rate_limited','blocked') else 'runtime_unavailable'
            reason=state.get('reason') or 'Необходимый runtime недоступен.'
        required=[field for field in (spec.input_schema or {}).get('required',[]) if field not in (arguments or {})]
        if status=='ready' and required:status='configuration_required';reason='Заполните обязательные параметры инструмента.'
        tools.append({'id':spec.name,'category':manifest(spec).category,'compatible':compatible,'status':status,
            'available':available,'reason':reason,'required_parameters':required,'accepted_kind':spec.kind,
            'target_parameter':spec.argument,**({'arguments':arguments} if arguments else {})})
    return {**crypto,'chains':list(CHAIN_OPTIONS),'tools':tools}

def execution_payload(node,payload):
    """Bind user-selected options to the server-owned node, never to its label."""
    from .agent_tools import _SPECS
    spec=next((s for s in _SPECS if s.name==payload.get('tool')),None)
    if spec is None:raise ValueError('Инструмент не зарегистрирован.')
    supplied=payload.get('arguments') or {}
    if not isinstance(supplied,dict):raise ValueError('Некорректные параметры инструмента.')
    item=next(row for row in capabilities(node,supplied.get('chain','auto'))['tools'] if row['id']==spec.name)
    if not item['compatible']:raise ValueError(item['reason'])
    target=item['arguments'][spec.argument]
    if spec.name=='map_panoramax' and 'longitude' in supplied and supplied['longitude']!=item['arguments']['longitude']:
        raise ValueError('Координаты инструмента отличаются от выбранного объекта.')
    if spec.argument in supplied and supplied[spec.argument]!=target:
        raise ValueError('Машинная цель инструмента отличается от выбранного объекта. Выберите объект заново.')
    result={**payload,'query':target}
    if spec.input_schema is not None:
        result['arguments']={**item['arguments'],**supplied,spec.argument:target}
        if spec.name=='blockchain_gansar':
            from .crypto_targets import validate_gansar_arguments
            result['arguments']=validate_gansar_arguments(result['arguments'])
    else:result.pop('arguments',None)
    return result
