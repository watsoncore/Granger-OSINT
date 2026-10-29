"""Descriptions distinguish implementations, local readiness and real executions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class ToolManifest:
    id: str
    name: str
    category: str
    description: str
    accepted_inputs: tuple[str,...]
    output_schema: dict
    access_mode: str
    auth_requirements: tuple[str,...]
    required_permissions: tuple[str,...]
    network_requirements: str
    rate_limit_policy: str
    capabilities: tuple[str,...]
    source_url: str
    documentation_url: str
    adapter_version: str = '1.0'

    def to_dict(self): return asdict(self)


OFFICIAL = {
 'maigret':('https://github.com/soxoj/maigret','LOCAL_CLI'),
 'blackbird':('https://github.com/p1ngul1n0/blackbird','LOCAL_CLI'),
 'snoop':('https://github.com/snooppr/snoop','LOCAL_CLI'),
 'social_analyzer':('https://github.com/qeeqbox/social-analyzer','LOCAL_CLI'),
 'holehe':('https://github.com/megadose/holehe','LOCAL_CLI'),
 'phoneinfoga':('https://github.com/sundowndev/phoneinfoga','LOCAL_CLI'),
 'blockchain':('https://github.com/watsoncore/Granger-OSINT','OFFICIAL_API'),
 'wayback':('https://archive.org/help/wayback_api.php','OFFICIAL_API'),
 'telegram':('https://core.telegram.org/api','OFFICIAL_API'),
 'vk':('https://dev.vk.com/ru/method/users.get','OFFICIAL_API'),
 'instagram':('https://instaloader.github.io/','LOCAL_CLI'),
 'web_search':('https://developers.google.com/custom-search/v1/overview','OFFICIAL_API'),
 'web_read':('https://developer.mozilla.org/en-US/docs/Web/HTTP','PERMITTED_HTTP'),
 'domain_lookup':('https://developers.google.com/speed/public-dns/docs/doh/json','OFFICIAL_API'),
 'ip_lookup':('https://stat.ripe.net/docs/data-api/api-endpoints/network-info','OFFICIAL_API'),
 'evidence_get':('https://github.com/watsoncore/Granger-OSINT','LOCAL_CLI'),
 'github_repository':('https://docs.github.com/en/rest/repos/repos#get-a-repository','OFFICIAL_API'),
 'threat_feodo':('https://feodotracker.abuse.ch/blocklist/','OPEN_DATASET'),
 'hash_virustotal':('https://docs.virustotal.com/reference/file-info','OFFICIAL_API'),
 'image_metadata':('https://pillow.readthedocs.io/en/stable/','LOCAL_CLI'),
 'image_ocr':('https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html','LOCAL_CLI'),
 'image_compare':('https://pillow.readthedocs.io/en/stable/','LOCAL_CLI'),
 'map_overpass':('https://wiki.openstreetmap.org/wiki/Overpass_API','OFFICIAL_API'),
 'map_wikimedia':('https://www.mediawiki.org/wiki/Extension:GeoData#API','OFFICIAL_API'),
 'map_geocode':('https://nominatim.org/release-docs/latest/api/Search/','OFFICIAL_API'),
}


def manifest(spec):
    url,mode=OFFICIAL.get(spec.source,('https://github.com/watsoncore/Granger-OSINT','LOCAL_CLI'))
    auth={'telegram':('telegram_api_hash','telegram_session'),'vk':('vk_token',),
          'hash_virustotal':('virustotal_api_key',),'instagram':('instagram_session',)}.get(spec.source,())
    category=('geoint' if spec.kind in ('image','coordinates') else 'threat_intelligence' if spec.kind=='hash' or spec.source=='threat_feodo'
              else 'infrastructure' if spec.kind in ('domain','ip','repository') else 'archives' if spec.source=='wayback'
              else 'blockchain' if spec.kind=='blockchain' else 'web' if spec.kind in ('web','dork','evidence') else 'socmint')
    return ToolManifest(spec.name,spec.name,category,spec.description,(spec.kind,),
        {'type':'object','required':['invocation_id','tool_id','status','started_at','finished_at','data','evidence_ids','warnings','errors']},
        mode,auth,('explicit_user_approval',) if spec.requires_approval else ('public_read_only',),
        'none' if spec.kind in ('image','evidence') else 'public HTTPS',
        ('Local processing; no network requests.' if spec.kind in ('image','evidence') else
         'Public integrations share two worker slots; per-service rate gates and a five-minute cache.'
         if spec.source in ('github_repository','threat_feodo','hash_virustotal') else
         'Mapping clients share a per-service rate gate and bounded cache.'
         if spec.kind=='coordinates' or spec.source=='map_geocode' else
         'Adapter/provider-specific limits; no shared cross-adapter concurrency guarantee.'),
        (spec.name,),url,url)


def technical_state(row):
    if row.get('state')=='disabled': return 'disabled'
    state=row.get('state')
    if state in ('auth_required','authentication_required'): return 'authentication_required'
    if state in ('not_installed','missing_runtime','missing_dependency'): return 'not_installed'
    if state in ('error','failed'): return 'failed'
    if state in ('blocked','timeout','rate_limited'): return 'temporarily_unavailable'
    last=row.get('last_execution') or {}
    if row.get('available') and last.get('status') in ('complete','completed','empty'): return 'live_verified'
    if row.get('available'): return 'ready_local'
    return 'configuration_required'


def relevant_names(specs, task):
    """A compact candidate set, without granting any additional execution rights."""
    if not task: return {s.name for s in specs}
    text=task.casefold()
    kinds={'dork','web','evidence'}
    if re.search(r'img_[a-f0-9]{64}|фото|изображени|картинк|exif|ocr|geoint|геолокац',text): kinds.update(('image','coordinates'))
    if re.search(r'ник|username|профил|аккаунт|пользовател',text): kinds.add('username')
    if re.search(r'email|e-mail|почт|[\w.+-]+@[\w.-]+',text): kinds.add('email')
    if re.search(r'телефон|phone|\+\d{8}',text): kinds.add('phone')
    if re.search(r'telegram|телеграм|t\.me/',text): kinds.add('telegram')
    if re.search(r'\bvk\b|вконтакте|vk\.(?:com|ru)',text): kinds.add('vk')
    if re.search(r'instagram|инстаграм',text): kinds.add('instagram')
    if re.search(r'блокчейн|кошел[её]к|blockchain|0x[a-f0-9]{40}',text): kinds.add('blockchain')
    if re.search(r'домен|dns|rdap|domain|сертификат|инфраструкт',text): kinds.add('domain')
    if re.search(r'\bip\b|asn|\d{1,3}(?:\.\d{1,3}){3}|инфраструкт',text): kinds.add('ip')
    if re.search(r'github|репозитор|repository',text): kinds.add('repository')
    if re.search(r'sha.?256|х[еэ]ш|hash|virustotal',text): kinds.add('hash')
    return {s.name for s in specs if s.kind in kinds}
