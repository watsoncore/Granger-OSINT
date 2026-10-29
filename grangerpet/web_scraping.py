"""Bounded inert extraction shared by HTTP and isolated rendered documents.

No source text is executed here. Observations preserve their extraction method;
neither a parsed record nor a structured field is a verified identity/fact.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from xml.etree import ElementTree


@dataclass
class ScrapeResult:
    source_id: str
    requested_url: str
    final_url: str
    method: str
    http_status: int | None
    title: str | None
    extracted_text: str | None
    structured_data: dict
    discovered_links: list[str]
    fetched_at: str
    extraction_status: str
    evidence_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def bounded_json(value, *, maximum=60_000):
    """Retain useful JSON without unbounded depth, strings, collections or output."""
    budget=[maximum]
    def walk(item,depth=0):
        if depth>8 or budget[0]<=0:return None
        if isinstance(item,dict):
            result={}
            for key,child in list(item.items())[:100]:
                key=str(key)[:200];budget[0]-=len(key)
                if budget[0]<=0:break
                result[key]=walk(child,depth+1)
            return result
        if isinstance(item,list):return [walk(child,depth+1) for child in item[:100] if budget[0]>0]
        if isinstance(item,str):
            text=item[:min(3000,max(0,budget[0]))];budget[0]-=len(text);return text
        budget[0]-=20
        return item if item is None or isinstance(item,(bool,int,float)) else str(item)[:100]
    return walk(value)


def parse_xml(text, base_url, public_url, max_text=12_000):
    """Parse RSS/Atom/plain XML; DTDs/entities are deliberately unsupported."""
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)',text,re.I):
        raise ValueError('xml_external_entities_forbidden')
    root=ElementTree.fromstring(text)
    nodes=list(root.iter())
    if len(nodes)>25_000:raise ValueError('xml_complexity_limit')
    def local(tag):return tag.rsplit('}',1)[-1].lower()
    def clean(value,limit=2000):return re.sub(r'\s+',' ',str(value or '')).strip()[:limit]
    def child_text(element,name):
        return next((clean(''.join(c.itertext())) for c in element if local(c.tag)==name),'')
    links=[];records=[];sections=[]
    for element in nodes:
        tag=local(element.tag)
        if tag=='link':
            candidate=element.attrib.get('href') or element.text or ''
            try:
                from urllib.parse import urljoin
                url=public_url(urljoin(base_url,candidate.strip()))
                if len(links)<60 and url not in [r['url'] for r in links]:links.append({'url':url,'text':clean(element.attrib.get('title',''),180)})
            except (RuntimeError,ValueError):pass
        if tag in ('item','entry') and len(records)<100:
            record={}
            for name in ('title','description','summary','content','published','updated','pubdate','author','creator','guid','id'):
                value=child_text(element,name)
                if value:record[name]=value
            record['links']=[c.attrib.get('href') or clean(c.text,2000) for c in element if local(c.tag)=='link'][:8]
            if record:records.append(record)
        if element.text and tag not in ('script','style'):
            sections.append(clean(element.text))
    title=next((clean(e.text,300) for e in nodes if local(e.tag)=='title' and e.text),'')
    return {'title':title,'text':'\n'.join(sections)[:max_text],'headings':[],
        'metadata':{},'tables':[],'json_ld':[],'links':links,'javascript_shell':False,
        'structured_data':{'format':local(root.tag),'records':bounded_json(records),
            'xml_fields':[{ 'name':local(e.tag),'text':clean(e.text,500),'attributes':dict(list(e.attrib.items())[:12])}
                          for e in nodes[:300] if e.text and e.text.strip()]}}


def extraction_status(data):
    text=str(data.get('text','')).strip()
    if data.get('javascript_shell'):return 'javascript_required'
    if not text and not data.get('structured_data',{}).get('records'):return 'empty_content'
    if data.get('structured_data',{}).get('records'):return 'record_extracted'
    return 'parsed_page'


def content_block(text):
    """Reject challenge/login responses even when an origin sends HTTP200."""
    sample=text[:150_000]
    if re.search(r'(?:g-recaptcha|h-captcha|cf-chl-|challenge-platform|verify you are human|checking your browser)',sample,re.I):
        return 'access_challenge'
    if re.search(r'<input\b[^>]*\btype\s*=\s*["\']?password\b',sample,re.I):
        return 'login_form'
    return None
