"""Public platform targets; URL structure is not identity or existence proof."""
import re
from urllib.parse import parse_qs,unquote,urlsplit


def _url(value,hosts):
    if not isinstance(value,str) or not 1<=len(value)<=2000 or any(ord(c)<33 for c in value):raise ValueError('Invalid public target')
    parsed=urlsplit(value if '://' in value else 'https://'+value)
    if (parsed.scheme not in ('https','http') or parsed.hostname not in hosts or parsed.username or parsed.password
            or parsed.port not in (None,443 if parsed.scheme=='https' else 80)):
        raise ValueError('Exact public platform URL required')
    return parsed


def vk(value):
    if isinstance(value,str) and '/' not in value:value='https://vk.com/'+value.lstrip('@')
    parsed=_url(value,{'vk.com','www.vk.com','m.vk.com','vk.ru','www.vk.ru','m.vk.ru'})
    parts=[unquote(part) for part in parsed.path.split('/') if part]
    if len(parts)!=1:raise ValueError('Exact public VK object required')
    identifier=parts[0]
    wall=parse_qs(parsed.query).get('w',[''])[0]
    if wall.startswith('wall'):identifier=wall
    post=re.fullmatch(r'wall(-?[1-9]\d*)_([1-9]\d*)',identifier)
    if post:
        return {'platform':'vk','kind':'post','identifier':identifier,'owner_id':post[1],
                'post_id':post[2],'canonical_url':'https://vk.com/'+identifier}
    if not re.fullmatch(r'[A-Za-z0-9_.]{1,64}',identifier) or identifier.casefold() in ('login','join','settings','im','feed','support'):
        raise ValueError('Public VK profile or community required')
    numeric=re.fullmatch(r'(id|club|public)([1-9]\d*)',identifier)
    return {'platform':'vk','kind':'community' if numeric and numeric[1]!='id' else 'profile',
            'identifier':identifier,'canonical_url':'https://vk.com/'+identifier,
            **({'profile_id':numeric[2]} if numeric and numeric[1]=='id' else
               {'community_id':numeric[2]} if numeric else {'screen_name':identifier})}


def tiktok(value):
    if isinstance(value,str) and re.fullmatch(r'@?[A-Za-z0-9_][A-Za-z0-9_.]{1,23}',value) and not value.lstrip('@').isdigit():
        value='https://www.tiktok.com/@'+value.lstrip('@')
    parsed=_url(value,{'tiktok.com','www.tiktok.com','m.tiktok.com'})
    match=re.fullmatch(r'/@([A-Za-z0-9_][A-Za-z0-9_.]{1,23})(?:/video/([1-9]\d{14,24}))?/?',unquote(parsed.path))
    if not match:raise ValueError('TikTok @username or full public video URL required; bare IDs are ambiguous')
    if match[1].endswith('.'):raise ValueError('TikTok username cannot end with a period')
    profile='https://www.tiktok.com/@'+match[1]
    return {'platform':'tiktok','kind':'video' if match[2] else 'profile','username':match[1],
            'canonical_url':profile+('/video/'+match[2] if match[2] else ''),'profile_url':profile,
            **({'video_id':match[2]} if match[2] else {})}
