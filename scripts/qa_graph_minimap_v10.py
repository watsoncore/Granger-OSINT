"""Focused native safe-zone regression: an open dock must move the minimap, never the camera."""
import argparse
import base64
import io
import json
import hashlib
from pathlib import Path
import sys
import os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session
from scripts.qa_canvas_stress import synthetic_document


def run(exe,out,source=False):
    if source:
        from scripts.build_release import build_frontend
        build_frontend(ROOT,os.environ.copy())
    from PIL import Image
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    out.mkdir(parents=True,exist_ok=False)
    report={'passed':False,'origin':'native-source' if source else 'frozen-EXE',
            'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[],'geometry':[]}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)});save();print(json.dumps(report['checks'][-1]),flush=True)
        if not value:raise QaFailure(name)
    with isolated_environment(out):
        SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
        data=io.BytesIO();Image.new('RGB',(64,64),'#427277').save(data,'PNG')
        store=CanvasStore(InvestigationJournal(out/'appdata/GrangerPet/investigations'))
        doc=store.save(synthetic_document(50,'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode()),0)
        s=V7Session(exe,out,source)
        def geometry(name):
            s.idle();g=wait_for(lambda:s.dom().get('graphLayout'),8)
            report['geometry'].append({'name':name,**g});save()
            check(name+'_no_overlap',not g['overlaps'] and not g['controlOverlaps'])
            s.command('qa_snapshot',{'name':name})
            return g
        try:
            s.start(0);s.click('Поиск');s.click('Мой граф');s.action('research_canvas_open',{'id':doc['id']})
            wait_for(lambda:s.document().get('id')==doc['id']);s.idle()
            s.click('Настроить граф');s.click('Фильтры')
            inputs=[e for e in s.dom()['elements'] if e.get('type')=='checkbox' and e.get('hit')]
            check('two_filter_checkboxes',len(inputs)==2)
            b=inputs[1];s.action('input',{'kind':'click','at':[b['x']+b['width']/2,b['y']+b['height']/2]})
            s.action('input',{'kind':'key','key':'escape'});s.click('Настроить граф')
            for style in ('glass','minimal'):
                s.action('settings_save',{'values':{'workspace_appearance':json.dumps({'graphStyle':style})}})
                before=s.metrics()['canvas'];g=geometry(style+'-closed')
                check(style+'_minimap_present',any(row['name']=='minimap' for row in g['boxes']))
                s.click('Показать редактор');g=geometry(style+'-inspector')
                after=s.metrics()['canvas']
                check(style+'_camera_unchanged',all(before.get(k)==after.get(k) for k in ('width','height','zoom','panX','panY')))
                s.command('qa_window_mode',{'mode':'fullscreen'});s.idle()
                inspector=next(row for row in s.dom()['graphLayout']['boxes'] if row['name']=='research-inspector')
                s.action('input',{'kind':'right_click','at':[inspector['x']-8,inspector['y']+80]})
                popup=wait_for(lambda:s.find('Новый объект здесь')[0],8)
                s.command('qa_snapshot',{'name':style+'-context-inspector'})
                check(style+'_context_above_inspector',popup.get('hit'))
                s.action('input',{'kind':'key','key':'escape'})
                check(style+'_context_escape_keeps_fullscreen',s.snapshot()['window']['fullscreen'] and not s.find('Новый объект здесь')[0])
                s.command('qa_window_mode',{'mode':'maximized'})
                s.click('Скрыть редактор');geometry(style+'-restored')
            report['passed']=True;save()
        finally:s.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',action='store_true');a=p.parse_args();run(a.exe.resolve(),a.output.resolve(),a.source)
