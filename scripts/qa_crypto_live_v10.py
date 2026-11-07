"""Fresh public Gansar profile → evidence → both V10 styles, in an isolated EXE."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session
from scripts.qa_v4_investigation import TON


def run(exe,out):
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    out.mkdir(parents=True,exist_ok=False)
    report={'passed':False,'mock':False,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[]}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)});save();print(json.dumps(report['checks'][-1]),flush=True)
        if not value:raise QaFailure(name)
    with isolated_environment(out):
        SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
        store=CanvasStore(InvestigationJournal(out/'appdata/GrangerPet/investigations'))
        s=V7Session(exe,out)
        try:
            s.start(0);s.click('Поиск');s.action('tools_refresh')
            wait_for(lambda:not s.snapshot().get('toolsChecking'),90)
            check('actual_gansar_runtime_ready',next(row for row in s.snapshot()['tools'] if row['id']=='blockchain_gansar')['available'])
            s.click('Мой граф');s.action('research_canvas_new',{'title':'V10 QA · Gansar public TON'})
            wait_for(lambda:s.document().get('title')=='V10 QA · Gansar public TON');s.ensure_expanded()
            wallet=s.create_v7('Криптокошелёк','Адрес кошелька',TON,'TON')
            s.select(wallet['id']);s.click('Исследовать');s.click('Исследовать криптообъект')
            s.pick('Операция Gansar','Обзор адреса','profile')
            started=time.monotonic();s.click('Выполнить → просмотр')
            def finished():
                state=s.snapshot();preview=state.get('research_canvas',{}).get('preview',{})
                return preview if preview.get('tool')=='blockchain_gansar' and not preview.get('running') and not state['search']['busy'] else None
            preview=wait_for(finished,210)
            report['execution']={key:preview.get(key) for key in ('tool','operation','status','request_counts','error_code','limitations')}
            report['execution'].update(records=len(preview.get('results',[])),elapsed_seconds=round(time.monotonic()-started,3));save()
            check('fresh_public_gansar_returned_observations',preview.get('status') in ('complete','completed','partial') and bool(preview.get('results')))
            s.click('Результаты для добавления')
            s.click('Выбрать все ('+str(len(preview['results']))+')');s.click('Добавить выбранные ('+str(len(preview['results']))+')')
            wait_for(lambda:(s.canvas().get('insertion') or {}).get('preview_token')==preview['token'],90);s.idle()
            identifier=s.document()['id']
            def facts():
                d=store.load(identifier)
                return {key:d[key] for key in ('entities','relations','evidence','annotations','activity')}|{'positions':d['view']['positions']}
            before=facts()
            s.click('Закрыть редактор')
            if s.find('Закрыть результаты')[0]:s.click('Закрыть результаты')
            for style in ('glass','minimal'):
                s.action('settings_save',{'values':{'workspace_appearance':json.dumps({'graphStyle':style})}});s.idle()
                s.click('Показать всё');s.command('qa_snapshot',{'name':'live-ton-'+style})
                check(style+'_network_and_evidence_kept',facts()==before and any(n['attributes'].get('chain')=='ton' for n in s.document()['entities']))
            report['passed']=True;save()
        except BaseException as error:
            report.update(error_type=type(error).__name__,error=str(error)[:180]);save();raise
        finally:s.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.exe.resolve(),a.output.resolve())
