"""Real public GET-form/DOM/OCR flow. No credentials or user chat/profile writes."""
import argparse
import base64
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.agent import AgentRunner
    from grangerpet.geoint import AttachmentStore
    from grangerpet.credentials import CredentialsStore
    from grangerpet.config import Settings
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    root=args.output.resolve();url='https://www.scrapethissite.com/pages/forms/'
    store=AttachmentStore(root=root/'isolated-profile',seal=CredentialsStore._protect,
        open_sealed=lambda raw:CredentialsStore._protect(raw,decrypt=True))
    r=ToolRegistry(Settings(),secret_getter=lambda name:'',image_store=store)
    r.seed_urls_from_user(url);events=[];last=None
    def run(name,arguments):
        nonlocal last
        start=time.monotonic();last=r.execute(name,arguments,deadline=time.monotonic()+60)
        if last['status']!='complete':raise RuntimeError(name+':'+last['status'])
        details=last['results'][0]['details']
        events.append({'action':name,'status':last['status'],'url':last['results'][0]['url'],
            'seconds':round(time.monotonic()-start,3),'tables':len(details.get('tables',[]))})
        print(json.dumps(events[-1]),flush=True)
        return details
    def action(name,item,details,**extra):
        return run(name,{'element_id':item['id'],'snapshot_id':details['snapshot_id'],**extra})
    try:
        d=run('browser_navigate',{'url':url})
        d=action('browser_type',next(x for x in d['elements'] if x.get('name')=='q'),d,text='New')
        d=action('browser_click',next(x for x in d['elements'] if x.get('type')=='submit'),d)
        for _ in range(4):
            d=run('browser_scroll',{'delta':1300})
            link=next((x for x in d['elements'] if 'page_num=2' in x.get('href','')),None)
            if link:break
        if not link:raise RuntimeError('public_pagination_not_found')
        d=action('browser_click',link,d)
        assert 'page_num=2' in last['results'][0]['url'] and d['tables'][0]['rows']
        runner=AgentRunner(object(),r);runner._record={'goal':'Прочитай результаты публичного поиска New'}
        compact=json.loads(runner._compact(last))
        assert compact['results'][0]['browser_controls']['snapshot_id']==d['snapshot_id']
        d=run('browser_screenshot',{})
        assert d.get('screenshot_attachment_id')
        state=r.browser_state();(root/'page.jpg').write_bytes(base64.b64decode(state['image'].split(',',1)[1]))
        (root/'model-view.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2),encoding='utf-8')
        browser=r._browser;process=browser.process;owned=[];performance={}
        from perf_process_metrics import _WindowsProcesses
        metrics=_WindowsProcesses();tree=metrics.ancestry();owned=[process.pid]
        while True:
            found=[pid for pid,row in tree.items() if row['parent_pid'] in owned and pid not in owned]
            if not found:break
            owned+=found
        counters=[row for pid in owned if (row:=metrics.counters(pid))]
        identities={row['pid']:(row['creation_ticks'],row['image']) for row in counters}
        performance={'process_count':len(owned),'rss_bytes':sum(row['rss_bytes'] or 0 for row in counters),
            'cpu_seconds':sum(row['cpu_seconds'] for row in counters)}
        cancel=threading.Event();timer=threading.Timer(.1,cancel.set);timer.start();start=time.monotonic()
        stopped=browser.execute('navigate',{'url':url},cancel_event=cancel)
        timer.cancel();browser.close()
        cancellation={'result':stopped.get('error_code') or 'completed_before_cancel','seconds':round(time.monotonic()-start,3)}
        teardown_deadline=time.monotonic()+8
        if owned:
            while True:
                alive=[pid for pid,identity in identities.items() if (row:=metrics.counters(pid)) and (row['creation_ticks'],row['image'])==identity]
                if not alive or time.monotonic()>=teardown_deadline:break
                time.sleep(.2)
            cancellation['owned_processes_left']=len(alive)
            cancellation['teardown_observed_seconds']=round(time.monotonic()-start,3)
            if alive:
                (root/'teardown.json').write_text(json.dumps({**cancellation,'alive_images':[Path(identities[pid][1]).name for pid in alive]}),encoding='utf-8')
            assert not alive,'owned_browser_process_leak'
        report={'test_kind':'live_public_site_real_edge','site':url,'events':events,'structured_rows':len(d['tables'][0]['rows']),
            'screenshot':{'real':True,'sha256':state['image_sha256'],'local_ocr':d.get('local_ocr',{}).get('status')},
            'model_current_controls':True,'performance':performance,'cancellation':cancellation,
            'limitations':['Public scraping practice site; no authentication, CAPTCHA, user cookies or vision model used.']}
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'complete':True,'ocr':report['screenshot']['local_ocr'],'cancellation':cancellation}),flush=True)
    finally:r.close()


if __name__=='__main__':main()
