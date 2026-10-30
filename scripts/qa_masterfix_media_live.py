"""Fetch one real media URL observed in the live TON evidence, never a guessed URL."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
out=ROOT/'output/masterfix/live-media-01';out.mkdir(parents=True,exist_ok=False)
os.environ['APPDATA']=str(out/'appdata')
from grangerpet.public_media import MediaStore,media_reference
records=json.loads((ROOT/'output/masterfix/live-ton-quick-04/result.json').read_text(encoding='utf-8'))['results']
references=[ref for row in records if row.get('type')=='nft_asset' and (ref:=media_reference(row))]
report={'mock':False,'observed_candidates':len(references),'checks':[]}
store=MediaStore()
for reference in references[:2]:
    try:
        value=asyncio.run(store.fetch(reference));report['checks'].append({k:v for k,v in value.items() if k!='thumbnail'})
        (out/'actual-thumbnail.jpg').write_bytes(base64.b64decode(value['thumbnail'].split(',',1)[1]))
        report['cache_restored']=store.cached(reference)==value
        report['passed']=report['cache_restored'];break
    except Exception as error:
        report['checks'].append({'url':reference['url'],'state':'unavailable','error_type':type(error).__name__,'code':getattr(error,'code','validation_or_network_error')})
report.setdefault('passed',False)
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
