"""Explicit real Nuclei QA against a newly owned loopback HTTP server only.

Run with --live after setup_nuclei.py. The private loopback target is passed to
the internal worker solely for this test; production execute rejects it.
"""
from pathlib import Path
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from grangerpet.integrations19 import nuclei
from grangerpet.agent_web import _FetchError


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('Use --live for the owned loopback smoke and cancellation check')
    binary=nuclei.runtime_path()
    if binary is None:parser.error('Install the verified optional runtime first')
    report={'fixture':False,'started_at':datetime.now(timezone.utc).isoformat(),'network':'owned-loopback-only','checks':[]}
    class Handler(BaseHTTPRequestHandler):
        calls=[];received=threading.Event();slow=False
        def do_HEAD(self):
            self.calls.append({'method':'HEAD','path':self.path,'host':self.headers.get('Host'),'user_agent':self.headers.get('User-Agent')})
            self.received.set()
            if self.slow:time.sleep(1)
            self.send_response(200);self.send_header('Content-Security-Policy',"default-src 'none'");self.end_headers()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    origin='http://127.0.0.1:'+str(server.server_port)+'/'
    try:
        result=nuclei._run_target(binary,origin,origin,'127.0.0.1',cancel=threading.Event(),deadline=time.monotonic()+20)
        assert result['status']=='complete' and len(Handler.calls)==1
        assert result['results'][0]['details']['observations']=={'status':200,'hsts_present':False,'csp_present':True}
        report['checks'].append({'name':'actual_cli_head','status':'passed','result':result,'requests':list(Handler.calls)})
        Handler.calls.clear();Handler.received.clear();Handler.slow=True
        cancel=threading.Event()
        def stop():
            if Handler.received.wait(10):cancel.set()
        thread=threading.Thread(target=stop,daemon=True);thread.start();started=time.monotonic()
        try:
            nuclei._run_target(binary,origin,origin,'127.0.0.1',cancel=cancel,deadline=time.monotonic()+15)
            raise AssertionError('Cancellation was ignored')
        except _FetchError as exc:
            assert exc.status=='cancelled'
            report['checks'].append({'name':'actual_cli_cancel','status':'passed','elapsed_seconds':round(time.monotonic()-started,3),'requests':list(Handler.calls)})
        # Test a new origin and the actual production gate; no CLI is spawned.
        denied=nuclei.execute({'target':origin,'authorized_scope':origin},approved=True)
        assert denied['status']=='invalid_arguments'
        report['checks'].append({'name':'production_private_target_blocked','status':'passed','result_status':denied['status']})
    finally:server.shutdown();server.server_close()
    destination=ROOT/'output'/'integrations19'/'nuclei-loopback-verified.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(destination),'checks':[(c['name'],c['status']) for c in report['checks']]},ensure_ascii=False))


if __name__=='__main__':main()
