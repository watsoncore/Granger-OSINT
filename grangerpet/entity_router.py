"""Deterministic investigation targets; recognition never asserts ownership."""
from dataclasses import dataclass, field, asdict
import hashlib
import ipaddress
import math
import re
from urllib.parse import urlsplit

from .engine.models import canonical_url
from .engine.router import normalize_email, normalize_phone, _domain, _platform
from .validators.ton_address import parse_ton_address


@dataclass(frozen=True)
class Target:
    entity_type: str
    identifier: str
    platform: str = ''
    canonical_url: str = ''
    properties: dict = field(default_factory=dict)
    tools: tuple = ()
    def to_dict(self):
        value = asdict(self)
        value['id'] = 'target_' + hashlib.sha256((self.entity_type + '|' + self.platform + '|' + self.identifier).encode()).hexdigest()[:24]
        return value


def route(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        return None
    value = value.strip()
    if re.fullmatch(r'img_[a-f0-9]{64}', value):
        return Target('image', value, properties={'attachment_id': value},
            tools=('visual_geoint', 'image_metadata', 'image_ocr', 'geoclip_predict', 'waypoint_predict'))
    match = re.fullmatch(r'\s*([+-]?\d{1,3}(?:\.\d+)?)\s*,\s*([+-]?\d{1,3}(?:\.\d+)?)\s*', value)
    if match:
        lat, lon = map(float, match.groups())
        if math.isfinite(lat + lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return Target('geographic_coordinates', f'{lat},{lon}', properties={'latitude': lat, 'longitude': lon},
                tools=('map_overpass', 'map_wikimedia', 'map_panoramax'))
        return None
    try:
        ip = ipaddress.ip_address(value)
        return Target('infrastructure_asset', str(ip), 'ip', properties={'public': ip.is_global},
                      tools=('ip_lookup', 'threat_feodo') if ip.is_global else ())
    except ValueError:
        pass
    ton = parse_ton_address(value)
    if ton:
        return Target('blockchain_address', ton['raw'], 'ton', properties={'test_only': bool(ton.get('test_only')), 'original': value},
            tools=() if ton.get('test_only') else ('blockchain_gansar',))
    if len(value) == 48 and value.startswith(('EQ', 'UQ', 'Ef', 'Uf', 'kQ', '0Q', 'kf', '0f')):
        return Target('blockchain_address', value, 'ton', properties={'validation_error': 'invalid_checksum_or_tag'}, tools=())
    if re.fullmatch(r'0x[0-9a-fA-F]{40}', value):
        return Target('blockchain_address', value, 'evm', tools=('blockchain_gansar',))
    if re.fullmatch(r'(?:bc1|[13])[a-zA-Z0-9]{25,90}|T[1-9A-HJ-NP-Za-km-z]{33}|[1-9A-HJ-NP-Za-km-z]{32,44}', value):
        return Target('blockchain_address', value, properties={'network_validation_pending': True}, tools=('blockchain_gansar',))
    if '@' in value and not value.startswith('@') and '://' not in value:
        try:
            email = normalize_email(value)
            return Target('email', email, properties={'domain': email.rsplit('@', 1)[1]}, tools=('mail_dns', 'email_holehe'))
        except ValueError:
            return None
    if value.startswith(('+', '00')) and re.fullmatch(r'[+\d ()-]{8,27}', value):
        try:
            return Target('phone', normalize_phone(value), tools=('phone_metadata',))
        except ValueError:
            return None
    if re.match(r'^(?:https?://|(?:www\.)?(?:t\.me|telegram\.me|github\.com|x\.com|twitter\.com|vk\.com|instagram\.com)/)', value, re.I):
        url = canonical_url(value if '://' in value else 'https://' + value)
        if not url:
            return None
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        parts = [p for p in parsed.path.split('/') if p]
        if host == 't.me':
            try:
                target_url = _platform(url, 'telegram')
            except ValueError:
                return None
            parts = [p for p in urlsplit(target_url).path.split('/') if p]
            return Target('public_post' if len(parts) == 2 else 'public_channel_or_profile',
                parts[0], 'telegram', target_url, {'username': parts[0], 'object_type_verified': False},
                ('telegram_public', 'web_read', 'web_archive'))
        if host == 'github.com' and parts:
            if len(parts) >= 2:
                repository = parts[0] + '/' + parts[1]
                return Target('github_repository', repository, 'github', 'https://github.com/' + repository,
                    {'repository': repository, 'requested_url': url}, ('github_repository', 'web_read'))
            return Target('github_profile', parts[0], 'github', 'https://github.com/' + parts[0],
                {'username': parts[0]}, ('github_profile', 'web_read'))
        if host == 'x.com' and parts:
            return Target('public_post' if len(parts) >= 3 and parts[1] == 'status' else 'social_profile',
                parts[0], 'x', url, {'username': parts[0]}, ('x_post', 'web_read') if len(parts) >= 3 and parts[1] == 'status' else ('x_profile', 'web_read'))
        if host in ('etherscan.io', 'tonviewer.com', 'tonscan.org') and parts and any(p in ('tx', 'transaction') for p in parts):
            return Target('blockchain_transaction', parts[-1], host, url,
                {'api_transaction_support': False}, ('web_read',))
        if host in ('vk.com', 'instagram.com', 'www.instagram.com', 'reddit.com', 'www.reddit.com') and parts:
            platform = 'vk' if host == 'vk.com' else 'instagram' if 'instagram' in host else 'reddit'
            return Target('social_profile', parts[0], platform, url,
                {'username': parts[0], 'identity_verified': False}, ((platform + '_public', 'web_read') if platform != 'reddit' else ('arctic_posts', 'arctic_comments', 'web_read')))
        return Target('website', url, host, url, {'domain': host}, ('web_read', 'web_archive', 'domain_lookup'))
    if '.' in value and not any(c in value for c in ' /:@'):
        try:
            domain = _domain(value)
            if not domain.endswith(('.local', '.localhost', '.internal', '.invalid', '.test')):
                return Target('domain', domain, canonical_url='https://' + domain + '/', tools=('domain_lookup', 'historical_contacts', 'web_read'))
        except ValueError:
            pass
    if re.fullmatch(r'@?[\w.-]{1,64}', value, re.UNICODE):
        return Target('username', value.lstrip('@'), properties={'identity_verified': False, 'interpretation': 'candidate'},
            tools=('username_maigret', 'username_blackbird', 'username_social_analyzer', 'github_profile', 'x_profile'))
    if value.lower().startswith(('организация:', 'organization:')):
        return Target('organization', value.split(':', 1)[1].strip(), properties={'identity_verified': False}, tools=('web_search',))
    return None


def route_goal(text, attachments=()):
    """Only literal identifiers from the human goal or scoped attachments."""
    if not isinstance(text, str):
        return []
    values = [text.strip()] if len(text) <= 2000 else []
    values += [value.rstrip('.,;:!?\"\')') for value in re.findall(r'https?://[^\s<>]+', text)]
    values += re.findall(r'(?<![\w])(?:-?\d:[a-fA-F0-9]{64}|[A-Za-z0-9_-]{48}|0x[a-fA-F0-9]{40})(?![\w])', text)
    values += re.findall(r'img_[a-f0-9]{64}', text)
    values += re.findall(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', text)
    values += re.findall(r'(?<![\w./])@[A-Za-z][A-Za-z0-9_]{3,63}', text)
    values += re.findall(r'(?<![\d.])[+-]?\d{1,2}\.\d+\s*,\s*[+-]?\d{1,3}\.\d+(?![\d.])', text)
    values += [value for value in attachments if isinstance(value, str)]
    targets = {}
    for value in values:
        target = route(value)
        if target is not None:
            key = (target.entity_type, target.platform, target.identifier)
            targets[key] = target
        if len(targets) >= 12:
            break
    return list(targets.values())
