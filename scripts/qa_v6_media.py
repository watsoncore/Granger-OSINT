"""Image import, graph gestures, and desktop navigation in an owned Windows window."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.qa_clean_release import QaFailure, isolated_environment, validate_report_path, wait_for
from scripts.qa_v5_acceptance import V5Session, digest

URL = 'https://www.w3.org/Icons/w3c_home.png'
PATH_LABEL = 'Путь на диске или публичный HTTPS-адрес'


def run(exe, report, shots, source=False):
    from PIL import Image, ImageDraw, ImageStat
    from PySide6.QtCore import QCoreApplication
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.geoint_tools import attachment_store
    from grangerpet.research_canvas import CanvasStore, merge_evidence, new_document

    app = QCoreApplication.instance() or QCoreApplication([])
    report.parent.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    result = {'passed':False, 'origin':'native-source' if source else 'frozen-Windows-EXE',
              'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
              'checks':[], 'captures':[]}

    def save():
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

    def check(name, condition):
        result['checks'].append({'name':name,'passed':bool(condition)})
        save()
        print(json.dumps(result['checks'][-1]), flush=True)
        if not condition:
            raise QaFailure(name)

    with tempfile.TemporaryDirectory(prefix='.granger-qa-v6-', dir=ROOT) as name:
        directory = Path(name)
        with isolated_environment(directory):
            os.environ['QT_SCALE_FACTOR'] = '1'
            SettingsStore().save(Settings(source_root=str(ROOT), ai_provider='none', cursor_reaction=False, reduced_motion=True))
            store = CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            originals = attachment_store(directory/'appdata/GrangerPet')
            for file, dimensions, colors in (
                ('drop.png', (1480, 820), ('#202d46','#e5c18d')),
                ('clipboard.png', (820, 1480), ('#243e3b','#c3ded7')),
                ('path.png', (760, 760), ('#30274c','#d9c5ed')),
            ):
                with Image.new('RGB', dimensions, colors[0]) as fixture:
                    drawing = ImageDraw.Draw(fixture)
                    for index in range(9):
                        x,y = dimensions[0]*index/10,dimensions[1]*index/10
                        drawing.rectangle((x+35,y+35,x+130,y+110),fill=colors[1])
                    drawing.text((36,16), 'GRANGER LAB / '+file.upper(), fill=colors[1])
                    fixture.save(directory/file)
            social = new_document('QA · Публичный профиль')
            row = normalize_evidence({'id':'v6-profile','type':'profile','platform':'github','title':'octocat',
                'url':'https://github.com/octocat','details':{'login':'octocat'},'status':'source_reported'},'github_profile','octocat')
            merge_evidence(social,[row])
            social = store.save(social, 0)
            profile = next(node for node in social['entities'] if node['type']=='public_profile')
            session = V5Session(exe,directory,source)

            def capture(label, suffix='-search.png'):
                session.command('qa_snapshot', {'name':label})
                path = directory/(label+suffix)
                def complete():
                    try:
                        with Image.open(path) as capture:
                            return min(capture.size)>200 and max(ImageStat.Stat(capture.convert('RGB')).stddev)>5
                    except (OSError,ValueError):return False
                wait_for(complete, 10)
                target = shots/(label+'.png')
                target.write_bytes(path.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
                save()

            def image_count(count):
                def current():
                    doc=session.document()
                    return doc if sum(node['type']=='image' for node in doc.get('entities',[]))==count else None
                return wait_for(current,30)

            def file_input(value):
                session.fill(PATH_LABEL,value)
                session.click('Загрузить')

            def canvas_point(x,y):
                area=session.metrics()['canvas']
                return area,[area['x']+area['width']*x,area['y']+area['height']*y]

            def evidence_unchanged():
                return digest(store.load(social['id'])['evidence']) == digest(social['evidence'])

            try:
                started=time.monotonic()
                session.start(0)
                result['startup_owned_workspace_seconds']=round(time.monotonic()-started,3)
                for label, heading in (
                    ('Гермиона','Диалог с Гермионой'), ('Поиск','Поиск и OSINT-инструменты'),
                    ('История','История'), ('Canvas','Canvas'), ('Настройки','Настройки'),
                ):
                    started=time.monotonic();session.click(label)
                    state=wait_for(lambda:dom if heading in (dom:=session.dom()).get('headings',[]) else None)
                    result.setdefault('navigation_observed_seconds',{})[label]=round(time.monotonic()-started,3)
                    check('native_route_'+label, not state.get('overflow'))
                    capture({'Гермиона':'chat','Поиск':'search','История':'history','Canvas':'text-canvas','Настройки':'settings'}[label])
                session.action('input',{'kind':'key','key':'k','ctrl':True})
                check('command_palette_native_keyboard',bool(wait_for(lambda:session.find('Поиск команд')[0],12)))
                capture('command-palette')
                session.click('Закрыть быстрый переход')

                session.action('route',{'route':'search'})
                session.click('Моё полотно');session.click('Новое')
                owner=wait_for(lambda:session.document().get('id'))
                session.ensure_expanded()
                session.viewport_patch({'x':320,'y':200,'scale':.8})
                area,at=canvas_point(.29,.40)
                expected=((at[0]-area['x']-320)/.8,(at[1]-area['y']-200)/.8)
                session.action('qa_media_input',{'kind':'drop','name':'drop.png','at':at})
                first=image_count(1);node=first['entities'][0];identifier=node['id']
                original=(directory/'drop.png').read_bytes()
                position=first['view']['positions'][identifier]
                check('qt_drop_exact_world_position_and_bytes',abs(position['x']-expected[0])<3 and abs(position['y']-expected[1])<3
                      and position.get('pinned') and originals.read_bytes(node['attributes']['attachment_id'])==original)
                check('stored_media_has_no_inline_thumbnail', 'thumbnail' not in store.load(owner)['entities'][0]['attributes']['media'])
                wait_for(lambda:int(session.metrics()['canvas'].get('drawnImages',0))>=1,20)
                capture('media-drop')
                session.select(identifier)
                frame=session.metrics()['canvas']
                bounds=session.visible_node(identifier)
                corner=[frame['x']+bounds['x']+bounds['width']/2-8,frame['y']+bounds['y']+bounds['height']/2-8]
                session.action('input',{'kind':'drag','at':corner,'to':[corner[0]+37,corner[1]+22]})
                check('media_resize_saved',bool(wait_for(lambda:session.document()['view'].get('card_sizes',{}).get(identifier),18)))
                _,at=canvas_point(.70,.45)
                session.action('input',{'kind':'click','at':at})
                session.action('qa_media_input',{'kind':'clipboard','name':'clipboard.png'})
                clipboard_node=next(item for item in image_count(2)['entities'] if item['id']!=identifier)
                metadata=clipboard_node['attributes']['media']
                check('windows_clipboard_ctrl_v_imports_bitmap',(metadata['width'],metadata['height'])==(820,1480))
                wait_for(lambda:int(session.metrics()['canvas'].get('drawnImages',0))>=2,20)
                capture('media-clipboard')

                session.click('Добавить изображение');file_input(str(directory/'path.png'))
                check('local_path_import',any(item['label']=='path.png' for item in image_count(3)['entities']))
                session.click('Добавить изображение');file_input(URL)
                remote=next(item for item in image_count(4)['entities'] if item['attributes']['media'].get('source_url')==URL)
                remote_reference=remote['attributes']['media']
                check('https_import_pins_verified_original',remote_reference['final_url'].startswith('https://www.w3.org/')
                      and hashlib.sha256(originals.read_bytes(remote_reference['id'])).hexdigest()==remote_reference['sha256'])

                saved=store.load(owner)
                session.select(identifier);bounds=session.visible_node(identifier);frame=session.metrics()['canvas']
                session.action('input',{'kind':'double_click','at':[frame['x']+bounds['x'],frame['y']+bounds['y']]})
                check('native_double_click_opens_full_viewer',bool(wait_for(
                    lambda:button if (button:=session.find('Оригинал')[0]) and not button['disabled'] and button.get('hit',True) else None,12)))
                capture('media-viewer')
                session.click('Оригинал');capture('media-original','-original-0.png')
                session.stop()

                session.start(1);session.action('route',{'route':'search'});session.click('Моё полотно')
                session.open_document(owner);reopened=store.load(owner)
                check('restart_preserves_media_positions_sizes_and_originals',
                      reopened['entities']==saved['entities'] and reopened['view']['positions']==saved['view']['positions']
                      and reopened['view']['card_sizes']==saved['view']['card_sizes']
                      and originals.read_bytes(node['attributes']['attachment_id'])==original)
                session.select(remote['id']);session.click('Сведения');session.click('Открыть изображение '+remote['label'])
                wait_for(lambda:'Целостность и метаданные' in session.dom()['text'],15)
                check('reopened_remote_uses_saved_attachment',session.document()['id']==owner)
                session.click('Закрыть изображение')
                session.open_document(social['id']);session.select(profile['id']);session.click('Сведения')
                session.click('Прикрепить фото');file_input(str(directory/'path.png'))
                linked=wait_for(lambda:next((entry['attributes'].get('image_attachments') for entry in session.document()['entities'] if entry['id']==profile['id']),None),25)
                check('attachment_dedup_and_evidence_preserved',len(linked)==1 and evidence_unchanged())
                capture('media-attached')
                session.click('Отвязать path.png')
                wait_for(lambda:not next(item for item in session.document()['entities'] if item['id']==profile['id'])['attributes'].get('image_attachments'))
                check('detach_preserves_evidence_and_encrypted_original',evidence_unchanged() and bool(originals.read_bytes(linked[0]['id'])))

                session.click('Встроить')
                result['viewports']=[]
                for width,height in ((1366,768),(1600,900),(1920,1080),(2560,1440)):
                    session.command('qa_window_mode',{'mode':'size','size':[width,height]})
                    time.sleep(.3)
                    dom=session.dom()
                    result['viewports'].append({'requested_qt_logical':[width,height],'web_view':[dom['width'],dom['height']],
                        'native_dpr':session.status().get('dpr')})
                    check('responsive_window_'+str(width),not dom['overflow'] and bool(session.find('Быстрый переход')[0]))
                session.command('qa_window_mode',{'mode':'maximized'})
                for mode in ('reduced','off','full'):
                    appearance=json.dumps({'appStyle':'glass','effects':mode})
                    session.action('settings_save',{'values':{'workspace_appearance':appearance,'ui_effects':mode}})
                    check('effects_mode_'+mode,bool(wait_for(lambda:session.dom().get('effects')==mode,12)))
                session.stop()
                os.environ['QT_SCALE_FACTOR']='2'
                session.start(2)
                session.action('route',{'route':'search'});session.click('Моё полотно');session.open_document(owner)
                session.click('Показать всё');session.idle()
                frame=session.metrics()['canvas']
                result['qt_scale_200']={'observed_native_dpr':session.status().get('dpr'),'canvas':[frame['width'],frame['height']]}
                check('qt_scale_200_canvas_readable',int(frame['drawnLabels'])>0 and bool(session.visible_node(identifier)))
                capture('graph-qt-200')
                result['passed']=True
                save()
            except Exception as error:
                result['failure']=str(error)[:160] if isinstance(error,QaFailure) else type(error).__name__
                save()
                try:capture('v6-failed')
                except Exception:pass
                raise
            finally:
                session.stop()
    result['temporary_profile_removed']=not directory.exists()
    save()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--screenshots',type=Path,required=True)
    parser.add_argument('--source',action='store_true')
    args=parser.parse_args()
    validate_report_path(args.report);validate_report_path(args.screenshots)
    result=run(args.exe.resolve(),args.report.resolve(),args.screenshots.resolve(),args.source)
    print(json.dumps({'passed':result['passed'],'checks':len(result['checks'])}),flush=True)


if __name__=='__main__':
    main()
