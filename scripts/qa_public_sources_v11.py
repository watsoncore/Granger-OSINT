"""Native public-source preview/insertion acceptance in an isolated profile.

Makes real bounded requests through the application's existing node-tool bridge.
The default six cases use actual Qt controls for selecting/running/inserting.
--all uses the same finite bridge actions for the full adapter matrix; it does
not evaluate page JavaScript or inject synthetic findings.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',action='store_true')
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--providers',nargs='+')
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a new output directory.')
    args.output.mkdir(parents=True);shots=args.output/'screens';shots.mkdir()
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.source_adapters import CONTRACTS,normalize_query
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    if args.source:
        from scripts.build_release import build_frontend
        import os
        build_frontend(ROOT,os.environ.copy())
    else:
        from scripts.qa_clean_release import frozen_frontend_current
        if not frozen_frontend_current(args.exe):raise QaFailure('Stale frozen frontend')
    queries=json.loads((ROOT/'tests/fixtures/public_source_queries_v11.json').read_text(encoding='utf-8'))
    providers=args.providers or (list(queries) if args.all else ['codeberg','brreg','pypi','blockstream','opentopodata','openalex'])
    if any(provider not in queries for provider in providers):parser.error('Unknown provider')
    result={'at_utc':datetime.now(timezone.utc).isoformat(),'origin':'native-source' if args.source else 'frozen-Windows-EXE',
        'exe_sha256':None if args.source else hashlib.sha256(args.exe.read_bytes()).hexdigest(),
        'mock':False,'isolated_profile':True,'actual_qt_controls':not args.all,'cases':[],'captures':[], 'passed':False}
    def save():(args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='.granger-sources-v11-',dir=ROOT) as name:
        directory=Path(name).resolve()
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            session=V7Session(args.exe.resolve(),directory,args.source)
            def capture(label):
                session.command('qa_snapshot',{'name':label});path=directory/(label+'-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:image.verify()
                        return True
                    except (OSError,ValueError):return False
                wait_for(ready,10);target=shots/(label+'.png');target.write_bytes(path.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
            try:
                session.start(0);session.click('Поиск');session.action('tools_refresh')
                wait_for(lambda:not session.snapshot().get('toolsChecking'),90)
                session.click('Моё полотно')
                for provider in providers:
                    item=CONTRACTS['source_'+provider];query=normalize_query(item.adapter_id,queries[provider])
                    session.action('research_canvas_new',{'title':'V11 source '+provider})
                    wait_for(lambda:session.document().get('title')=='V11 source '+provider and not session.canvas().get('busy'))
                    session.ensure_expanded()
                    kind='username' if item.input_kind in ('username','handle') else 'person' if item.input_kind=='person' else 'organization' if item.input_kind=='company' else 'coordinate' if item.input_kind=='coordinates' else 'domain' if item.input_kind in ('site','domain') else 'repository' if item.input_kind=='repository' else 'blockchain_address' if item.input_kind.startswith('crypto_') else 'document'
                    value='https://github.com/'+query if item.input_kind=='repository' else query
                    arguments={'type':kind,'value':value,'label':'Public test target · '+provider}
                    if item.input_kind.startswith('crypto_'):arguments['chain']=item.input_kind.removeprefix('crypto_')
                    document=session.settled()
                    session.action('research_canvas_edit',{'id':document['id'],'revision':document['revision'],'operation':'node','arguments':arguments})
                    wait_for(lambda:len(session.document().get('entities',[]))==1 and not session.canvas().get('busy'))
                    document=session.settled();owner=document['entities'][0];before=deepcopy(document)
                    started=time.monotonic()
                    if not args.all:
                        session.select(owner['id']);session.click('Исследовать')
                        session.click('Отдельные и дополнительные инструменты')
                        session.pick('Инструмент узла',item.display_name,item.display_name.split(' · ')[0])
                        session.click('Выполнить → просмотр')
                    else:
                        session.action('research_canvas_tool',{'id':document['id'],'revision':document['revision'],'entity_id':owner['id'],
                            'tool':item.adapter_id,'arguments':{'query':query,'limit':3},'limit':3})
                    def completed():
                        state=session.snapshot();preview=state.get('research_canvas',{}).get('preview') or {}
                        return preview if preview.get('tool')==item.adapter_id and not preview.get('running') and not state['search']['busy'] else None
                    preview=wait_for(completed,50)
                    wait_for(lambda:'Найденные сведения' in session.dom().get('text',''),10)
                    current=session.settled()
                    untouched=current['entities']==before['entities'] and current['evidence']==before['evidence']
                    row={'provider_id':provider,'status':preview['status'],'observations':len(preview['results']),
                        'preview_did_not_insert':untouched,'seconds':round(time.monotonic()-started,3),
                        'error_code':preview.get('error_code'),'insertion':False,'reopen':False,'deduplicated':False,'connected_to_target':False}
                    result['cases'].append(row);save()
                    if preview['results']:
                        if not args.all:
                            session.click('Результаты для добавления')
                            count=len(preview['results']);session.click(f'Выбрать все ({count})');session.click(f'Добавить выбранные ({count})')
                        else:
                            session.action('research_canvas_insert',{'id':current['id'],'revision':current['revision'],
                                'token':preview['token'],'evidence_ids':[record['evidence_id'] for record in preview['results']]})
                        wait_for(lambda:(session.canvas().get('insertion') or {}).get('preview_token')==preview['token'],35)
                        session.idle()
                        inserted=session.settled();receipt=session.canvas()['insertion']
                        row['insertion']=receipt['selected_records']==len(preview['results']) and receipt['unprojected_records']==0
                        found=[n for n in inserted['entities'] if n.get('attributes',{}).get('provider_id')==provider]
                        row['connected_to_target']=bool(found) and all(n['id']==owner['id'] or any(e['from_id']==owner['id'] and e['to_id']==n['id'] for e in inserted['relations']) for n in found)
                        from grangerpet.desktop_bridge import source_view
                        saved=store.load(inserted['id'])
                        # The UI DTO intentionally compacts raw evidence. Compare
                        # the documented projection, then reopen full bytes with
                        # an independent store instead of equating two formats.
                        reopened=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations')).load(inserted['id'])
                        row['reopen']=all(saved[key]==reopened[key] for key in ('entities','relations','evidence')) and all(saved[key]==inserted[key] for key in ('entities','relations')) and [source_view(record,compact=True) for record in saved['evidence']]==inserted['evidence']
                        previous_insertion=receipt['insertion_id']
                        if not args.all:
                            session.click('Результаты для добавления')
                            session.click(f'Добавить выбранные ({len(preview["results"])})')
                        else:
                            session.action('research_canvas_insert',{'id':inserted['id'],'revision':inserted['revision'],
                                'token':preview['token'],'evidence_ids':[record['evidence_id'] for record in preview['results']]})
                        wait_for(lambda:(session.canvas().get('insertion') or {}).get('insertion_id')!=previous_insertion,30)
                        session.idle();again=session.settled()
                        row['deduplicated']=all(again[key]==inserted[key] for key in ('entities','relations'))
                        if not args.all:
                            session.click('Показать всё');capture(provider+'-inserted')
                    row['passed']=preview['status']=='complete' and bool(preview['results']) and all(row[key] for key in ('preview_did_not_insert','insertion','reopen','deduplicated','connected_to_target'))
                    row['flow_passed']=row['passed'] or (untouched and not preview['results'] and preview['status'] in ('unavailable','timeout','auth_required','rate_limited','blocked'))
                    if not preview['results'] and not args.all:capture(provider+'-error')
                    save();print(json.dumps(row),flush=True)
                    if not row['flow_passed']:raise QaFailure('Native source flow failed: '+provider)
                result['passed']=all(row['flow_passed'] for row in result['cases'])
                result['independent_nonempty_live_providers']=len({row['provider_id'] for row in result['cases'] if row['passed']});save()
            except BaseException as error:
                result.update(error_type=type(error).__name__,error=str(error)[:240]);save()
                try:
                    capture('failure')
                    (args.output/'failure-dom-private.json').write_text(json.dumps(session.dom(),ensure_ascii=False),encoding='utf-8')
                except Exception:pass
                raise
            finally:session.stop()
    result['temporary_profile_removed']=not directory.exists();save()
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
