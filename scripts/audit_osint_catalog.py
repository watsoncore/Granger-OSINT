"""Reproducible technical audit of supplied OSINT names, not an adapter installer.

Only explicit reviewed URLs are probed. Ambiguous names keep a null URL. A
landing-page GET and robots response never mean search automation is permitted.
The unavailable Start.me collection is not replaced with another page or export.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from grangerpet.agent_browser import public_url, resolve_public, PinnedTransport
CATALOG='https://start.me/p/L1rEYQ/osint4all'
UA='Granger-OSINT/3.1 (+https://github.com/watsoncore/Granger-OSINT)'
# Explicit official/repository addresses, individually inspected; never formed
# by interpolating a site name, guessing a TLD or converting a search title.
URLS={
0:'https://www.google.com/',1:'https://www.bing.com/',2:'https://yandex.com/',3:'https://duckduckgo.com/',4:'https://search.brave.com/',5:'https://www.startpage.com/',6:'https://www.mojeek.com/',7:'https://search.yahoo.com/',8:'https://www.baidu.com/',9:'https://www.qwant.com/',10:'https://docs.searxng.org/',11:'https://www.ecosia.org/',12:'https://www.dogpile.com/',13:'https://swisscows.com/',14:'https://developers.google.com/custom-search/v1/overview',15:'https://www.google.com/advanced_search',
16:'https://github.com/soxoj/maigret',17:'https://github.com/sherlock-project/sherlock',18:'https://github.com/qeeqbox/social-analyzer',19:'https://github.com/WebBreacher/WhatsMyName',20:'https://namechk.com/',21:'https://www.reddit.com/',22:'https://www.reddit.com/search/',24:'https://pushshift.io/',25:'https://docs.github.com/en/rest/users/users#get-a-user',26:'https://developers.tiktok.com/',27:'https://developers.google.com/youtube/v3',28:'https://steamcommunity.com/',29:'https://dev.twitch.tv/docs/api/',30:'https://docs.joinmastodon.org/methods/accounts/',31:'https://discord.com/developers/docs/intro',32:'https://core.telegram.org/api',33:'https://dev.vk.com/ru/reference',34:'https://developers.facebook.com/docs/',35:'https://developers.facebook.com/docs/instagram-platform/',36:'https://learn.microsoft.com/en-us/linkedin/',
37:'https://t.me/TelegagoBot',40:'https://search.buzz.im/',45:'https://github.com/TelegramDB/TelegramDB',47:'https://core.telegram.org/api',
48:'https://www.iana.org/assignments/rdap-dns/rdap-dns.xhtml',49:'https://www.icann.org/rdap',50:'https://developers.google.com/speed/public-dns/docs/doh/json',51:'https://docs.securitytrails.com/',52:'https://developer.shodan.io/api',53:'https://docs.censys.com/',54:'https://docs.greynoise.io/',55:'https://www.onyphe.io/',56:'https://viewdns.info/api/',57:'https://domainbigdata.com/',58:'https://domaincodex.com/',59:'https://dnslytics.com/api',60:'https://en.fofa.info/api',61:'https://docs.netlas.io/',62:'https://crt.sh/',63:'https://www.iana.org/assignments/rdap-dns/rdap-dns.xhtml',
64:'https://www.openstreetmap.org/',65:'https://dev.overpass-api.de/overpass-doc/en/preface/commons.html',66:'https://operations.osmfoundation.org/policies/nominatim/',67:'https://www.geonames.org/export/web-services.html',68:'https://www.mapillary.com/developer/api-documentation/',69:'https://www.mediawiki.org/wiki/Extension:GeoData',70:'https://www.geoseer.net/about.php',73:'https://data.apps.fao.org/map/catalog/',74:'https://developers.arcgis.com/rest/users-groups-and-items/search-reference/',
76:'https://developers.google.com/maps/documentation',77:'https://learn.microsoft.com/en-us/bingmaps/',78:'https://yandex.com/maps-api/',79:'https://www.openstreetmap.org/',80:'https://developer.mapquest.com/',81:'https://www.mapillary.com/developer/api-documentation/',82:'https://developers.google.com/waze',83:'https://www.geonames.org/export/web-services.html',85:'https://satellites.pro/',86:'https://api.windy.com/',87:'https://livingatlas.arcgis.com/',88:'https://firms.modaps.eosdis.nasa.gov/api/',
90:'https://archive.org/advancedsearch.php',91:'https://archive.org/help/wayback_api.php',92:'https://news.google.com/',93:'https://www.newslookup.com/',94:'https://www.newspapers.com/',95:'https://newspaperarchive.com/',97:'https://www.newsnow.com/',99:'https://www.mediawiki.org/wiki/API:Search',
101:'https://docs.virustotal.com/reference/overview',102:'https://otx.alienvault.com/',103:'https://www.fortiguard.com/',104:'https://talosintelligence.com/',105:'https://www.threatminer.org/api.php',106:'https://threatbutt.com/about',107:'https://urlhaus.abuse.ch/api/',108:'https://feodotracker.abuse.ch/blocklist/',
109:'https://data.gov/developers/apis/',110:'https://github.com/Kaggle/kaggle-api',111:'https://datasetsearch.research.google.com/',112:'https://help.opendatasoft.com/apis/ods-search-v2/',113:'https://dev.socrata.com/docs/other/discovery/',114:'https://apidocs.data.world/',115:'https://www.opensanctions.org/docs/api/',
122:'https://blockchair.com/api/docs',124:'https://github.com/watsoncore/Granger-OSINT',
126:'https://images.google.com/',127:'https://yandex.com/images/',128:'https://www.bing.com/images/',129:'https://fotoforensics.com/',130:'https://29a.ch/photo-forensics/',133:'https://github.com/watsoncore/Granger-OSINT',
134:'https://www.adsbexchange.com/data/',135:'https://www.flightaware.com/commercial/aeroapi/',136:'https://fr24api.flightradar24.com/docs',137:'https://www.planespotters.net/',138:'https://developers.skyscanner.net/',139:'https://www.radarbox.com/',
142:'https://github.com/yt-dlp/yt-dlp',147:'https://github.com/gchq/CyberChef',148:'https://github.com/laramies/theHarvester',149:'https://github.com/megadose/holehe',150:'https://github.com/sundowndev/phoneinfoga',
}
# Only reviewed primary contracts get an access verdict. Familiar brand names
# or an HTTP200 documentation landing page do not establish API permission.
API_FREE={25,48,50,63,65,66,69,90,91,99,108}
API_KEY={14,32,33,35,47,67,68,70,81,83,101,107}
LOCAL={16,17,18,19,124,130,133,142,147,148,149,150}
ADAPTERS={16:['username_maigret'],18:['username_social_analyzer'],25:['github_repository','github_profile','github_users','github_repositories'],32:['telegram_public'],33:['vk_public'],35:['instagram_public'],47:['telegram_public'],48:['domain_lookup'],50:['domain_lookup'],63:['domain_lookup'],64:['map_overpass','map_geocode'],65:['map_overpass'],66:['map_geocode'],69:['map_wikimedia'],79:['map_overpass','map_geocode'],91:['web_archive'],99:['wikipedia_search'],101:['hash_virustotal'],108:['threat_feodo'],124:['blockchain_gansar'],133:['image_metadata','image_ocr','image_compare'],149:['email_holehe'],150:['phone_metadata']}
NOTES={
3:'robots.txt disallows /html and /lite; these search endpoints are not automated. Manual site use is not a backend integration.',
10:'Open-source metasearch software, not one guaranteed public endpoint; each instance has its own permission and JSON policy.',
19:'A rule dataset is not a verified running adapter; adding hundreds of rules does not prove corresponding sites accessible.',
24:'Archive/service scope and current user access require verification; no unreviewed third-party Reddit archive is substituted.',
28:'Public Steam pages do not imply general permission or a working parser; no Steam profile parser shipped.',
30:'Federated service: permissions vary by instance and operation. No arbitrary-instance adapter shipped.',
37:'The actual official bot address was found, not an unauthenticated scraping API. No Telegram bot interaction or Google CSE automation.',
45:'Project/official documentation indicates Telegram/web account workflows; no account or private membership queries were made.',
58:'Indexed official page is a human-verification challenge; no challenge bypass.',
62:'Certificate-transparency candidate; actual endpoint schema, limits and permission not validated, no fake adapter.',
65:'Bounded default Overpass: fixed500m/20records/10s/1MiB query;1.1s gate,60 new requests/hour, cache and429/5xx backoff. No arbitraryQL.',
66:'Deliberate single-user integration only: individual end-user-triggered public place query,1.1s gate,30 new requests/hour/cache, attribution. No autocomplete orbulkgeocoding.',
67:"GeoNames requires the user's own enabled username. A demo account is not used.",
68:'Mapillary Graph API requires an access token. No fake public anonymous integration.',
70:'Official GeoSeer docs explicitly describe its API as paid; web-search permission and a parser are not established.',
88:'FIRMS API requires a MAP_KEY. Publicly visible maps do not establish anonymous API access.',
90:'Official advanced search API supports bounded public metadata search; copyrighted full content is not automatically downloaded.',
101:'Optional existing VirusTotal SHA256 report adapter uses a separately stored key; no file upload or rescan.',
105:'Documented ThreatMiner API candidate, not an implemented adapter; no livequery claimed.',
108:'A specific reviewed Feodo recommended C2 feed represents this otherwise generic direction; a negative match is not a safety verdict.',
115:'OpenSanctions dataset/API licensing and API key depend on use. Not automatically treated as an unrestricted freepersonsearch.',
124:'Existing Gansar localintegration retained; it does not imply every listed blockchain explorer has an adapter.',
130:'A local browser forensics tool, not a remote geolocation API; existing Granger local tools handle its own pixels.',
133:'Existing localEXIF/OCR/dHash operate on user-selected images; no semantic geolocation claims.',
142:'CLIproject inspected; yt-dlp is not installed or invoked by this update and no YouTube adapter is claimed.',
147:'Local transformation tool, not an OSINT source by itself; no arbitrary recipe execution added.',
}
class Title(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.parts=[]
 def handle_starttag(self,tag,attrs):self.active=tag.lower()=='title' or self.active
 def handle_endtag(self,tag):
  if tag.lower()=='title':self.active=False
 def handle_data(self,value):
  if self.active:self.parts.append(value)
def supplied_entries(path):
 text=path.read_text(encoding='utf-8')
 part=text.split('## 3.2.',1)[1].split('## 3.3.',1)[0];category='';rows=[]
 for line in part.splitlines():
  if line.startswith('### '):category=line[4:]
  elif line.startswith('- '):rows.append({'category':category,'name':line[2:].rstrip(';.')})
 if len(rows)!=153 or rows[0]['name']!='Google Search' or rows[-4]['name']!='Holehe':raise ValueError('This reviewed URL map belongs to the153-entry supplied request; do not apply to a different list.')
 return rows
async def request(url):
 try:
  url=public_url(url);parsed=urlsplit(url);port=443 if parsed.scheme=='https' else 80
  addresses=await resolve_public(parsed.hostname,port)
  async with httpx.AsyncClient(transport=PinnedTransport(parsed.hostname,port,addresses),headers={'User-Agent':UA,'Accept':'text/html,text/plain,application/json'},timeout=7,follow_redirects=False,trust_env=False) as c:
   async with c.stream('GET',url) as response:
    raw=bytearray()
    async for chunk in response.aiter_bytes(16384):
     raw.extend(chunk)
     if len(raw)>=200000:break
    text=bytes(raw).decode(response.encoding or 'utf-8','replace');title=Title();title.feed(text[:100000])
    return {'requested_url':url,'final_url':str(response.url),'http_status':response.status_code,'title':re.sub(r'\s+',' ',' '.join(title.parts))[:300],
     'sample_bytes':len(raw),'response_prefix_sha256':hashlib.sha256(raw).hexdigest(),'truncated':len(raw)>=200000,
     'location':response.headers.get('location'),'challenge':any(marker in text.casefold() for marker in ['cf-chl','just a moment','verify you are human','captcha','security verification'])}
 except Exception as error:return {'requested_url':url,'error_type':type(error).__name__,'error_code':getattr(error,'code',None)}
async def probe_urls(urls):
 gate=asyncio.Semaphore(5);rows={};domains={};next_request={}
 async def run(url):
  host=urlsplit(url).hostname
  async with domains.setdefault(host,asyncio.Lock()):
   delay=next_request.get(host,0)-asyncio.get_running_loop().time()
   if delay>0:await asyncio.sleep(delay)
   async with gate:
    rows[url]=await request(url)
    next_request[host]=asyncio.get_running_loop().time()+1.1
 await asyncio.gather(*(run(url) for url in sorted(set(urls))))
 return rows
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request-file',type=Path,required=True);parser.add_argument('--live',action='store_true');parser.add_argument('--probe-missing',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'docs/OSINT4ALL_AUDIT.json');args=parser.parse_args()
 rows=supplied_entries(args.request_file);existing={}
 if args.output.is_file():existing=json.loads(args.output.read_text(encoding='utf-8')).get('url_probes',{})
 probes=asyncio.run(probe_urls(URLS.values())) if args.live else existing
 if args.probe_missing:probes.update(asyncio.run(probe_urls(set(URLS.values())-set(probes))))
 probes={url:row for url,row in probes.items() if url in URLS.values()}
 for probe in probes.values():
  marker=probe.get('challenge_marker_present',probe.get('challenge',False))
  probe['challenge_marker_present']=marker
  title=probe.get('title','').casefold()
  probe['challenge']=any(word in title for word in ['just a moment','security verification','attention required','verify you are human','access denied','robot check']) or bool(probe.get('http_status')==403 and marker)
 from grangerpet.agent_tools import _SPECS
 installed={item.name:item for item in _SPECS};seen={}
 for i,row in enumerate(rows):
  url=URLS.get(i);probe=probes.get(url,{}) if url else {};names=[name for name in ADAPTERS.get(i,[]) if name in installed]
  duplicate=seen.get(url) if url else None
  if url:seen.setdefault(url,i)
  reason=NOTES.get(i,'Landing/documentation identification only. A permitted search operation, concrete selectors/schema and liveadapter result have not been established; excluded from autonomous registry.')
  if not url:reason='Supplied name/direction is ambiguous or no exact primary source URL was recovered from the blocked catalog. No URL was generated from its name; excluded pending identification.'
  if names:decision='existing_or_implemented_scoped_adapter';reason=NOTES.get(i,'Only the listed adapter operations are implemented; landingpage status does not verify the adapter. Other platform operations remain unsupported.')
  elif duplicate is not None:decision='duplicate_technical_entry'
  elif not url:decision='unresolved_source_or_direction'
  elif i in API_KEY:decision='optional_auth_or_paid_api_not_basic_search'
  elif i in LOCAL:decision='local_project_not_integrated'
  elif probe.get('challenge'):decision='blocked_or_challenge_no_bypass'
  else:decision='operation_permission_or_parser_not_verified'
  row.update(source_id=f'supplied_{i+1:03}',actual_url=url,domain=urlsplit(url).hostname if url else None,original_catalog_url=CATALOG,
   from_catalog=False,candidate_type='technical_candidate' if url else 'unresolved_name_or_direction',extraction_method='supplied_request_name + explicit official/repository address inspection' if url else 'supplied_request_name_only',
   access_type='local_project' if i in LOCAL else 'public_api_or_documentation' if i in API_FREE|API_KEY else 'public_website_or_unresolved',
   public_api_available='documented_no_personal_key' if i in API_FREE else 'documented_auth_or_key' if i in API_KEY else 'not_verified',
   permitted_scraping_available='not_verified',js_rendering_required='not_verified',test_status='landing_or_documentation_probe_only' if probe else 'not_live_tested',
   http_status=probe.get('http_status'),challenge=probe.get('challenge'),error_type=probe.get('error_type'),duplicate_of=f'supplied_{duplicate+1:03}' if duplicate is not None else None,
   decision=decision,reason=reason,adapter_names=names,
   supported_input=[{'adapter':name,'kind':installed[name].kind,'argument':installed[name].argument,'max_length':installed[name].max_length} for name in names],
   supported_output={'type':'normalized_tool_invocation','fields':['tool_id','invocation_id','status','started_at','finished_at','data','evidence_ids','warnings','errors']} if names else None,
   live_verified=False,last_checked='2026-10-29 (landing/documentation probe)' if probe else None,last_reviewed_at=datetime.now(timezone.utc).isoformat())
 access=ROOT/'output/autonomous-qa/osint4all-access.json';catalog=json.loads(access.read_text(encoding='utf-8')) if access.is_file() else{}
 report={'schema_version':1,'catalog_url':CATALOG,'catalog_access':catalog,'whole_collection_extracted':False,'catalog_records_discovered':0,
 'scope_note':'All153 supplied entries are considered. ExactStart.me catalog is blocked; no hidden API, guessedURL, alternatecollection or CAPTCHA bypass. URLprobes identify landingpages/documents only, never liveadapterverification. Further categories mentioned without concrete sites cannot be recovered.',
 'counts':{'catalog_records_discovered':0,'supplied_entries_reviewed':len(rows),'supplied_exact_url_identified':sum(bool(r['actual_url']) for r in rows),'supplied_without_exact_url':sum(not r['actual_url'] for r in rows),'duplicate_entries':sum(bool(r['duplicate_of']) for r in rows),'unique_urls_http_checked':len(probes),'http200_landing_or_docs':sum(p.get('http_status')==200 for p in probes.values()),'unavailable_in_this_probe':sum(p.get('http_status',0)>=400 or bool(p.get('error_type')) for p in probes.values()),'challenge_pages':sum(bool(p.get('challenge')) for p in probes.values()),'documented_auth_or_key_entries':sum(r['public_api_available']=='documented_auth_or_key' for r in rows),'documented_no_personal_key_api_entries':sum(r['public_api_available']=='documented_no_personal_key' for r in rows),'permitted_scraping_operations_verified':0,'entries_with_scoped_implemented_adapter':sum(bool(r['adapter_names']) for r in rows),'catalog_adapters_integrated':0,'catalog_adapters_live_verified':0},
 'implemented_distinct_adapter_names':sorted({name for row in rows for name in row['adapter_names']}),
 'additional_sources_outside_supplied_list':[
  {'name':'Hacker News Algolia','actual_url':'https://hn.algolia.com/api','documentation_url':'https://hn.algolia.com/api','from_catalog':False,'public_api_available':'documented_no_personal_key','rate_limit':'Officialdocs10000/hour/IP; application chooses muchlowerlimits','adapter_names':[name for name in ('hn_search','hn_profile') if name in installed],'live_verified':False},
  {'name':'Open Library','actual_url':'https://openlibrary.org/dev/docs/api/search','documentation_url':'https://openlibrary.org/developers/api','from_catalog':False,'public_api_available':'documented_no_personal_key','rate_limit':'IdentifyingUA, cache and conservative1request/second','adapter_names':[name for name in ('openlibrary_search',) if name in installed],'live_verified':False}],
 'entries':rows,'url_probes':probes}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report['counts'],ensure_ascii=True))
if __name__=='__main__':main()
