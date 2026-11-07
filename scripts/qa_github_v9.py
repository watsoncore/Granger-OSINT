"""Fresh public Maigret → GitHub → saved graph acceptance through native controls."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session


def run(exe,output,*,source=False):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image,ImageStat
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore

    app=QCoreApplication.instance() or QCoreApplication([])
    output.mkdir(parents=True,exist_ok=False)
    report={'origin':'native-source' if source else 'frozen-Windows-EXE',
            'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
            'mock':False,'checks':[],'executions':[],'passed':False}
    def save():
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,condition):
        report['checks'].append({'name':name,'passed':bool(condition)});save()
        print(json.dumps(report['checks'][-1]),flush=True)
        if not condition:raise QaFailure(name)
    with tempfile.TemporaryDirectory(prefix='profile-',dir=output) as name:
        directory=Path(name)
        with isolated_environment(directory):
            settings=Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True,
                              workspace_appearance=json.dumps({'theme':'violet','glow':18,'reflection':3,'selectionBorder':1}))
            SettingsStore().save(settings)
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            session=V7Session(exe,directory,source)

            def capture(label):
                session.command('qa_snapshot',{'name':label})
                path=directory/(label+'-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:
                            return min(image.size)>300 and max(ImageStat.Stat(image.convert('RGB')).stddev)>5
                    except (ValueError,OSError):return False
                wait_for(ready,12)
                (output/(label+'.png')).write_bytes(path.read_bytes())

            def choose(node,label):
                session.select(node['id']);session.click('Исследовать')
                session.click(label)

            def execute(tool,*,double_click=None):
                previous=(session.canvas().get('preview') or {}).get('token')
                session.click('Выполнить → просмотр')
                if double_click:
                    session.action('input',{'kind':'double_click','at':session.point(double_click)})
                def finished():
                    state=session.snapshot();preview=state.get('research_canvas',{}).get('preview') or {}
                    if preview.get('tool')==tool and preview.get('token')!=previous and not preview.get('running') and not state['search']['busy']:
                        return preview
                preview=wait_for(finished,210)
                report['executions'].append({key:preview.get(key) for key in ('tool','status','limitations','error_code','request_counts')})
                report['executions'][-1]['records']=len(preview['results']);save()
                session.click('Результаты для добавления')
                return preview

            def insert(preview):
                count=len(preview['results'])
                if not count:return
                session.click(f'Выбрать все ({count})');session.click(f'Добавить выбранные ({count})')
                wait_for(lambda:(session.canvas().get('insertion') or {}).get('preview_token')==preview['token'],90)
                session.idle()

            def activation(identifier,slow=False):
                point=session.point(identifier)
                if slow:
                    session.action('input',{'kind':'click','at':point})
                    time.sleep(.06)
                    session.action('input',{'kind':'click','at':point})
                else:session.action('input',{'kind':'double_click','at':point})
                session.idle()
                check('profile_activation_preserves_graph_and_opens_details',
                      session.process.poll() is None and not session.canvas().get('error')
                      and not session.find('Закрыть изображение')[0])

            try:
                session.start(0);session.click('Поиск');session.action('tools_refresh')
                wait_for(lambda:not session.snapshot().get('toolsChecking'),90)
                session.click('Мой граф')
                session.action('research_canvas_new',{'title':'V9 QA · Публичный GitHub'})
                wait_for(lambda:session.document().get('title')=='V9 QA · Публичный GitHub' and not session.canvas().get('busy'))
                session.ensure_expanded()
                username=session.create_v7('Никнейм','Никнейм','solvnox')
                choose(username,'Найти публичные профили')
                session.pick('Режим Maigret','Быстрый','quick')
                preview=execute('username_maigret')
                session.click('Галерея')
                capture('maigret-gallery')
                insert(preview)
                github=next((node for node in session.document()['entities'] if node['type']=='public_profile'
                             and node['attributes'].get('url','').rstrip('/')=='https://github.com/solvnox'),None)
                report['github_found_in_fresh_maigret']=github is not None;save()
                if not github:
                    github=session.create_v7('Профиль','Ссылка на профиль','https://github.com/solvnox')
                    report['github_profile_created_manually_after_partial_maigret']=True;save()
                session.select(github['id']);activation(github['id']);activation(github['id'],slow=True)
                capture('profile-details')
                profile_canvas_id=session.document()['id']
                session.click('Встроить');session.click('История');session.click('Поиск');session.click('Мой граф')
                session.open_document(profile_canvas_id);session.ensure_expanded()
                session.select(github['id']);activation(github['id'])
                choose(github,'Изучить GitHub-профиль')
                first=store.load(session.document()['id'])
                preview=execute('github_profile',double_click=github['id'])
                check('github_returned_real_observations',preview['status'] in ('complete','partial') and bool(preview['results']))
                session.click('Таблица')
                capture('github-table')
                insert(preview)
                saved=store.load(session.document()['id'])
                check('github_insert_preserves_previous_evidence',
                      {row['evidence_id'] for row in first['evidence']}<={row['evidence_id'] for row in saved['evidence']})
                repositories=[node for node in saved['entities'] if node['type']=='repository']
                check('github_repository_saved',bool(repositories))
                check('github_repository_visible_in_identity_projection',
                      int(session.metrics()['canvas']['modelNodes'])>=len([node for node in saved['entities'] if node['type']=='public_profile'])+2)
                session.select(repositories[0]['id'])
                capture('github-repository-in-graph')
                session.click('Закрыть редактор')
                session.click('Чистое расследование');capture('github-clean-mode');session.click('Полный набор')
                final=deepcopy(saved);identifier=saved['id']
                session.stop();session.start(1);session.click('Поиск');session.click('Мой граф')
                session.open_document(identifier);session.select(github['id']);activation(github['id'])
                reopened=store.load(identifier)
                differences={}
                for key in ('entities','relations','evidence'):
                    if reopened[key]==final[key]:continue
                    field='evidence_id' if key=='evidence' else 'id'
                    before={row[field]:row for row in final[key]}
                    after={row[field]:row for row in reopened[key]}
                    differences[key]={'added':len(after.keys()-before.keys()),'missing':len(before.keys()-after.keys()),
                        'changed_fields':[name for identifier in before.keys()&after.keys()
                                          for name in set(before[identifier])|set(after[identifier])
                                          if before[identifier].get(name)!=after[identifier].get(name)]}
                    if key=='entities':
                        differences[key]['changed_attributes']=[name for identifier in before.keys()&after.keys()
                            for name in set(before[identifier].get('attributes',{}))|set(after[identifier].get('attributes',{}))
                            if before[identifier].get('attributes',{}).get(name)!=after[identifier].get('attributes',{}).get(name)]
                report['restart_differences']=differences;save()
                if differences:
                    (output/'before-restart-private.json').write_text(json.dumps(final,ensure_ascii=False),encoding='utf-8')
                    (output/'after-restart-private.json').write_text(json.dumps(reopened,ensure_ascii=False),encoding='utf-8')
                check('github_findings_survive_restart',all(reopened[key]==final[key] for key in ('entities','relations','evidence')))
                capture('github-after-restart')
                report['passed']=True;save()
            except BaseException as error:
                report.update(error_type=type(error).__name__,error=str(error)[:180]);save()
                (output/'failed-dom-private.json').write_text(json.dumps(session.dom(),ensure_ascii=False),encoding='utf-8')
                capture('failed-layout-private')
                for path in directory.glob('process-*.log'):(output/path.name).write_bytes(path.read_bytes())
                for index,path in enumerate((directory/'appdata/GrangerPet/logs').glob('*.log')):
                    (output/f'runtime-{index}-private.log').write_bytes(path.read_bytes())
                raise
            finally:
                session.stop();save()
    report['temporary_profile_removed']=not directory.exists();save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',action='store_true')
    args=parser.parse_args();run(args.exe.resolve(),args.output.resolve(),source=args.source)
