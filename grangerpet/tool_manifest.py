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
    execution_mode: str = ''
    input_schema: dict | None = None
    requires_external_key: bool = False
    requires_user_confirmation: bool = False
    supports_cancellation: bool = True
    supports_evidence: bool = True

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
    from .public_sources import SOURCES
    url,mode=OFFICIAL.get(spec.source,('https://github.com/watsoncore/Granger-OSINT','LOCAL_CLI'))
    if spec.source in SOURCES:url,mode=SOURCES[spec.source][2],'OFFICIAL_API'
    if spec.documentation_url:url=spec.documentation_url
    if spec.execution_mode=='PUBLIC_API_NO_KEY':mode='OFFICIAL_API'
    elif spec.execution_mode=='PERMITTED_HTTP_PARSER':mode='PERMITTED_HTTP'
    elif spec.execution_mode=='ISOLATED_PUBLIC_PARSER':mode='PERMITTED_HTTP'
    elif spec.execution_mode=='ISOLATED_PUBLIC_BROWSER':mode='PERMITTED_HTTP'
    elif spec.execution_mode in ('LOCAL_PYTHON','LOCAL_MODEL'):mode='LOCAL_CLI'
    auth={'telegram':('telegram_api_hash','telegram_session'),'vk':('vk_token',),
          'hash_virustotal':('virustotal_api_key',),'instagram':('instagram_session',)}.get(spec.source,())
    if spec.source=='research_v7':
        from .source_registry_v2 import SOURCES as research_sources
        source=research_sources.get(spec.name)
        auth=(source.auth_key,) if source and source.auth_key else ()
        mode='OFFICIAL_API'
        if source:url=source.documentation
    category=('geoint' if spec.kind in ('image','coordinates') else 'threat_intelligence' if spec.kind=='hash' or spec.source=='threat_feodo'
              else 'infrastructure' if spec.kind in ('domain','ip','repository') else 'archives' if spec.source=='wayback'
              else 'blockchain' if spec.kind=='blockchain' else 'web' if spec.kind in ('web','dork','evidence') else 'socmint')
    return ToolManifest(spec.name,spec.name,spec.category or category,spec.description,(spec.kind,),
        {'type':'object','required':['invocation_id','tool_id','status','started_at','finished_at','data','evidence_ids','warnings','errors']},
        mode,auth,('explicit_user_approval',) if spec.requires_approval else ('public_read_only',),
        'one explicitly approved public HTTP(S) origin' if spec.name=='nuclei_check' else
        'none' if spec.kind in ('image','evidence') or spec.execution_mode.startswith('LOCAL_') else 'public HTTPS',
        ('Local processing; no network requests.' if spec.kind in ('image','evidence') else
         'Public integrations share two worker slots; per-service rate gates and a five-minute cache.'
         if spec.source in ('github_repository','threat_feodo','hash_virustotal') or spec.source in SOURCES else
         'Mapping clients share a per-service rate gate and bounded cache.'
         if spec.kind=='coordinates' or spec.source=='map_geocode' else
         'Adapter/provider-specific limits; no shared cross-adapter concurrency guarantee.'),
        (spec.name,),url,url,execution_mode=spec.execution_mode or
            ('PUBLIC_API_NO_KEY' if mode=='OFFICIAL_API' and not auth else 'OPEN_DATASET' if mode=='OPEN_DATASET' else 'LOCAL_CLI' if mode=='LOCAL_CLI' else 'PERMITTED_HTTP_PARSER'),
        input_schema=spec.input_schema,requires_external_key=bool(auth),requires_user_confirmation=spec.requires_approval)


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


def relevant_names(specs, task, records=()):
    """A compact candidate set, without granting any additional execution rights."""
    legacy={'username_blackbird','username_social_analyzer','username_snoop'}
    if not task: return {s.name for s in specs}-legacy
    text=task.casefold()
    kinds={'dork','web','evidence'}
    if re.search(r'браузер|browser|динамич|\bDOM\b|кнопк|форм[ауы]|прокру|страниц|открой',task,re.I):kinds.add('browser')
    from .entity_router import route_goal, route
    targets = route_goal(task)
    if any(t.canonical_url for t in targets):kinds.add('browser')
    if any(target.entity_type != 'username' for target in targets):
        kinds.discard('dork')
    if re.search(r'img_[a-f0-9]{64}|фото|изображени|картинк|exif|ocr|geoint|геолокац',text): kinds.update(('image','coordinates'))
    if re.search(r'img_[a-f0-9]{64}|фото|изображени|geoclip|waypoint|geoint|геолокац',text):kinds.add('visual_geoint')
    if re.search(r'тень|тени|shadow|солнц|солнечн',text):kinds.add('geoint_geometry')
    if re.search(r'tiktok|тикток|хронолог|timestamp|время.*публикац',text):kinds.add('chronology')
    if re.search(r'tiktok|тикток',text):kinds.add('tiktok')
    if re.search(r'должност|иерарх|организац|classification|classify',text):kinds.add('social_analytics')
    if re.search(r'граф|связ|отношени|соседн|повторя|graph|relation|neighbor',text):kinds.add('graph')
    if re.search(r'\bx\b|\bx\.com/|twitter\.com/|тв[иu]т|tweet|твиттер',text):kinds.update(('x_post','username'))
    if re.search(r'reddit|реддит|subreddit|сабреддит|arctic',text):kinds.add('reddit')
    if re.search(r'nuclei|уязвим|разреш.*проверк.*безопас',text):kinds.add('active_security')
    if re.search(r'ник|username|профил|аккаунт|пользовател',text): kinds.add('username')
    if re.search(r'email|e-mail|почт|[\w.+-]+@[\w.-]+',text): kinds.add('email')
    if re.search(r'телефон|phone|\+\d{8}',text): kinds.add('phone')
    if re.search(r'telegram|телеграм|t\.me/',text): kinds.add('telegram')
    if re.search(r'\bvk\b|вконтакте|vk\.(?:com|ru)',text): kinds.add('vk')
    if re.search(r'instagram|инстаграм',text): kinds.add('instagram')
    if re.search(r'(?i)steam|стим',text):kinds.add('steam')
    if re.search(r'блокчейн|кошел[её]к|blockchain|0x[a-f0-9]{40}',text): kinds.add('blockchain')
    if re.search(r'домен|dns|rdap|domain|сертификат|инфраструкт',text): kinds.add('domain')
    if re.search(r'\bip\b|asn|\d{1,3}(?:\.\d{1,3}){3}|инфраструкт',text): kinds.add('ip')
    if re.search(r'github|репозитор|repository',text): kinds.add('repository')
    if re.search(r'sha.?256|х[еэ]ш|hash|virustotal',text): kinds.add('hash')
    selected = {s.name for s in specs if s.kind in kinds}
    if not re.search(r'blackbird|social.?analyzer|snoop|дополнительн.{0,30}(?:провер|инструмент)|расширенн.{0,25}поиск',text):selected.difference_update(legacy)
    selected.update(('web_search', 'web_read', 'web_archive', 'evidence_get', 'evidence_graph'))
    for target in targets:
        selected.update(target.tools)
    if re.search(r'github|репозитор|repository', text):
        selected.update(('github_profile', 'github_users', 'github_repositories', 'github_repository'))
    if re.search(r'wikipedia|википеди', text): selected.add('wikipedia_search')
    if re.search(r'hacker.?news|\bhn\b', text): selected.update(('hn_search', 'hn_profile'))
    if re.search(r'openlibrary|книг', text): selected.add('openlibrary_search')
    # Only observed URLs and actual extracted links can expand platform scope.
    for record in list(records)[-150:]:
        if not isinstance(record, dict): continue
        details = record.get('details') or {}
        urls = [record.get('url')]
        if isinstance(details, dict) and isinstance(details.get('links'), list):
            urls += [link.get('url') for link in details['links'][:40] if isinstance(link, dict)]
        for url in urls:
            target = route(url)
            if target: selected.update(target.tools)
    return selected & {s.name for s in specs}
