"""Standalone public-only browser policy, also imported by the isolated worker."""
import ipaddress
import re
import socket
from urllib.parse import parse_qsl,unquote,urlsplit,urlunsplit

SENSITIVE=re.compile(r'(?i)api.?key|token|password|passwd|session|cookie|secret|credential|authorization')
STATEFUL=re.compile(r'(?i)(?:^|/)(?:login|signin|logout|signout|delete|remove|checkout|purchase|payment|publish|upload|oauth|reset-password)(?:/|$)')


def public_address(value):
    try: address=ipaddress.ip_address(value)
    except ValueError:return False
    return (address.is_global and not any((address.is_private,address.is_loopback,address.is_link_local,
        address.is_reserved,address.is_multicast,address.is_unspecified)) and
        not (isinstance(address,ipaddress.IPv6Address) and (address.ipv4_mapped or address.teredo or address.sixtofour)))


def public_url(value):
    if not isinstance(value,str) or not 1<=len(value)<=2000 or any(ord(c)<33 for c in value) or '\\' in value:raise ValueError('unsafe_url')
    p=urlsplit(value)
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:raise ValueError('unsafe_url')
    host=p.hostname.rstrip('.').encode('idna').decode().lower()
    decoded=unquote(p.path+'?'+p.query)
    if any(ord(c)<32 or ord(c)==127 for c in decoded):raise ValueError('encoded_control_disabled')
    if host=='localhost' or host.endswith(('.local','.localhost','.internal','.test','.invalid','.onion','.home.arpa')):raise ValueError('non_public_host')
    if '%' in host or p.port not in (None,443 if p.scheme=='https' else 80):raise ValueError('unsafe_port')
    try:ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host or len(host)>253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.')):raise ValueError('invalid_host')
    else:
        if not public_address(host):raise ValueError('private_address')
    if STATEFUL.search(unquote(p.path)):raise ValueError('consequential_navigation_disabled')
    if any(SENSITIVE.search(key) for key,_ in parse_qsl(p.query,keep_blank_values=True)):raise ValueError('sensitive_query_disabled')
    if host=='api.proxynova.com' and unquote(p.path).startswith('/comb'):raise ValueError('restricted_source')
    if host in ('looka.one','www.looka.one') and unquote(p.path).startswith('/vk_user/'):raise ValueError('restricted_source')
    return urlunsplit((p.scheme,'['+host+']' if ':' in host else host,p.path or '/',p.query,''))


def public_endpoint(host,port):
    public_url(('https://' if port==443 else 'http://')+('['+host+']' if ':' in host else host))
    rows=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(row[4][0] for row in rows))
    if not addresses or any(not public_address(address) for address in addresses):raise ValueError('private_or_rebound_dns')
    # Literal connect pins the validated address; no second hostname lookup.
    return addresses[0]


def search_text(value):
    if (not isinstance(value,str) or not 1<=len(value)<=300 or any(ord(c)<32 for c in value)
            or re.search(r'(?i)\b(?:sk-[a-z0-9_-]{20,}|AIza[a-z0-9_-]{25,}|bearer\s+\S+)',value)):
        raise ValueError('unsafe_search_text')
    return value


# Public, read-only search operations reviewed by endpoint. A page cannot
# nominate its own POST handler, add hidden fields, or authorize a write.
SEARCH_POST_ENDPOINTS = {
    'https://www.ebi.ac.uk/europepmc/webservices/rest/searchPOST': 'query',
    'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi': 'term',
}


def search_post_destination(page_url, action):
    endpoint = public_url(action)
    if urlsplit(public_url(page_url)).netloc != urlsplit(endpoint).netloc or endpoint not in SEARCH_POST_ENDPOINTS:
        raise ValueError('unreviewed_search_form')
    return endpoint


def validate_search_post(page_url, action, content_type, body, entered):
    endpoint = search_post_destination(page_url, action)
    field = SEARCH_POST_ENDPOINTS[endpoint]
    if content_type.split(';')[0].strip().lower() != 'application/x-www-form-urlencoded':
        raise ValueError('unsafe_search_encoding')
    if not isinstance(body, str) or len(body) > 2200:
        raise ValueError('unsafe_search_fields')
    pairs = parse_qsl(body, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
    fields = dict(pairs)
    if len(fields) != len(pairs) or fields.get(field) != search_text(entered):
        raise ValueError('search_terms_changed')
    options = {'format': {'json','xml'}, 'pageSize': {'1','5','10'}} if field=='query' else {
        'db': {'pubmed','pmc'}, 'retmode': {'json','xml'}, 'retmax': {'1','5','10'}}
    if any(k != field and v not in options.get(k, set()) for k,v in pairs):
        raise ValueError('unsafe_search_fields')
    return endpoint
