"""Real phone-reference/email-DNS controls → preview → same saved graph node."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session


def run(exe,output,source=False):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    if output.exists():raise ValueError('Use a new QA directory')
    output.mkdir(parents=True)
    if source:
        from scripts.build_release import build_frontend
        import os
        build_frontend(ROOT,os.environ.copy())
    result={'origin':'native-source' if source else 'frozen-Windows-EXE','mock':False,
        'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
        'gateway_calls':0,'cases':[],'captures':[],'passed':False}
    def save():(output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cases=[('Телефон','Телефон','+12025550123','phone_metadata','Проверить формат телефона','phone'),
           ('Email','Email','contact@example.org','email_research','Исследовать email','email')]
    with tempfile.TemporaryDirectory(prefix='.granger-identifiers-v11-',dir=ROOT) as name:
        directory=Path(name).resolve()
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            session=V7Session(exe,directory,source)
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            def capture(label):
                session.command('qa_snapshot',{'name':label});path=directory/(label+'-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:image.verify()
                        return True
                    except (OSError,ValueError):return False
                wait_for(ready,10);target=output/(label+'.png');target.write_bytes(path.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
            try:
                session.start(0);session.click('Поиск');session.action('tools_refresh')
                wait_for(lambda:not session.snapshot().get('toolsChecking'),90);session.click('Моё полотно')
                for title,field,value,tool,button,kind in cases:
                    session.action('research_canvas_new',{'title':'V11 identifier '+kind})
                    wait_for(lambda:session.document().get('title')=='V11 identifier '+kind and not session.canvas().get('busy'))
                    session.ensure_expanded();owner=session.create_v7(title,field,value)
                    session.select(owner['id']);session.click('Исследовать');session.click(button)
                    session.click('Выполнить → просмотр')
                    def completed():
                        state=session.snapshot();preview=state.get('research_canvas',{}).get('preview') or {}
                        return preview if preview.get('tool')==tool and not preview.get('running') and not state['search']['busy'] else None
                    preview=wait_for(completed,50)
                    wait_for(lambda:'Найденные сведения' in session.dom().get('text',''),10)
                    before=session.settled()
                    if not preview['results']:raise QaFailure(tool+' returned no metadata')
                    if before['evidence']:raise QaFailure('Preview inserted data automatically')
                    session.click('Результаты для добавления');count=len(preview['results'])
                    session.click(f'Выбрать все ({count})');session.click(f'Добавить выбранные ({count})')
                    wait_for(lambda:(session.canvas().get('insertion') or {}).get('preview_token')==preview['token'],35)
                    session.idle();document=session.settled();saved=store.load(document['id'])
                    node=next(n for n in saved['entities'] if n['id']==owner['id'])
                    matches=[n for n in saved['entities'] if n['type']==kind]
                    facts=node['attributes']
                    check=(len(matches)==1 and bool(node['evidence_ids']) and bool(saved['evidence']) and
                        facts.get('owner_verified') is False and (facts.get('numbering_metadata_only') is True and
                        facts.get('current_location_verified') is False if kind=='phone' else facts.get('dns_policy_only') is True and facts.get('mailbox_verified') is False))
                    reopened=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations')).load(saved['id'])
                    check=check and all(reopened[k]==saved[k] for k in ('entities','relations','evidence'))
                    row={'tool':tool,'status':preview['status'],'observations':count,'same_manual_entity':len(matches)==1,
                        'evidence_ids_attached':len(node['evidence_ids']),'claims_limited_to_metadata':check,'passed':check}
                    result['cases'].append(row);save();print(json.dumps(row),flush=True)
                    session.click('Показать всё');capture(kind+'-enriched')
                    if not check:raise QaFailure('Identifier metadata contract failed: '+kind)
                result['passed']=all(row['passed'] for row in result['cases']);save()
            except BaseException as error:
                result.update(error_type=type(error).__name__,error=str(error)[:220]);save()
                try:capture('failure')
                except Exception:pass
                raise
            finally:session.stop()
    result['temporary_profile_removed']=not directory.exists();save();return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',action='store_true');args=parser.parse_args()
    run(args.exe.resolve(),args.output.resolve(),args.source)
