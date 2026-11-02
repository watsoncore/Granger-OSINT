"""Registration scopes and registry roles are not physical location or operator."""
import ipaddress
import re


def registry_entity_type(entity):
    if not isinstance(entity,dict):return 'unknown'
    declared=entity.get('entity_type')
    if declared in ('organization','registry_contact','maintainer','registry_authority','registry_reference'):return declared
    name=str(entity.get('name') or '');handle=str(entity.get('handle') or '')
    value=handle+' '+name
    if re.search(r'(?i)(?:\bMNT[-_]|[-_]MNT\b)',value):return 'maintainer'
    if re.search(r'(?i)ORG-NCC1-RIPE|RIPE.?NCC|RIPE Network Coordination Centre|American Registry for Internet Numbers|APNIC|LACNIC|AFRINIC',value):return 'registry_authority'
    if re.fullmatch(r'(?i)ORG-[A-Z0-9-]+',name):return 'registry_reference'
    if entity.get('vcard_kind')=='org' or entity.get('organization_name'):return 'organization'
    roles=entity.get('roles');roles=roles if isinstance(roles,list) else []
    return 'organization' if 'registrant' in roles else 'registry_contact'


def registration_match(resource,fields):
    if not fields.get('startAddress') or not fields.get('endAddress'):return None
    start,end=ipaddress.ip_address(fields['startAddress']),ipaddress.ip_address(fields['endAddress'])
    if start.version!=end.version or int(start)>int(end):raise ValueError('Invalid RDAP interval')
    requested=ipaddress.ip_network(resource,strict=False) if '/' in resource else ipaddress.ip_network(resource+('/32' if start.version==4 else '/128'))
    if requested.version!=start.version:raise ValueError('RDAP IP family mismatch')
    first,last=int(requested.network_address),int(requested.broadcast_address)
    exact=first==int(start) and last==int(end)
    contains=int(start)<=first<=last<=int(end)
    contained=first<=int(start)<=int(end)<=last
    overlap=max(first,int(start))<=min(last,int(end))
    kind='matched_exact' if exact else 'matched_parent' if contains and '/' in resource else 'containing_range' if contains else 'matched_subrange' if contained else 'overlap' if overlap else 'mismatch'
    return {'requested_resource':str(requested) if '/' in resource else resource,
        'returned_prefixes':[str(net) for net in ipaddress.summarize_address_range(start,end)],
        'match_type':kind,'covers_entire_requested_range':contains,'requested_prefix_is_returned_object':exact,
        'not_a_bgp_announcement':True}
