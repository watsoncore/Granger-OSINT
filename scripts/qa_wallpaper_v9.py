"""Measure known wallpaper geometry in actual owned Qt/WebEngine windows."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_appearance_v8 import AppearanceSession


def run(exe,output,*,source=False):
    from PIL import Image,ImageDraw,ImageChops
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore,new_document
    from grangerpet.geoint.images import AttachmentStore
    from grangerpet.credentials import seal_bytes,open_bytes
    from grangerpet.appearance import normalize_appearance

    app=QCoreApplication.instance() or QCoreApplication([])
    output.mkdir(parents=True,exist_ok=False)
    report={'origin':'native-source' if source else 'frozen-Windows-EXE',
            'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
            'data_origin':'generated_geometry_fixtures','cases':[],'passed':False}
    def save():
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='profile-',dir=output) as name:
        directory=Path(name)
        with isolated_environment(directory):
            settings=SettingsStore()
            profile=directory/'appdata/GrangerPet'
            store=CanvasStore(InvestigationJournal(profile/'investigations'))
            images=AttachmentStore(profile/'wallpapers',seal=seal_bytes,open_sealed=open_bytes)
            fixtures=[]
            for title,size,format,orientation in (
                ('16x9-4k',(3840,2160),'PNG',1),('4x3',(1200,900),'JPEG',1),
                ('square',(1000,1000),'WEBP',1),('portrait',(900,1400),'JPEG',1),
                ('exif-rotated',(900,1200),'JPEG',6),
                ('4k-texture',(3840,2160),'JPEG',1),
            ):
                image=Image.effect_noise(size,32).convert('RGB') if title=='4k-texture' else Image.new('RGB',size,'#263847')
                with image:
                    draw=ImageDraw.Draw(image)
                    radius=min(size)*.1
                    draw.ellipse((size[0]/2-radius,size[1]/2-radius,size[0]/2+radius,size[1]/2+radius),fill='#00df30')
                    data=io.BytesIO()
                    exif=Image.Exif();exif[274]=orientation
                    image.save(data,format,exif=exif)
                original=data.getvalue()
                attachment=images.import_bytes(original,title)
                document=store.save(new_document('V9 QA · '+title),0)
                fixtures.append({'name':title,'size':list(reversed(size)) if orientation==6 else list(size),
                                 'id':attachment['id'],'canvas_id':document['id'],
                                 'original_sha256':hashlib.sha256(original).hexdigest()})
            overrides={item['canvas_id']:{'source':'image','image':item['id'],'fit':'contain',
                         'quality':'original','dim':0,'blur':0,'opacity':100} for item in fixtures}
            initial=Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True)
            initial.workspace_appearance=normalize_appearance(json.dumps({'theme':'azure','glow':0,'overrides':overrides}))
            settings.save(initial)
            session=AppearanceSession(exe,directory,source)

            def snapshot(label,fixture):
                session.idle()
                metrics=wait_for(lambda: value if (value:=session.metrics().get('wallpaper')) and
                    value.get('loaded')=='true' and value.get('current')=='true' else None,45)
                session.command('qa_snapshot',{'name':label})
                path=directory/(label+'-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:image.verify()
                        return True
                    except (OSError,ValueError):return False
                wait_for(ready,12)
                target=output/(label+'.png')
                target.write_bytes(path.read_bytes())
                with Image.open(target) as image:
                    red,green,blue=image.convert('RGB').split()
                    mask=ImageChops.multiply(green.point(lambda v:255 if v>175 else 0),
                         ImageChops.multiply(red.point(lambda v:255 if v<55 else 0),blue.point(lambda v:255 if v<90 else 0)))
                    bounds=mask.getbbox()
                if not bounds:raise QaFailure('wallpaper_circle_not_visible')
                width,height=bounds[2]-bounds[0],bounds[3]-bounds[1]
                case={'name':label,'wallpaper':fixture['name'],'format_geometry':fixture['size'],
                      'metrics':metrics,'circle_pixels':[width,height],
                      'circle_aspect_error':abs(width/height-1),
                      'original_bytes_preserved':hashlib.sha256(images.read_bytes(fixture['id'])).hexdigest()==fixture['original_sha256'],
                      'screenshot_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
                case['passed']=case['circle_aspect_error']<.02 and case['original_bytes_preserved']
                report['cases'].append(case);save()
                if not case['passed']:raise QaFailure('wallpaper_geometry_changed')
                print(json.dumps({'name':label,'circle':case['circle_pixels'],'dpr':metrics['dpr'],'passed':case['passed']}),flush=True)

            def graph(item):
                if not session.find('Встроить')[0] and not session.find('Развернуть')[0]:
                    session.click('Поиск');session.click('Мой граф')
                session.open_document(item['canvas_id'])

            def fit(label=None,quality=None):
                session.click('Встроить')
                session.click('Настройки');session.click('Оформление')
                session.click('Обои графа',role='button')
                # The existing investigation override is selected explicitly.
                session.pick('Где использовать','V9 QA · 16x9-4k','V9 QA · 16x9-4k')
                if label:session.pick('Расположение',label,label)
                if quality:session.pick('Качество обоев',quality,quality)
                session.click('Применить')
                time.sleep(.4)
                session.click('Поиск');session.click('Мой граф')
                session.open_document(fixtures[0]['canvas_id'])

            try:
                os.environ['QT_SCALE_FACTOR']='1'
                session.start(0)
                graph(fixtures[0])
                session.command('qa_window_mode',{'mode':'size','size':[1366,900]})
                time.sleep(.5)
                snapshot('contain-1366x900',fixtures[0])
                for label,key in (('Заполнить','cover'),('Оригинальный размер · 100%','original'),('Вписать','contain')):
                    fit(label)
                    snapshot(key+'-windowed',fixtures[0])
                    session.command('qa_window_mode',{'mode':'fullscreen'})
                    wait_for(lambda:session.snapshot()['window']['fullscreen'])
                    snapshot(key+'-fullscreen',fixtures[0])
                    session.command('qa_window_mode',{'mode':'windowed'})
                    wait_for(lambda:not session.snapshot()['window']['fullscreen'])
                for quality,key in (('Автоматическое','auto'),('Высокое','high')):
                    fit(quality=quality)
                    snapshot(key+'-dpr125',fixtures[0])
                fit(quality='Оригинальное')
                for fixture in fixtures[1:]:
                    graph(fixture)
                    snapshot(fixture['name'],fixture)
                session.stop()
                os.environ['QT_SCALE_FACTOR']='1.5'
                session.start(1)
                graph(fixtures[0])
                fit(quality='Автоматическое')
                for width,height in ((1280,800),(1920,1080)):
                    session.command('qa_window_mode',{'mode':'size','size':[width,height]})
                    time.sleep(.5)
                    snapshot('dpr150-'+str(width),fixtures[0])
                result=store.load(fixtures[0]['canvas_id'])
                report['wallpaper_did_not_create_graph_entities']=not result['entities']
                report['passed']=all(case['passed'] for case in report['cases']) and report['wallpaper_did_not_create_graph_entities']
            except BaseException as error:
                report.update(error_type=type(error).__name__,error=str(error)[:180])
                raise
            finally:
                session.stop();save()
    report['temporary_profile_removed']=not directory.exists();save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',action='store_true')
    args=parser.parse_args()
    run(args.exe.resolve(),args.output.resolve(),source=args.source)
