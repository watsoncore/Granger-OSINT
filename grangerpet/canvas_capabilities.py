"""Local typed-node compatibility; labels are never executable tool inputs."""
from .crypto_targets import node_gansar_capability,CHAIN_OPTIONS

_KINDS={
    'username':{'username'},'email':{'email'},'phone':{'phone'},'ip':{'ip'},
    'domain':{'domain'},'website':{'web'},'public_profile':{'web','telegram','vk','tiktok','instagram','github','username'},
    'social_profile':{'web','telegram','vk','tiktok','instagram','github','username'},
    'image':{'image'},'blockchain_address':{'blockchain'},'contract':{'blockchain'},
    'nft_asset':{'blockchain'},'nft':{'blockchain'},'collection':{'blockchain'},
}

def capabilities(node,chain='auto'):
    from .agent_tools import _SPECS
    attrs=node.get('attributes',{})
    kind=node.get('type')
    kinds=_KINDS.get(kind,set())
    if kind=='infrastructure_asset' and attrs.get('asset_type') in ('ip','ipv4','ipv6'):kinds={'ip'}
    crypto=node_gansar_capability(node,chain)
    tools=[]
    for spec in _SPECS:
        arguments=None
        if spec.name=='blockchain_gansar':
            compatible=crypto['compatible']
            reason=crypto['reason'] or ('Выберите EVM-сеть.' if crypto['requires_network'] else 'Поддерживаемый криптографический идентификатор.')
            if compatible:arguments={'address':crypto['canonical_address'],'chain':crypto['chain'] if not crypto['requires_network'] else 'auto','operation':'profile'}
        else:
            value=(attrs.get('attachment_id') if spec.kind=='image' else attrs.get('url') if spec.kind=='web' else attrs.get(spec.argument) or attrs.get('value') or attrs.get('address'))
            compatible=spec.kind in kinds and isinstance(value,str) and bool(value.strip())
            reason='Тип и машинный идентификатор совместимы.' if compatible else 'Инструмент не принимает этот тип объекта или у узла нет машинного идентификатора.'
            if compatible:arguments={spec.argument:value}
        tools.append({'id':spec.name,'compatible':compatible,'reason':reason,**({'arguments':arguments} if arguments else {})})
    return {**crypto,'chains':list(CHAIN_OPTIONS),'tools':tools}
