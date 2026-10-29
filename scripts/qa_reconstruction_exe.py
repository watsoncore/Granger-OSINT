"""Actual frozen GUI + real image/OCR tools with an isolated synthetic profile.

No saved user keys, conversations, photographs or other applications are used.
Snapshots remain private local QA files; the public report contains assertions
and synthetic tool observations only. No gateway generation is performed here.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from PIL import Image,ImageDraw,ImageFont
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from perf_process_metrics import ProcessSampler,summarize
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--keep-open',action='store_true')
    p.add_argument('--public-tools',action='store_true',help='Also execute one real key-free API and permitted JS sandbox in the frozen EXE')
    p.add_argument('--integrations19',action='store_true',help='Verify typed local tools, graph and the installed optional CPU pipeline')
    args=p.parse_args();out=args.output.resolve()
    if out.exists(): raise SystemExit('Previous evidence retained; choose a new directory')
    app=QCoreApplication.instance() or QCoreApplication([])
    if send_command('pet','status') or send_command('launcher','status'): raise SystemExit('Existing Granger instance left untouched')
    out.mkdir(parents=True);profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(cursor_reaction=False,reduced_motion=True,source_root=str(ROOT)).to_dict()),encoding='utf-8')
    exe=ROOT/'dist/Granger-OSINT.exe'
    env=os.environ.copy()
    for name in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QTWEBENGINE_CHROMIUM_FLAGS','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
        env.pop(name,None)
    env.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),
        GRANGERPET_QA_VAULT='GrangerPet/QA/reconstruction_'+uuid.uuid4().hex,PATH=str(Path(env.get('SystemRoot','C:/Windows'))/'System32'))
    report={'mode':'actual_frozen_GUI_local_pixel_tools','mock':False,'user_data_read':False,'gateway_calls':0,
        'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[],'metrics':{}}
    def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,condition):
        report['checks'].append({'name':name,'passed':bool(condition)});save()
        if not condition: raise AssertionError(name)
    def wait(predicate,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Bounded frozen QA wait expired')
    owned=None
    def state():
        row=send_command('pet','status',timeout=1500)
        if row and owned and row.get('pid')!=owned: raise RuntimeError('Unrelated app instance; no further control')
        return row
    def command(name,payload=None):
        if not state(): raise RuntimeError('Own instance is unavailable')
        value=send_command('pet',name,payload,timeout=2500)
        if not value or not value.get('ok'):raise RuntimeError('Own action rejected: '+name)
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.3)
    def snapshot(label):
        path=out/(label+'.json')
        command('qa_desktop',{'action':'save_state','name':label})
        wait(path.exists)
        return json.loads(path.read_text(encoding='utf-8'))
    def import_image(raw,name):
        action('attachment_import',{'name':name,'base64':base64.b64encode(raw).decode('ascii')})
        row=wait(lambda:s if (s:=snapshot('attachment-'+uuid.uuid4().hex[:12])) and not s.get('attachment_busy') else None)
        check('image_import_'+name,bool(row.get('attachments')) and not row.get('attachment_error'))
        return row['attachments'][-1]['id']
    def tool(name,identifier):
        action('route',{'route':'search'})
        started=time.perf_counter();action('tool_run',{'tool':name,**({'arguments':identifier} if isinstance(identifier,dict) else {'query':identifier,'limit':1})})
        result=wait(lambda:s if (s:=snapshot('tool-'+uuid.uuid4().hex[:12])) and not s['search']['busy'] else None,seconds=270 if name=='visual_geoint' else 35)
        report['metrics'][name+'_ms']=round((time.perf_counter()-started)*1000,2)
        check(name+'_actual_results',bool(result['search']['results']) and result['activity'][-1]['status'] in ('complete','partial'))
        time.sleep(.5)  # Allow the queued WebChannel update and paint to settle.
        return result['search']['results'][0]['details']
    process=None;monitor=ProcessSampler(exe)
    try:
        start=time.perf_counter()
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        row=wait(state);owned=row['pid'];check('owned_executable',Path(process_image(owned)).resolve()==exe.resolve())
        wait(lambda:(s:=state()) and s.get('desktop',{}).get('ready'))
        report['metrics']['startup_ms']=round((time.perf_counter()-start)*1000,2)
        command('show_workspace',{'route':'chat'})
        for theme in ('dark','black','light','mono'):
            action('settings_save',{'values':{'ui_theme':theme}})
            def theme_rendered():
                command('qa_desktop',{'action':'dom'});time.sleep(.3)
                current=state()
                if not current or not current.get('desktop',{}).get('dom'):return None
                dom=current['desktop']['dom']
                return dom if dom.get('theme')==theme else None
            dom=wait(theme_rendered,25)
            check('theme_'+theme,dom.get('theme')==theme)
            check('font_'+theme,dom.get('font',{}).get('loaded'))
            check('overflow_'+theme,not dom.get('overflow',True))
            command('qa_snapshot',{'name':'theme-'+theme})
        if args.public_tools:
            profile_data=tool('github_profile','octocat')
            check('keyfree_public_API_in_actual_EXE',profile_data.get('login')=='octocat' and type(profile_data.get('public_repos')) is int)
            rendered=tool('web_read','https://quotes.toscrape.com/js/')
            check('actual_frozen_browser_DOM',rendered.get('reading_method')=='browser_dom' and rendered.get('content_fetched') is True)
            check('actual_frozen_DOM_data','Albert Einstein' in rendered.get('content_text','') and 'J.K. Rowling' in rendered.get('content_text','') and rendered.get('content_length',0)>500)
            report['public_observations']={'github':profile_data,'rendered_page':rendered}
            command('qa_snapshot',{'name':'public-sources'})
        image=Image.new('RGB',(1150,170),'white')
        font=ImageFont.truetype(str(ROOT/'frontend/public/fonts/Manrope-Variable.ttf'),48)
        ImageDraw.Draw(image).text((25,40),'МОСКВА УЛИЦА МИРА',font=font,fill='black')
        data=io.BytesIO();image.save(data,'PNG',optimize=True)
        check('fixture_within_tiny_QA_IPC',len(base64.b64encode(data.getvalue()))<14000)
        image_id=import_image(data.getvalue(),'Синтетическая надпись.png')
        if args.integrations19:
            local=tool('tiktok_timestamp',{'value':'6854717870488702213'})
            check('typed_timestamp_real_UTC',local['date_utc']=='2020-07-29T02:06:13Z')
            roles=tool('role_classify',{'titles':['Chief Technology Officer','Software Engineer']})
            check('packaged_classification_rules_loaded',len(roles['results'])==2)
            dns=tool('mail_dns',{'email':'contact@example.org'})
            check('packaged_real_DNS',dns['domain']=='example.org')
            reference=tool('map_panoramax',{'latitude':48.8584,'longitude':2.2945,'limit':1})
            check('packaged_Panoramax_license',bool(reference['license']) and reference['pixels_downloaded'] is False)
            shadow=tool('shadow_regions',{'datetime_utc':'2024-02-29T13:59:59Z','object_height':10,'shadow_length':5,'max_cells':30})
            check('typed_shadow_real_geometry',shadow['cells_evaluated']>0 and bool(shadow['regions']['features']))
            tool('visual_geoint',{'attachment_id':image_id,'include_ocr':False,'methods':['geoclip_predict','waypoint_predict'],'top_k':3,'samples':8})
            visual=snapshot('visual-geoint-result')
            check('frozen_pipeline_real_candidates',any(row['details'].get('predictions') for row in visual['search']['results']))
            check('frozen_model_uncalibrated_label',all(row['status']=='hypothesis' for row in visual['search']['results'] if row['details'].get('predictions')))
            command('qa_snapshot',{'name':'visual-geoint'})
            graph=tool('evidence_graph',{})
            check('graph_local_evidence_relations',graph['total_entities']>0 and graph['total_relations']>0)
        metadata=tool('image_metadata',image_id)
        check('no_GPS_not_invented',metadata['metadata']['status']=='no_gps_metadata' and metadata['metadata']['gps'] is None)
        ocr=tool('image_ocr',image_id)
        check('real_russian_pixel_OCR','МОСКВА' in ocr.get('text','') and bool(ocr.get('segments')))
        report['ocr_observation']={'text':ocr.get('text'),'languages':ocr.get('languages'),'segments':ocr.get('segments')}
        data=io.BytesIO();exif=Image.Exif();exif[34853]={1:'N',2:(51.0,30.0,0.0),3:'W',4:(0.0,7.0,30.0)}
        Image.new('RGB',(180,120),'white').save(data,'JPEG',exif=exif)
        gps_id=import_image(data.getvalue(),'synthetic-gps.jpg')
        gps=tool('image_metadata',gps_id)['metadata']['gps']
        check('real_GPS_from_EXIF',gps and abs(gps['latitude']-51.5)<1e-8 and abs(gps['longitude']+.125)<1e-8)
        check('metadata_not_authenticated',gps['authenticity_verified'] is False)
        encrypted=list((profile/'attachments').glob('*.gpi'))
        check('encrypted_originals',len(encrypted)==2 and all(not path.read_bytes().startswith((b'\xff\xd8',b'\x89PNG')) for path in encrypted))
        action('window',{'mode':'minimize'});wait(lambda:not state()['desktop']['page_visible'])
        check('background_visibility',True)
        command('show_workspace',{'route':'chat'});wait(lambda:state()['desktop']['page_visible'])
        check('restore_active',state()['desktop']['lifecycle_state']=='Active')
        time.sleep(2);monitor.sample([process.pid]);samples=[]
        for _ in range(6):time.sleep(1);samples.append(monitor.sample([process.pid]))
        report['metrics']['post_tools_idle']=summarize(samples)
        action('route',{'route':'search'})
        ciphertext_before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in encrypted}
        old_root=process.pid
        command('stop');process.wait(timeout=20)
        check('first_run_exit_zero',process.returncode==0)
        owned=None
        with (out/'restart.log').open('wb') as log:
            process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        row=wait(state);owned=row['pid']
        check('restart_owned_executable',Path(process_image(owned)).resolve()==exe.resolve())
        wait(lambda:(s:=state()) and s.get('desktop',{}).get('ready'))
        command('show_workspace',{'route':'chat'})
        def restored_theme():
            command('qa_desktop',{'action':'dom'});time.sleep(.3)
            return state()['desktop']['dom'].get('theme')=='mono'
        wait(restored_theme)
        check('saved_theme_restored_after_restart',True)
        check('encrypted_images_preserved_after_restart',ciphertext_before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in encrypted})
        same_id=import_image(data.getvalue(),'synthetic-gps.jpg')
        check('same_encrypted_image_reopens_after_restart',same_id==gps_id)
        check('GPS_survives_restart',tool('image_metadata',same_id)['metadata']['gps']['latitude']==51.5)
        command('qa_snapshot',{'name':'restart'})
        report['passed']=True;save()
        if args.keep_open:
            print(json.dumps({'ready_for_native_review':True,'pid':owned,'checks':len(report['checks'])}),flush=True)
            process.wait()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:250]);save();raise
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=20)
        if process:
            check('actual_EXE_exit_zero',process.returncode==0)
            time.sleep(.5);check('owned_processes_gone',monitor.sample([process.pid])['process_count']==0)
        monitor.close();save()
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'metrics':report['metrics']},ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
