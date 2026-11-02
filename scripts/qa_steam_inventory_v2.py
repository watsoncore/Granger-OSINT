"""User-requested passive public inventory control. No sessions or trade actions."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.agent_browser import PublicPageReader,PageReadError
    from grangerpet.agent_web import _run,_FetchError
    from grangerpet.web_http import fetch_public
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--collect',action='store_true');p.add_argument('--page-size',type=int,choices=(100,200),default=100);args=p.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Prior receipts preserved')
    out.mkdir(parents=True);registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    profile=registry.execute('steam_profile',{'profile':'76561198045277210'},deadline=time.monotonic()+40)
    (out/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.collect:
        import asyncio,base64
        from grangerpet.public_media import MediaStore,media_reference
        cursor=None;calls=[]
        try:
            for index in range(5):
                arguments={'profile':'76561198045277210','page_size':args.page_size,'price_limit':3 if index==0 else 0,**({'cursor':cursor} if cursor else {})}
                result=registry.execute('steam_inventory',arguments,deadline=time.monotonic()+40)
                (out/f'inventory-{index+1}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                summary=next((row['details'] for row in result.get('results',[]) if row.get('type')=='steam_inventory'),{})
                coverage=summary.get('coverage',{});calls.append({'status':result.get('status'),'coverage':coverage,'source_failures':summary.get('source_failures',[])})
                (out/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'call':index+1,'status':result.get('status'),'assets':coverage.get('observed_assets'),'more':coverage.get('more_items')}),flush=True)
                cursor=coverage.get('next_cursor')
                if not cursor or coverage.get('stop_reason')!='page_limit':break
            records=registry.evidence.records();items=[row for row in records if row.get('type')=='steam_item'];media=[]
            for index,row in enumerate(items[:2]+profile.get('results',[])[:1]):
                reference=media_reference(row)
                if not reference:continue
                try:
                    value=asyncio.run(MediaStore(out/'isolated-profile/public-media').fetch(reference,deadline=time.monotonic()+20))
                    if value.get('thumbnail'):(out/f'media-{index+1}.jpg').write_bytes(base64.b64decode(value['thumbnail'].split(',',1)[1]))
                    media.append({key:value.get(key) for key in ('id','state','source_url','url','width','height','bytes','sha256','fetched_at')})
                except (ValueError,OSError,PageReadError,TimeoutError) as error:media.append({'state':'unavailable','error_code':getattr(error,'code',type(error).__name__)})
            summary={'timestamp':datetime.now(timezone.utc).isoformat(),'live':True,'keys_or_cookies':False,
                'distinct_assets':len({row['details']['assetid'] for row in items}),
                'names_observed':sum(bool(row['details'].get('name')) for row in items),
                'floats_observed':sum(row['details'].get('float_value') is not None for row in items),
                'patterns_observed':sum(row['details'].get('pattern_template') is not None for row in items),
                'priced_assets':sum(bool((row['details'].get('price') or {}).get('amount_decimal')) for row in items),
                'sample_names':[row['details'].get('name') for row in items[:5]],'calls':calls,'media':media}
            (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:value for key,value in summary.items() if key!='calls'},ensure_ascii=False),flush=True)
        finally:registry.close()
        return
    reader=PublicPageReader(max_pages=2,max_depth=0)
    endpoint='https://steamcommunity.com/inventory/76561198045277210/730/2?l=english&count=50'
    summary={'timestamp':datetime.now(timezone.utc).isoformat(),'endpoint':endpoint,'profile_status':profile.get('status'),
        'actual_profile_names':[row.get('details',{}).get('display_name') for row in profile.get('results',[])],
        'keys_or_cookies':False,'probe_page_size':50}
    async def probe():
        end=time.monotonic()+30
        return await fetch_public(endpoint,deadline=end,rate_interval=1,
            allowed_types=('application/json','text/json'),accepted_statuses=(200,401,403,404,429,500,502,503),
            before_request=lambda url:reader._check_robots(url,None,end))
    try:
        result=_run(probe,timeout=35);body=result['body'];summary.update(http_status=result['status'],
            response_bytes=len(body),body_sha256=hashlib.sha256(body).hexdigest(),final_url=result['final_url'])
        if result['status']==200:
            payload=json.loads(body.decode('utf-8-sig'))
            (out/'inventory-page.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            summary.update(payload_keys=sorted(payload),assets=len(payload.get('assets',[])),descriptions=len(payload.get('descriptions',[])),
                more_items=payload.get('more_items'),total_inventory_count=payload.get('total_inventory_count'),
                sample_names=[row.get('name') for row in payload.get('descriptions',[])[:5]])
    except (PageReadError,_FetchError) as error:summary.update(status=error.status,error_code=error.code)
    finally:registry.close()
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
