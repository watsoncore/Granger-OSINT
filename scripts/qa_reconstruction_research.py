"""Actual public geographic research using a previously completed pixel pipeline."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--no-compare',action='store_true')
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Choose another output explicitly; prior live results are preserved.')
    out=args.output.resolve();out.mkdir(parents=True)
    os.environ['APPDATA']=str(out/'appdata')
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.geoint_tools import attachment_store
    from grangerpet.visual_models.manager import get_manager
    store=attachment_store();image=store.import_bytes(args.image.read_bytes(),args.image.name)
    registry=ToolRegistry(Settings(source_root=str(ROOT)),attachment_ids=[image['id']],image_store=store,secret_getter=lambda _: '')
    previous=json.loads(args.observations.read_text(encoding='utf-8'))
    registry.evidence.restore(previous['results'],[])
    events=[];started=time.monotonic()
    result=registry.execute('geoint_research',{'attachment_id':image['id'],'max_candidates':2,
        'references_per_candidate':3,'compare':not args.no_compare},deadline=time.monotonic()+180,on_event=events.append)
    get_manager().close()
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    candidates=[row['details'] for row in result.get('results',[]) if row['type']=='geoint_candidate']
    images=[row for row in result.get('results',[]) if row['type']=='reference_image']
    report={'mock':False,'mode':'actual_public_sources_and_local_visual_comparison','status':result['status'],
        'error':result.get('error'),'elapsed_seconds':round(time.monotonic()-started,3),'image_uploaded':False,
        'candidates':[{key:row.get(key) for key in ('candidate_id','latitude','longitude','region','verification_status',
            'nearby_landmarks','research_queries','reference_images')} for row in candidates],
        'reference_images':[{key:row['details'].get(key) for key in ('provider','source_url','image_url','title','license','author',
            'image_fetched','comparison')} for row in images], 'streamed_results':len(events)}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('candidates','reference_images')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
