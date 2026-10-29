"""Measure production chat DOM bounds using explicit UI-only fixtures.

No source observations, tool executions, external APIs or user data are faked.
Fixtures replace this isolated WebChannel snapshot only for visual/layout QA.
Physical Windows scaling and other applications are left unchanged.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists(): raise SystemExit('Choose a new output directory; prior evidence is preserved')
    out.mkdir(parents=True)
    os.environ['APPDATA'] = str(out / 'appdata')
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.desktop_surface import register_desktop_scheme
    from grangerpet.pet import PetWindow
    from grangerpet.theme import apply_theme
    from grangerpet.typography import apply_app_font
    import grangerpet.credentials as credentials
    register_desktop_scheme()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setProperty('web_desktop', True)
    apply_app_font(app)
    apply_theme(app, 'dark')
    profile = out / 'appdata/GrangerPet'
    credentials._STORE = credentials.CredentialsStore(prefix='GrangerPet/ChatLayoutQA/' + uuid.uuid4().hex,
        directory=profile/'vault', data_root=profile)
    credentials._STORE.portable.create('synthetic chat layout QA password', secrets={})
    settings = Settings(ai_provider='none', reduced_motion=True, cursor_reaction=False)
    store = SettingsStore(profile/'settings.json')
    store.save(settings)
    pet = PetWindow(settings, store, interaction_qa=True)
    pet.show()
    panel = pet.panel
    panel.resize(1366, 768)
    panel.show()
    surface = panel.desktop_surface
    bridge = surface.bridge
    checks = []
    cases = []
    fixture = {}
    def wait(predicate, timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate(): return
            QTest.qWait(20)
        raise TimeoutError('Isolated production chat did not settle')
    def settle(ms=140):
        QTest.qWait(ms)
        app.processEvents()
    def js(script):
        values = []
        surface.page().runJavaScript(script, values.append)
        wait(lambda:bool(values))
        return values[0]
    def check(name, passed, **data):
        checks.append({'name':name,'passed':bool(passed),**data})
    def publish():
        bridge.publish(force=True)
        settle()
    def dock(opened):
        selector = '[aria-label="Показать Гермиону и источники"]' if opened else '[aria-label="Свернуть панель Гермионы"]'
        js('document.querySelector(' + json.dumps(selector) + ')?.click()')
        settle()
    sources = [{'evidence_id':f'ev_{index:020d}', 'title':f'UI FIXTURE ONLY · Источник {index}',
        'url':f'https://example.org/layout-fixture/{index}','kind':'page','status':'read',
        'details':{'content_fetched':True},'excerpt':'Синтетическая выдержка для проверки размещения. Не OSINT-результат.'} for index in range(120)]
    prose = [{'id':'layout-user','role':'user','text':'UI FIXTURE ONLY: проверь публичные сведения.'},
        {'id':'layout-model','role':'model','text':'## Проверенные сведения\n\nПервый обычный абзац синтетического ответа.\n\nВторой абзац с пояснением ограничений.\n\n- Источник не доказывает личность.\n- Отделяем наблюдение от гипотезы.','sources':sources}]
    table = '| Источник | Наблюдение | Ограничение |\n| --- | --- | --- |\n' + '\n'.join(f'| Запись {i} | Синтетический текст | Не реальная находка |' for i in range(25))
    code = '```python\n' + ('public_fixture = "' + 'x'*240 + '"\n')*8 + '```\n\nПояснение после блока кода.'
    image = {'id':'img_'+'a'*64,'name':'UI fixture.png','format':'PNG','mime':'image/png','bytes':1024,'width':300,'height':100,'sha256':'a'*64}
    def scenario(name):
        fixture.update(messages=deepcopy(prose), busy=False, activity=[], attachments=[], attachment_busy=False,
            investigation={'canResume':False}, task_sources=sources, evidence=sources)
        if name=='empty': fixture['messages']=[];fixture['task_sources']=[]
        elif name=='table': fixture['messages']=[{'id':'table','role':'model','text':table}]
        elif name=='code': fixture['messages']=[{'id':'code','role':'model','text':code}]
        elif name=='long': fixture['messages']=[{'id':f'long-{i}','role':'model' if i%2 else 'user','text':f'UI FIXTURE {i}. Только проверка длинного списка.'} for i in range(1000)]
        elif name=='active': fixture.update(busy=True,activity=[{'id':'layout-call','tool':'web_read','status':'running','summary':'UI FIXTURE: чтение публичного источника'}])
        elif name=='paused': fixture['investigation']={'id':'ui-fixture-not-an-investigation','status':'paused','canResume':True,'stop_reason':'Повторяющиеся проверки не дали новых данных. План сохранён.'}
        elif name=='attachment': fixture['attachments']=[image]
        publish()
        if name=='sources':
            js("document.querySelector('.sources-trigger[aria-expanded=false]')?.click()")
            settle(220)
    def measure(label):
        value = json.loads(js('''JSON.stringify((()=>{
          const rect=(node)=>{if(!node)return null;const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
          const one=(s)=>rect(document.querySelector(s));
          const scroll=document.querySelector('.chat-scroll');
          return {width:innerWidth,height:innerHeight,theme:document.documentElement.dataset.theme,
            documentOverflow:document.documentElement.scrollWidth>innerWidth,
            main:one('.main-workspace'),header:one('.workspace-header'),route:one('.route-chat'),
            conversation:one('.conversation'),scroll:one('.chat-scroll'),composerZone:one('.composer-zone'),composer:one('.composer-content'),
            input:one('.composer textarea'),model:one('.message-model .message-content'),sources:one('.sources-group'),
            activity:one('.activity-block'),paused:one('.task-status'),sidebar:one('.sidebar'),dock:one('.hermione-sidebar'),
            selectedImages:document.querySelectorAll('.composer-zone .attachment-preview').length,
            mountedMessages:document.querySelectorAll('[data-message-id]').length,
            sourceCards:document.querySelectorAll('.message .source-card').length,
            childScrollports:[...document.querySelectorAll('.chat-scroll *')].filter(n=>['auto','scroll'].includes(getComputedStyle(n).overflowY)&&n.scrollHeight>n.clientHeight+1).map(n=>n.className),
            scrollHeight:scroll.scrollHeight,clientHeight:scroll.clientHeight,
            sourcesOverflow:document.querySelector('.sources-list') ? getComputedStyle(document.querySelector('.sources-list')).overflowY : null,
            formatsPermanent:!!document.querySelector('.attachment-actions small')};
        })())'''))
        case_checks = {
            'document_bounds':not value['documentOverflow'],
            'shared_content_width':abs(value['conversation']['x']-value['composer']['x'])<1.2 and abs(value['conversation']['width']-value['composer']['width'])<1.2,
            'composer_inside_route':value['composerZone']['bottom']<=value['route']['bottom']+1 and value['composerZone']['x']>=value['main']['x']-1 and value['composerZone']['right']<=value['main']['right']+1,
            'one_transcript_scrollport':not value['childScrollports'],
            'transcript_has_room':value['scroll']['height']>25,
            'composer_below_transcript':value['scroll']['bottom']<=value['composerZone']['y']+1,
            'no_format_row':not value['formatsPermanent'],
        }
        if value['model']:
            case_checks['text_input_alignment']=abs(value['model']['x']-value['input']['x'])<1.2
            if value['sources']: case_checks['source_text_alignment']=abs(value['sources']['x']-value['model']['x'])<1.2
        if value['dock']: case_checks['dock_not_over_composer']=value['composerZone']['right']<=value['dock']['x']+1
        else: case_checks['no_phantom_column']=abs(value['main']['right']-value['width'])<1.2
        for key,passed in case_checks.items(): check(label+'_'+key,passed)
        cases.append({'case':label,'checks':case_checks,'dom':value})
    try:
        wait(lambda:bridge.ui_ready)
        fixture.update(bridge.snapshot())
        fixture.update(route='chat',conversation_id='ui-layout-fixture', connection={**fixture['connection'],'canSend':True,'model':'UI FIXTURE · no API calls'})
        bridge.snapshot=lambda:deepcopy(fixture)
        scenario('prose')
        for theme in ('dark','black','light','mono'):
            fixture['settings']['ui_theme']=theme
            apply_theme(app,theme)
            publish()
            for width,height in ((760,560),(1280,720),(1366,768),(1600,900),(1920,1080)):
                panel.resize(width,height)
                for zoom in (.8,1,1.25,1.5):
                    surface.setZoomFactor(zoom);settle()
                    for opened in (False,True):
                        dock(opened)
                        measure(f'{theme}_{width}x{height}_{zoom}_dock{opened}')
            if theme in ('dark','light'):
                panel.grab().save(str(out/f'{theme}-prose.png'))
        for width,height,zoom in ((1366,768,1),(760,560,1.5)):
            panel.resize(width,height);surface.setZoomFactor(zoom);settle()
            for theme in ('dark','black','light','mono'):
                fixture['settings']['ui_theme']=theme;publish()
                for opened in (False,True):
                    dock(opened)
                    for name in ('empty','prose','table','code','long','sources','active','paused','attachment'):
                        scenario(name)
                        measure(f'{theme}_{width}x{height}_{zoom}_dock{opened}_{name}')
                        if width==1366 and theme=='light' and opened and name in ('sources','paused','attachment'):
                            panel.grab().save(str(out/f'light-{name}.png'))
                        if name=='long':check('virtual_long_mount_'+str(len(cases)),cases[-1]['dom']['mountedMessages']<40)
                        if name=='sources':check('bounded_sources_'+str(len(cases)),cases[-1]['dom']['sourceCards']==6)
        panel.grab().save(str(out/'narrow-final.png'))
        pet.grab().save(str(out/'native-pet.png'))
    finally:
        pet.shutdown();panel.close();app.processEvents()
        report={'method':'Production PetWindow, QtWebEngine, WebChannel and built React. Explicit UI-only synthetic snapshots; no external requests, no real investigations, credentials, photos or history. Physical Windows DPI unchanged.',
            'native_dpr':app.primaryScreen().devicePixelRatio(),'physical_dpi_settings_changed':False,
            'logical_window_sizes_are_not_monitor_resolutions':True,'cases':cases,'checks':checks,'passed':bool(checks) and all(c['passed'] for c in checks)}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(cases),'checks':len(checks),'failures':[r['name'] for r in checks if not r['passed']]}))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
