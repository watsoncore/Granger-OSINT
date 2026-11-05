"""Bounded public-source workers from actual V7 node controls in an owned EXE."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session,TON


def run(exe,report_path,shots,*,source=False):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    report_path.parent.mkdir(parents=True,exist_ok=True);shots.mkdir(parents=True,exist_ok=True)
    result={'origin':'native-source' if source else 'frozen-Windows-EXE','exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
        'passed':False,'mock':False,'checks':[],'executions':[],'captures':[]}
    def save():report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        result['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps(result['checks'][-1]),flush=True)
        if not ok:raise QaFailure(name)
    with tempfile.TemporaryDirectory(prefix='.granger-live-v7-',dir=ROOT) as name:
        directory=Path(name).resolve();assert directory.parent==ROOT.resolve()
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'));session=V7Session(exe,directory,source)
            def capture(name):
                session.command('qa_snapshot',{'name':name});path=directory/(name+'-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:image.verify()
                        return True
                    except (OSError,ValueError):return False
                wait_for(ready,10);target=shots/(name+'.png');target.write_bytes(path.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
            def project(title):
                # Existing finite action creates the document; target forms,
                # tool setup/run/selection/insertion are actual Qt inputs.
                session.action('research_canvas_new',{'title':title});wait_for(lambda:session.document().get('title')==title and not session.canvas().get('busy'))
                session.ensure_expanded()
            def choose(node,action):
                session.select(node['id']);session.click('Исследовать')
                wait_for(lambda:e if (e:=session.find(action)[0]) and not e.get('disabled') else None,30)
                session.click(action)
            def execute(tool,operation=None):
                previous=(session.canvas().get('preview') or {}).get('token');started=time.monotonic()
                session.click('Выполнить → просмотр')
                def finished():
                    state=session.snapshot();preview=state.get('research_canvas',{}).get('preview',{})
                    return preview if preview.get('tool')==tool and preview.get('token')!=previous and not state['search']['busy'] and not preview.get('running') else None
                preview=wait_for(finished,210)
                result['executions'].append({'tool':tool,'operation':preview.get('operation'),'status':preview.get('status'),'records':len(preview['results']),
                    'elapsed_seconds':round(time.monotonic()-started,3),'from_saved_data':preview.get('from_saved_data'),'request_counts':preview.get('request_counts'),
                    'limitations':preview.get('limitations'),'error_code':preview.get('error_code')});save()
                check(tool+'_'+str(operation or 'default')+'_preview_is_new_and_honest',preview.get('status') in ('complete','completed','partial','empty','timeout','blocked','rate_limited','auth_required','unavailable') and (not operation or preview.get('operation')==operation))
                session.click('Результаты для добавления')
                return preview
            def insert(preview):
                count=len(preview['results'])
                if not count:return None
                session.click(f'Выбрать все ({count})');session.click(f'Добавить выбранные ({count})')
                wait_for(lambda:(session.canvas().get('insertion') or {}).get('preview_token')==preview['token'],90);session.idle()
                receipt=deepcopy(session.canvas()['insertion']);result['executions'][-1]['insertion']={k:v for k,v in receipt.items() if k!='added_node_ids'};save()
                saved=store.load(session.document()['id']);owner=next((node for node in saved['entities'] if node['id']==preview.get('node_id')),None)
                query=(owner or {}).get('attributes',{}).get('address') or (owner or {}).get('attributes',{}).get('value','')
                (report_path.parent/(report_path.stem+'-'+preview['tool']+'-'+str(preview.get('operation') or 'default')+'-observed-private.json')).write_text(
                    json.dumps({'origin':'actual native source worker' if source else 'actual frozen native worker','mock':False,
                        'tool':preview['tool'],'status':preview.get('status'),'query':query,'results_scope':'all saved after this operation',
                        'results':saved['evidence']},ensure_ascii=False),encoding='utf-8')
                return receipt
            try:
                session.start(0);session.click('Поиск');session.action('tools_refresh');wait_for(lambda:not session.snapshot().get('toolsChecking'),90)
                session.click('Моё полотно');project('V7 / Публичные профили')
                username=session.create_v7('Никнейм','Никнейм','solvnox');choose(username,'Найти публичные профили')
                session.pick('Режим Maigret','Быстрый','quick');preview=execute('username_maigret')
                check('live_maigret_has_observed_profiles',bool(preview['results']))
                insert(preview);check('maigret_inserted_profiles',any(n['type']=='public_profile' for n in session.document()['entities']))
                capture('live-maigret')
                project('V7 / Email')
                email=session.create_v7('Email','Email','octocat@github.com');choose(email,'Исследовать email');preview=execute('email_research');insert(preview)
                saved=store.load(session.document()['id']);check('email_evidence_does_not_verify_mailbox',bool(saved['evidence']) and all(row.get('details',{}).get('mailbox_verified') is False for row in saved['evidence']))
                capture('live-email')
                project('V7 / Компания')
                session.click('Новый объект');session.pick('Тип нового узла','Компания / организация','Компания');session.pick('Юрисдикция компании','США','США');session.fill('Название','MICROSOFT CORPORATION')
                session.click('Добавить объект');wait_for(lambda:len(session.document()['entities'])==1);company=session.settled()['entities'][0]
                choose(company,'Исследовать компанию');preview=execute('company_research');insert(preview)
                saved=store.load(session.document()['id']);check('company_source_is_registry_not_dns',bool(saved['evidence']) and all(row.get('details',{}).get('source_id')=='company_gleif' for row in saved['evidence']))
                candidates=[n for n in saved['entities'] if n['type']=='organization' and n['id']!=company['id']]
                check('company_candidates_remain_separate',len(candidates)>=2 and all(n['attributes'].get('identity_match_verified') is False for n in candidates))
                capture('live-company')
                project('V7 / TON и повторные NFT')
                wallet=session.create_v7('Криптокошелёк','Адрес кошелька',TON,'TON');choose(wallet,'Исследовать криптообъект')
                session.pick('Операция Gansar','Обзор адреса','profile');preview=execute('blockchain_gansar','profile');insert(preview)
                first=store.load(session.document()['id']);first_ids={row['evidence_id'] for row in first['evidence']}
                check('live_gansar_profile_saved',bool(first_ids))
                choose(wallet,'Исследовать криптообъект');session.pick('Операция Gansar','NFT','nft');preview=execute('blockchain_gansar','nft');receipt=insert(preview)
                saved=store.load(session.document()['id']);check('nft_run_keeps_previous_evidence',first_ids<={row['evidence_id'] for row in saved['evidence']})
                result['nft_observed']=bool(preview['results'])
                if receipt:
                    check('nft_insertion_uses_actual_counts_and_visible_projection',receipt['selected_records']==len(preview['results']) and saved['view']['ui']['graph_mode']=='assets')
                    check('saved_nft_entities_present',any(n['type'] in ('asset','nft','collection') for n in saved['entities']))
                capture('live-nft-repeat')
                final=deepcopy(saved);identifier=saved['id'];session.stop();session.start(1);session.click('Поиск');session.click('Моё полотно');session.open_document(identifier)
                reopened=store.load(identifier);check('live_results_survive_restart',reopened['entities']==final['entities'] and reopened['evidence']==final['evidence'])
                result['passed']=True;save()
            except BaseException as error:
                result.update(error_type=type(error).__name__,error=str(error)[:200]);save()
                result['owned_parent_exit_code']=session.process.poll() if session.process else None
                for file in directory.glob('process-*.log'):
                    (report_path.parent/(report_path.stem+'-'+file.name)).write_bytes(file.read_bytes())
                for i,file in enumerate((directory/'appdata/GrangerPet/logs').glob('*.log')):
                    (report_path.parent/(report_path.stem+'-runtime-'+str(i)+'.log')).write_bytes(file.read_bytes())
                save()
                try:
                    (report_path.parent/(report_path.stem+'-dom-private.json')).write_text(json.dumps(session.dom(),ensure_ascii=False),encoding='utf-8')
                    result['failure_metrics']=session.metrics();save();capture('failure')
                except Exception:pass
                raise
            finally:session.stop()
    result['temporary_profile_removed']=not directory.exists();save();return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--screenshots',type=Path,required=True);parser.add_argument('--source',action='store_true')
    args=parser.parse_args();run(args.exe.resolve(),args.report.resolve(),args.screenshots.resolve(),source=args.source)


if __name__=='__main__':main()
