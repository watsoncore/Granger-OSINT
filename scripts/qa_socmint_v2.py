"""Controlled public SOCMINT live checks; no account/profile secrets are read."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import httpx
    from grangerpet.agent_browser import PublicPageReader
    from grangerpet.socmint_public import vk_public,tiktok_public
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--platform',choices=('all','vk','tiktok'),default='all');p.add_argument('--limit',type=int,default=4);args=p.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Existing receipts preserved; choose another directory')
    out.mkdir(parents=True);http=[];results=[]
    async def response(value):
        http.append({'timestamp':datetime.now(timezone.utc).isoformat(),'url':str(value.request.url),'status':value.status_code,
                     'method':value.request.method,'content_type':value.headers.get('content-type')})
    def factory(**kwargs):return httpx.AsyncClient(**kwargs,event_hooks={'response':[response]})
    class RecordingReader(PublicPageReader):
        def read(self,*a,**k):
            result=super().read(*a,**k)
            (out/f'{len(results)+1}-page.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
    reader=RecordingReader(max_pages=8,max_depth=1,client_factory=factory,respect_robots=True,allow_browser=True)
    class RecordingRegistry(ToolRegistry):
        def _structured_operation(self,spec,*a,**k):
            result=super()._structured_operation(spec,*a,**k)
            if spec.source=='browser_agent':
                (out/f'{len(results)+1}-browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
    registry=RecordingRegistry(Settings(),secret_getter=lambda _: '')
    registry.web_reader=reader
    cases=[('vk','https://vk.com/apiclub'),('vk','https://vk.com/vk'),
           ('tiktok','@scout2015'),('tiktok','https://www.tiktok.com/@scout2015/video/6718335390845095173')]
    for platform,target in cases:
        if args.platform not in ('all',platform):continue
        if len(results)>=args.limit:break
        start=time.monotonic();before=len(http)
        result=registry.execute('vk_public',{'target':target},deadline=start+55) if platform=='vk' else tiktok_public(
            target,client_factory=factory,deadline=start+30)
        rows=result.get('results',[])
        results.append({'platform':platform,'target':target,'status':result.get('status'),
            'error_code':result.get('error_code') or result.get('error'),'evidence_count':len(rows),
            'fields_present':[{key for key,value in row.get('details',{}).items() if value is not None} for row in rows],
            'http_requests':len(http)-before,'seconds':round(time.monotonic()-start,3),
            'source_diagnostics':result.get('source_diagnostics'),
            'limitations':result.get('limitations',[])})
        (out/f'{len(results)}-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'http.json').write_text(json.dumps(http,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=lambda x:sorted(x)),encoding='utf-8')
        print(json.dumps(results[-1],ensure_ascii=False,default=lambda x:sorted(x)),flush=True)
        registry.close()


if __name__=='__main__':main()
