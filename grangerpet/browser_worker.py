"""Isolated Playwright/Edge public research worker. Bounded JSON-lines pipes."""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
import os

sys.path.insert(0,str(Path(__file__).resolve().parent))
from browser_policy import public_url,search_text,SENSITIVE
from browser_proxy import PublicProxy,RobotsPolicy

SNAPSHOT=r'''() => {
  const visible=e=>{const r=e.getBoundingClientRect();return !!(r.width&&r.height)&&getComputedStyle(e).visibility!=='hidden'};
  const all=[...document.querySelectorAll('a[href],button,input,textarea,select,[role="button"]')].filter(visible).slice(0,100);
  return {title:document.title,url:location.href,text:((document.querySelector('main')||document.querySelector('#mw-content-text')||document.body)?.innerText||'').slice(0,18000),loading_state:document.readyState,
    viewport:{width:innerWidth,height:innerHeight,scrollY},
    elements:all.map((e,id)=>({id:String(id),tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',name:e.getAttribute('name')||'',
      label:(e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||e.getAttribute('title')||((e.type==='submit'||e.type==='button')?e.value:'')||'').trim().slice(0,180),
      href:e.tagName==='A'?e.href:'',form_method:e.form?(e.form.method||'get').toLowerCase():'',
      search_field:e.matches('input[type="search"],input[name="q"],input[name="query"],input[name="search"],input[role="searchbox"]')})),
    tables:[...document.querySelectorAll('table')].slice(0,6).map(t=>({headers:[...t.querySelectorAll('th')].slice(0,20).map(e=>e.innerText.slice(0,120)),
      rows:[...t.querySelectorAll('tr')].filter(r=>r.querySelector('td')).slice(0,40).map(r=>[...r.querySelectorAll('td')].slice(0,20).map(e=>e.innerText.slice(0,200))),rows_total:t.querySelectorAll('tr').length})),
    metadata:[...document.querySelectorAll('meta[name],meta[property]')].slice(0,25).map(m=>({name:m.name||m.getAttribute('property'),content:(m.content||'').slice(0,500)})),
    json_ld:[...document.querySelectorAll('script[type="application/ld+json"]')].slice(0,8).map(s=>{try{return JSON.parse(s.textContent.slice(0,5000))}catch(e){return {parse_error:true}}})};
}'''


def main():
    print(json.dumps({'ready':True,'pid':os.getpid(),'protocol':1}),flush=True)
    browser=context=page=proxy=playwright=None;epoch='';last={};handles=[];robots=None
    try:
        for line in sys.stdin:
            if len(line)>32768:break
            command={};result={}
            try:
                command=json.loads(line)
                if not isinstance(command,dict) or set(command)-{'id','action','url','element_id','snapshot_id','text','delta'}:raise ValueError('invalid_browser_command')
                action=command.get('action')
                if action=='close':
                    print(json.dumps({'id':command['id'],'ok':True,'closed':True}),flush=True);break
                if action not in ('navigate','snapshot','screenshot','click','type','scroll','back'):raise ValueError('unknown_browser_action')
                if browser is None:
                    from playwright.sync_api import sync_playwright
                    proxy=PublicProxy();robots=RobotsPolicy(proxy);playwright=sync_playwright().start()
                    browser=playwright.chromium.launch(channel='msedge',headless=True,
                        proxy={'server':'http://127.0.0.1:'+str(proxy.server_address[1]),'bypass':'<-loopback>'},
                        args=['--disable-quic','--disable-background-networking','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
                    context=browser.new_context(viewport={'width':1024,'height':720},service_workers='block',
                        accept_downloads=False,permissions=[],ignore_https_errors=False,
                        user_agent='Granger-OSINT/3.1 public research (https://github.com/watsoncore/Granger-OSINT)')
                    def route(request_route):
                        req=request_route.request
                        try:
                            public_url(req.url)
                            if req.method not in ('GET','HEAD') or req.resource_type in ('websocket','eventsource'):raise ValueError()
                            if req.is_navigation_request() and not robots.allowed(req.url):raise ValueError('robots_disallowed')
                            request_route.continue_()
                        except (ValueError,UnicodeError):request_route.abort('blockedbyclient')
                    context.route('**/*',route)
                    context.route_web_socket('**/*',lambda socket:socket.close())
                    context.add_init_script("for(const n of ['RTCPeerConnection','webkitRTCPeerConnection','WebTransport'])try{Object.defineProperty(window,n,{value:undefined,writable:false,configurable:false})}catch(e){}")
                    page=context.new_page();page.set_default_timeout(8000);page.on('dialog',lambda dialog:dialog.dismiss())
                    page.on('download',lambda download:download.cancel())
                    context.on('page',lambda popup:popup.close() if popup!=page else None)
                if action=='navigate':
                    if not robots.allowed(public_url(command.get('url'))):raise ValueError('robots_disallowed')
                    page.goto(public_url(command.get('url')),wait_until='domcontentloaded',timeout=18000)
                elif action in ('click','type'):
                    if command.get('snapshot_id')!=epoch:raise ValueError('stale_browser_snapshot')
                    element_id=command.get('element_id')
                    if not isinstance(element_id,str) or not element_id.isdigit() or int(element_id)>=len(last.get('elements',[])):raise ValueError('unknown_element')
                    element=last['elements'][int(element_id)]
                    handle=handles[int(element_id)]
                    # Handles live in Python, never a writable page global.
                    # Recheck the actual element immediately before acting.
                    current=handle.evaluate("e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',name:e.getAttribute('name')||'',href:e.tagName==='A'?e.href:'',label:(e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||e.getAttribute('title')||((e.type==='submit'||e.type==='button')?e.value:'')||'').trim(),form_method:e.form?(e.form.method||'get').toLowerCase():'',search_field:e.matches('input[type=search],input[name=q],input[name=query],input[name=search],input[role=searchbox]')})")
                    element=current
                    if action=='type':
                        text=search_text(command.get('text'))
                        if not element['search_field'] or element['type'] not in ('','text','search') or element['form_method'] not in ('','get') or SENSITIVE.search(element['name']):raise ValueError('search_fields_only')
                        handle.fill(text)
                    else:
                        label=element['label'].casefold()
                        if element['href']:public_url(element['href'])
                        elif element['form_method']=='get' and re.search(r'search|поиск|найти',label):pass
                        elif not element['form_method'] and re.search(r'^(?:next|more|load more|show|следующ|ещ[её]|показать)',label):pass
                        else:raise ValueError('consequential_or_unknown_button_disabled')
                        handle.click()
                elif action=='scroll':
                    delta=command.get('delta',500)
                    if type(delta) is not int or not -1400<=delta<=1400:raise ValueError('invalid_scroll')
                    page.mouse.wheel(0,delta)
                elif action=='back':page.go_back(wait_until='domcontentloaded')
                page.wait_for_timeout(350)
                public_url(page.url)
                if not robots.allowed(page.url):raise ValueError('robots_disallowed')
                for handle in handles:
                    try:handle.dispose()
                    except Exception:pass
                def in_view(handle):
                    box=handle.bounding_box()
                    return handle.is_visible() and box and box['y']+box['height']>=0 and box['y']<=720 and box['x']+box['width']>=0 and box['x']<=1024
                primary=[h for h in page.query_selector_all('main a[href],main button,main input,#mw-content-text a[href],.mw-search-results a[href]') if in_view(h)][:75]
                secondary=[h for h in page.query_selector_all('input,button,a[href],textarea,select,[role="button"]') if in_view(h)][:25 if primary else 100]
                handles=primary+secondary
                last=page.evaluate(SNAPSHOT)
                # Store the map using metadata from the same retained handles.
                last['elements']=[]
                for index,handle in enumerate(handles):
                    item=handle.evaluate("e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',name:e.getAttribute('name')||'',label:(e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||e.getAttribute('title')||((e.type==='submit'||e.type==='button')?e.value:'')||'').trim().slice(0,180),href:e.tagName==='A'?e.href:'',form_method:e.form?(e.form.method||'get').toLowerCase():'',search_field:e.matches('input[type=search],input[name=q],input[name=query],input[name=search],input[role=searchbox]')})")
                    item['id']=str(index);last['elements'].append(item)
                epoch=uuid.uuid4().hex
                picture=page.screenshot(type='jpeg',quality=65,timeout=8000)
                if len(picture)>700_000:raise ValueError('screenshot_budget')
                result={'id':command['id'],'ok':True,'snapshot_id':epoch,'action':action,'untrusted_page_data':last,
                    'screenshot':base64.b64encode(picture).decode(),'screenshot_mime':'image/jpeg','screenshot_sha256':hashlib.sha256(picture).hexdigest(),
                    'network':{'wire_bytes':proxy.bytes,'requests':proxy.requests,'blocked':proxy.blocked},
                    'robots_checks':robots.checks,
                    'visual_access':'DOM text only for text models; screenshot is for local UI/OCR, not sent as vision input'}
            except Exception as error:
                code=str(error) if isinstance(error,ValueError) else 'browser_timeout' if 'Timeout' in type(error).__name__ else 'browser_operation_failed'
                result={'id':command.get('id'),'ok':False,'error_code':code[:100] if re.fullmatch(r'[a-z_]+',code) else 'browser_operation_failed'}
            raw=json.dumps(result,ensure_ascii=True)
            if len(raw)>1_800_000:raw=json.dumps({'id':command.get('id'),'ok':False,'error_code':'browser_output_budget'})
            print(raw,flush=True)
    finally:
        if context:context.close()
        if browser:browser.close()
        if playwright:playwright.stop()
        if proxy:proxy.stop()


if __name__=='__main__':main()
