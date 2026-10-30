"""Own isolated Qt/WebEngine: real previously fetched photos, live OSM tiles.

No ML, API key, user profile or image upload is needed to inspect the evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--research',type=Path,required=True)
    parser.add_argument('--observations',type=Path,required=True)
    parser.add_argument('--exe',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a fresh QA directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    profile=out/'appdata/GrangerPet'
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/gallery_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.config import Settings
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.investigation import new_investigation
    from grangerpet.graph_store import GraphViewStore
    from grangerpet.ipc import send_command
    # Only these protected image stores from a named prior QA run, never credentials/history.
    source=args.research.resolve()/'appdata/GrangerPet'
    for name in ('attachments','public-media'):
        if (source/name).exists():shutil.copytree(source/name,profile/name)
    profile.mkdir(parents=True,exist_ok=True)
    (profile/'settings.json').write_text(json.dumps(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    rows=json.loads(args.observations.read_text(encoding='utf-8'))['results']+json.loads((args.research/'result.json').read_text(encoding='utf-8'))['results']
    record,protocol=new_investigation('Проверка сохранённых GEOINT-фотографий: исходник, эталоны и карта')
    record.update(status='completed')
    journal=InvestigationJournal(profile/'investigations')
    journal.save_checkpoint({**protocol,'version':1,'id':record['id'],'record':record,'evidence':rows,'executions':[]})
    GraphViewStore(journal).select(record['id'])
    report={'mode':'actual_frozen_Qt_WebEngine' if args.exe else 'actual_source_Qt_WebEngine','mock':False,
        'inference_calls':0,'gateway_calls':0,'image_uploads':0,'checks':[]}
    owned=None;process=None
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)})
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'check':name,'passed':bool(ok)}),flush=True)
        if not ok:raise AssertionError(name)
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.2)
        raise TimeoutError('Own gallery GUI wait expired')
    def state():
        value=send_command('pet','status',timeout=2500)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Own PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own QA command failed: '+name)
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():action('dom');return state()['desktop'].get('dom',{})
    def click(label):
        e=wait(lambda:next((e for e in dom().get('elements',[]) if (e.get('label')==label or e.get('text')==label) and e['width']>0 and 0<e['y']<dom().get('height',0)-12),None))
        action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(18,e['height']/2)]})
    def snapshot(name):command('qa_snapshot',{'name':name})
    def saved():
        command('qa_desktop',{'action':'save_state','name':'current'})
        return json.loads((out/'current.json').read_text(encoding='utf-8'))
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/'process.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready'])
        command('show_workspace',{'route':'search'})
        wait(lambda:saved().get('investigation_graph',{}).get('state')=='ready')
        action('graph_scroll');click('Карта и фото')
        value=wait(lambda:v if (v:=saved()).get('geo_views',{}).get(record['id'],{}).get('has_geoint') else None)
        geo=value['geo_views'][record['id']]
        check('same_investigation_and_real_cached_reference_photos',geo['investigation_id']==record['id'] and sum(image.get('media',{}).get('state')=='ready' for image in geo['images'])>=2)
        def map_ready():
            images=[image for image in (dom().get('geo') or {}).get('images',[]) if image['alt']=='Картографическая подложка OpenStreetMap']
            return len(images)>1 and all(image['loaded'] for image in images)
        wait(map_ready,90)
        check('actual_osm_basemap_and_attribution',(dom().get('geo') or {}).get('attribution')=='© OpenStreetMap contributors')
        action('geoint_scroll',{'section':'map'})
        snapshot('actual-geoint-map')
        action('geoint_scroll',{'section':'header'})
        click('Фото')
        wait(lambda:any(image['loaded'] for image in (dom().get('geo') or {}).get('images',[]) if image['alt']=='Исходная фотография пользователя'))
        check('rendered_pixels_are_local_cache_data',all(image['source_is_local'] for image in dom()['geo']['images']))
        action('geoint_scroll',{'section':'gallery'})
        snapshot('actual-photo-gallery')
        # Scroll within the native WebEngine surface until the comparison action is visible.
        for _ in range(6):
            element=next((e for e in dom().get('elements',[]) if e.get('text')=='Сравнить с исходным' and 0<e['y']<dom().get('height',0)-40),None)
            if element:break
            action('input',{'kind':'wheel','at':[max(100,dom()['width']-350),dom()['height']-110],'delta':-400})
        click('Сравнить с исходным')
        action('geoint_scroll',{'section':'compare'})
        wait(lambda:(dom().get('geo') or {}).get('comparison'))
        check('native_side_by_side_comparison',sum(image['loaded'] for image in dom()['geo']['images'])>=2)
        snapshot('actual-photo-comparison')
        action('geoint_scroll',{'section':'controls'})
        click('Совпадения деталей')
        wait(lambda:(dom().get('geo') or {}).get('overlays')==2)
        check('native_geometry_overlays_without_claiming_verified_location',True)
        action('geoint_scroll',{'section':'compare'})
        snapshot('actual-feature-overlays')
        check('no_horizontal_window_overflow',not dom()['overflow'])
        command('stop');process.wait(timeout=30);owned=None
    except Exception as error:
        snapshot('failure')
        (out/'failure-dom.json').write_text(json.dumps(dom(),ensure_ascii=False,indent=2),encoding='utf-8')
        report.update(passed=False,error_type=type(error).__name__)
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally:
        if owned and process and process.poll() is None:
            try:command('stop');process.wait(timeout=30)
            except Exception:pass
    if any(not row['passed'] for row in report['checks']):raise SystemExit(1)


if __name__=='__main__':main()
