"""Native V5 graph review, with public observations in an isolated profile.

Raw evidence stays in an explicitly supplied private QA directory. Only own-window
screenshots and aggregate measurements are intended for publication.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_v4_investigation import Session, TON
from scripts.qa_clean_release import isolated_environment, wait_for, QaFailure


def baseline(exe:Path, output:Path, hold:bool=False,source:bool=False):
 from PySide6.QtCore import QCoreApplication
 from grangerpet.config import Settings, SettingsStore
 from grangerpet.agent_journal import InvestigationJournal
 from grangerpet.research_canvas import CanvasStore
 app=QCoreApplication.instance() or QCoreApplication([])
 output.mkdir(parents=True,exist_ok=True)
 result={'origin':'source-preview-public-network' if source else 'actual-v4-frozen-public-network','exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),'passed':False}
 with tempfile.TemporaryDirectory(prefix='.granger-qa-v5-',dir=ROOT) as name:
  directory=Path(name)
  with isolated_environment(directory):
   SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
   session=Session(exe,directory,source=source)
   try:
    session.start(0);session.click('Поиск');session.action('tools_refresh')
    wait_for(lambda:not session.snapshot().get('toolsChecking'),90)
    session.click('Моё полотно');session.click('Новое');wait_for(lambda:session.document().get('id'));session.click('Развернуть')
    wallet=session.create('blockchain_address','V5 public TON',TON,'ton');session.select(wallet['id']);session.click('Действия')
    wait_for(lambda:not session.find('Инструмент узла')[0].get('disabled'))
    session.pick('Инструмент узла','Gansar','gansar');session.pick('Операция Gansar','Обзор адреса','profile')
    session.click('Выполнить → просмотр')
    preview=wait_for(lambda:p if (p:=session.canvas().get('preview',{})).get('tool')=='blockchain_gansar' and not session.snapshot()['search']['busy'] else None,180)
    if not preview.get('results'):raise QaFailure('baseline_gansar_empty')
    count=len(preview['results']);session.click(f'Выбрать все ({count})');session.click(f'Добавить выбранные ({count})')
    wait_for(lambda:session.document()['view'].get('ui',{}).get('crypto_root_id')==wallet['id']);session.settled()
    if source:wait_for(lambda:session.document()['view']['layout']=='wallet' and not session.document()['view']['ui'].get('initial_layout'),40)
    store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
    doc=store.load(session.document()['id'])
    (output/'baseline-document-private.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
    (output/'ton-observed-private.json').write_text(json.dumps({'tool':'blockchain_gansar','status':preview['status'],'mock':False,'query':wallet['attributes']['address'],'results':doc['evidence']},ensure_ascii=False),encoding='utf-8')
    result.update(status=preview['status'],records=count,nodes=len(doc['entities']),edges=len(doc['relations']))
    def capture(label):
     session.command('qa_snapshot',{'name':label});time.sleep(.25)
     target=directory/(label+'-search.png')
     (output/(label+'.png')).write_bytes(target.read_bytes())
    capture('v4-import-before')
    # Match the reported analytical projection with a manual layout at18%.
    doc=session.settled();session.action('research_canvas_edit',{'id':doc['id'],'revision':doc['revision'],'operation':'view','arguments':{'view':{'viewport':{'x':730,'y':350,'scale':.18}}}})
    wait_for(lambda:session.document()['revision']>doc['revision']);capture('v4-far-before')
    (output/'baseline-ready.json').write_text(json.dumps({'pid':session.owned_pid,'qa_directory':str(directory),'document_id':doc['id']}),encoding='utf-8')
    if hold:
     deadline=time.monotonic()+900
     while time.monotonic()<deadline and not (output/'baseline-continue').exists():time.sleep(.25)
    result['passed']=True
   except BaseException:
    for file in directory.glob('process-*.log'):(output/file.name).write_bytes(file.read_bytes())
    (output/'failure.json').write_text(json.dumps({'owned_exit_code':session.process.poll() if session.process else None}),encoding='utf-8')
    raise
   finally:session.stop()
 result['temporary_profile_removed']=not directory.exists()
 (output/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False),flush=True)


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',action='store_true');parser.add_argument('--hold',action='store_true');parser.add_argument('--source',action='store_true')
 args=parser.parse_args()
 if not args.baseline:parser.error('Select an explicit QA mode')
 baseline(args.exe.resolve(),args.output.resolve(),args.hold,args.source)

if __name__=='__main__':main()
