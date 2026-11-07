"""Reviewed source contracts, separate from user actions and network execution."""
from dataclasses import asdict,dataclass
import threading
from datetime import datetime,timezone

@dataclass(frozen=True)
class SourceDescriptor:
    id:str
    name:str
    category:str
    entity_types:tuple
    region:tuple
    documentation:str
    host:str
    license:str
    auth_key:str=''
    parser_version:str='1'
    status:str='implemented'

SOURCES={row.id:row for row in (
    SourceDescriptor('company_gleif','GLEIF · LEI','company',('organization',),('global',),'https://www.gleif.org/en/lei-data/gleif-api/','api.gleif.org','GLEIF open data terms'),
    SourceDescriptor('company_sec','SEC EDGAR · filings','company',('organization',),('US',),'https://www.sec.gov/search-filings/edgar-application-programming-interfaces','data.sec.gov','US government public data'),
    SourceDescriptor('company_companies_house','Companies House','company',('organization',),('GB',),'https://developer.company-information.service.gov.uk/','api.company-information.service.gov.uk','Crown copyright / Open Government Licence','companies_house_api_key'),
    SourceDescriptor('company_opencorporates','OpenCorporates','company',('organization',),('global',),'https://api.opencorporates.com/documentation/API-Reference','api.opencorporates.com','OpenCorporates API / account licence','opencorporates_api_key'),
    SourceDescriptor('company_opensanctions','OpenSanctions · candidates','company',('organization',),('global',),'https://www.opensanctions.org/docs/api/','api.opensanctions.org','OpenSanctions data licence / non-commercial conditions','opensanctions_api_key'),
    SourceDescriptor('publication_crossref','Crossref · publications','academic',('document','organization'),('global',),'https://www.crossref.org/documentation/retrieve-metadata/rest-api/','api.crossref.org','Crossref metadata reuse; abstracts may have separate rights'),
    SourceDescriptor('software_osv','OSV · vulnerability record','software',('document','repository'),('global',),'https://google.github.io/osv.dev/api/','api.osv.dev','Source-specific OSV database licences'),
)}
_LOCK=threading.RLock();_HEALTH={}

def record_health(identifier,status,count):
    # No target, query, secret, response body or private model text is retained.
    checked_at=datetime.now(timezone.utc).isoformat()
    with _LOCK:
        last_success_at=checked_at if status=='complete' and count else _HEALTH.get(identifier,{}).get('last_success_at')
        _HEALTH[identifier]={'status':status,'result_count':count,'checked_at':checked_at,'last_success_at':last_success_at}

def describe(identifier,configured):
    item=SOURCES.get(identifier)
    if not item:
        from .source_adapters import CONTRACTS
        adapter=CONTRACTS.get(identifier)
        return {**adapter.describe(),'runtime_available':bool(configured)} if adapter else None
    with _LOCK:health=dict(_HEALTH.get(identifier,{}))
    return {**{k:v for k,v in asdict(item).items() if k!='auth_key'},
        'authentication':'own_api_key' if item.auth_key else 'none','runtime_available':bool(configured),
        'health':health or {'status':'not_checked'},'formats':['json'],
        'provenance_schema':'source_id, endpoint, observed_at, content_sha256, parser_version',
        'limits':'2 MB per response; bounded records, rate gate, 5-minute cache; no access bypass'}

def catalog(secret_getter=lambda _: ''):
    rows=[]
    for item in SOURCES.values():
        configured=not item.auth_key or bool(secret_getter(item.auth_key))
        rows.append(describe(item.id,configured))
    from .source_adapters import CONTRACTS
    rows.extend(describe(identifier,True) for identifier in CONTRACTS)
    return rows
