"""Real CPU/public-source/SSE verification on a preselected licensed photo set.

Input annotations are used only for scoring after inference, never in tool or
gateway prompts. Files and answers remain in the private output directory.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--images',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--synthesis',action='store_true')
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior actual inference retained; choose a fresh output directory')
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    key=resolve_deepseek_key() if args.synthesis else ''
    out.mkdir(parents=True)
    os.environ['APPDATA']=str(out/'appdata')
    from grangerpet.geoint_tools import attachment_store
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.agent import AgentRunner,AgentLimits
    from grangerpet.ai import DeepSeekClient
    from grangerpet.config import Settings
    from grangerpet.visual_models.manager import get_manager
    from grangerpet.visual_models.pipeline import haversine_km
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    report={'mock':False,'mode':'actual_cpu_public_research_and_optional_gateway_sse',
        'selection':manifest['selection'],'original_sources':manifest['original_sources'],
        'image_uploads':0,'ground_truth_sent_to_models':False,'cases':[],
        'synthesis_requested':args.synthesis,'gateway_key_available':bool(key)}
    def write(path,value):
        text=json.dumps(value,ensure_ascii=False,indent=2)
        if key and key in text:raise RuntimeError('Secret in report; write refused')
        path.write_text(text,encoding='utf-8')
    def save():write(out/'report.json',report)
    store=attachment_store()
    for case in manifest['cases']:
        case_dir=out/case['id'];case_dir.mkdir()
        row={**case,'pixel_review':'pending','started_at':time.time()};report['cases'].append(row);save()
        started=time.monotonic()
        try:
            # Neutral name, no geography/credit/annotation in the inference input.
            image=store.import_bytes((args.images/case['file']).read_bytes(),case['id']+'.jpg')
            registry=ToolRegistry(Settings(source_root=str(ROOT)),attachment_ids=[image['id']],image_store=store,secret_getter=lambda _: '')
            visual=registry.execute('visual_geoint',{'attachment_id':image['id']},deadline=time.monotonic()+300)
            write(case_dir/'visual.json',visual)
            row['visual_status']=visual['status'];row['stages']=[];row['predictions']=[]
            for record in visual.get('results',[]):
                d=record.get('details',{});tool=d.get('capability') or d.get('tool')
                row['stages'].append({'tool':tool,'status':d.get('status'),'description':d.get('description') if tool=='image_understand' else None})
                predictions=d.get('predictions')
                if tool in ('geoclip_predict','waypoint_predict') and isinstance(predictions,list):
                    scores=[]
                    for rank,candidate in enumerate(predictions,1):
                        lat=candidate.get('lat',candidate.get('latitude'));lon=candidate.get('lon',candidate.get('longitude'))
                        if type(lat) in (int,float) and type(lon) in (int,float):
                            scores.append({'rank':rank,'latitude':lat,'longitude':lon,
                                'raw_score':candidate.get('raw_score'),'sample_fraction':candidate.get('sample_fraction'),
                                'distance_to_annotation_km':round(haversine_km([lat,lon],case['annotated_coordinate']),3)})
                    row['predictions'].append({'tool':tool,'candidates':scores})
            repeated=registry.execute('geoclip_predict',{'attachment_id':image['id']},deadline=time.monotonic()+30)
            row['exact_repeat_reused']=repeated.get('from_saved_data') is True and repeated.get('inference_calls')==0
            research=registry.execute('geoint_research',{'attachment_id':image['id'],
                'max_candidates':2,'references_per_candidate':3,'compare':True},deadline=time.monotonic()+180)
            write(case_dir/'research.json',research)
            row['research_status']=research['status'];row['references']=[]
            for record in research.get('results',[]):
                if record.get('type')=='reference_image':
                    d=record['details'];row['references'].append({k:d.get(k) for k in
                        ('source_url','image_url','author','license','captured_at','image_fetched','comparison')})
            row['evidence_count']=len(registry.evidence.records());save()
            if key:
                class SavedOnly:
                    def catalog(self):return []
                    def schemas(self):return []
                    def begin_investigation(self):runner._store.restore(registry.evidence.records(),registry.evidence.executions())
                    def execute(self,*a,**kw):raise AssertionError('Synthesis must not collect new data')
                events=[]
                runner=AgentRunner(DeepSeekClient(key),SavedOnly(),limits=AgentLimits(max_tokens=1,synthesis_timeout=300))
                answer=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':
                    'Проанализируй выбранное фото: видимая сцена, ориентиры, кандидаты места, совпадения и противоречия с реальными сравнительными снимками. '
                    'Раздели наблюдаемые признаки, гипотезы моделей и подтверждённые сведения. Объясни неопределённость и что ещё нужно проверить. '
                    'Не утверждай точное место без достаточных оснований; новые внешние вызовы сейчас не нужны.'}],on_event=events.append)
                if key in answer['text']:raise RuntimeError('Secret in answer; write refused')
                (case_dir/'answer.md').write_text(answer['text'],encoding='utf-8')
                row['synthesis']={'status':answer['investigation']['status'],
                    'report_status':answer['investigation'].get('report_status'),
                    'usage':answer['metadata'].get('usage'),'characters':len(answer['text']),
                    'text_events':sum(e['type']=='text' for e in events),
                    'raw_evidence_ids':bool(re.search(r'(?<!#)ev_[a-f0-9]{20}',answer['text']))}
            row['status']='executed'
        except Exception as error:
            row.update(status='failed',error_type=type(error).__name__,error_code=getattr(error,'code','qa_failure'))
        finally:
            get_manager().close()
            row['elapsed_seconds']=round(time.monotonic()-started,3);save()
            print(json.dumps({'case':case['id'],'status':row['status'],'visual':row.get('visual_status'),
                'research':row.get('research_status'),'seconds':row['elapsed_seconds']},ensure_ascii=False),flush=True)
    report['finished']=True;save()


if __name__=='__main__':main()
