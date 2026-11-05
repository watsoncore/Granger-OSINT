"""Bounded inert extraction shared by HTTP and isolated rendered documents.

No source text is executed here. Observations preserve their extraction method;
neither a parsed record nor a structured field is a verified identity/fact.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from xml.etree import ElementTree
import csv
import io

PARSER_REGISTRY={
    'html':{'version':'granger-html/2','mime_types':('text/html','application/xhtml+xml'),'mode':'inert_html'},
    'json':{'version':'granger-json/2','mime_types':('application/json','application/ld+json'),'mode':'bounded_json'},
    'xml':{'version':'granger-xml/2','mime_types':('application/xml','text/xml'),'mode':'no_dtd_entities'},
    'rss':{'version':'granger-rss-atom/2','mime_types':('application/rss+xml','application/atom+xml'),'mode':'no_dtd_entities'},
    'csv':{'version':'granger-csv/1','mime_types':('text/csv','application/csv','text/tab-separated-values'),'mode':'inert_table'},
    'pdf':{'version':'granger-qtpdf/1','mime_types':('application/pdf',),'mode':'local_text_only'},
    'text':{'version':'granger-text/1','mime_types':('text/plain',),'mode':'inert_text'},
}


def parser_contract(content_type):
    mime=content_type.split(';',1)[0].strip().lower()
    for name,contract in PARSER_REGISTRY.items():
        if mime in contract['mime_types']:return {'format':name,**contract}
    return {'format':'text',**PARSER_REGISTRY['text']}


def parse_csv(text,base_url,max_text=12_000):
    sample=text[:8000]
    try:dialect=csv.Sniffer().sniff(sample,delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    rows=[];truncated=False
    try:
        for index,row in enumerate(csv.reader(io.StringIO(text),dialect)):
            if index>=101:truncated=True;break
            if len(row)>100:raise ValueError('csv_columns_limit')
            rows.append([cell[:2000] for cell in row])
    except csv.Error:raise ValueError('invalid_csv') from None
    title=base_url.rsplit('/',1)[-1] or 'CSV'
    return {'title':title,'text':'\n'.join(' · '.join(row) for row in rows)[:max_text],'headings':[],
        'metadata':{},'tables':[{'headers':rows[0] if rows else [],'rows':rows[1:]}],'json_ld':[],'links':[],'javascript_shell':False,
        'structured_data':{'format':'csv','records':bounded_json(rows[1:]),'headers':rows[0] if rows else [],'truncated':truncated},
        'render_warnings':['CSV ограничен 100 строками данных; формулы сохраняются как текст.'] if truncated else []}


def parse_pdf(raw,base_url,*,cancel_event=None,max_text=12_000,max_pages=20):
    """Qt's installed PDFium extracts text locally; no rendering, OCR or links."""
    if len(raw)>2_000_000 or not raw.startswith(b'%PDF-'):raise ValueError('invalid_or_large_pdf')
    from PySide6.QtCore import QByteArray,QBuffer,QIODevice
    from PySide6.QtPdf import QPdfDocument
    buffer=QBuffer();buffer.setData(QByteArray(raw));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    document=QPdfDocument();sections=[];pages=[];length=0
    try:
        document.load(buffer)
        if document.status()!=QPdfDocument.Status.Ready:raise ValueError('pdf_unreadable_or_password_required')
        count=document.pageCount()
        for index in range(min(count,max_pages)):
            if cancel_event and cancel_event.is_set():raise ValueError('cancelled')
            text=document.getAllText(index).text()[:max_text-length]
            pages.append({'page':index+1,'text':text});sections.append(text);length+=len(text)
            if length>=max_text:break
        return {'title':document.metaData(QPdfDocument.MetaDataField.Title) or base_url.rsplit('/',1)[-1],
            'text':'\n\n'.join(sections)[:max_text],'headings':[],'metadata':{'pdf_pages':count},'tables':[],
            'json_ld':[],'links':[],'javascript_shell':False,'structured_data':{'format':'pdf','records':pages,'page_count':count,'pages_extracted':len(pages)},
            'render_warnings':['Локально извлечён текст первых '+str(len(pages))+' страниц. Сканированные страницы требуют отдельного OCR; отсутствие текста не означает отсутствие содержимого.']}
    finally:document.close();buffer.close()


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
    parents={child:parent for parent in nodes for child in parent}
    for element in nodes:
        tag=local(element.tag)
        if tag=='link':
            candidate=element.attrib.get('href') or element.text or ''
            try:
                from urllib.parse import urljoin
                url=public_url(urljoin(base_url,candidate.strip()))
                parent=parents.get(element)
                record_link=parent is not None and local(parent.tag) in ('entry','item')
                if len(links)<60 and url not in [r['url'] for r in links]:links.append({'url':url,'text':clean(element.attrib.get('title',''),180),
                    'content_region':'record_field' if record_link else 'unclassified','extraction_method':'inert_xml_parser',
                    'selector':(local(parent.tag)+'/' if parent is not None else '')+'link'})
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
