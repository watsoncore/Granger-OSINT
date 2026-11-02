"""Worker-local pinned egress proxy. No system or user proxy settings changed."""
import select
import socket
import socketserver
import threading
import time
import http.client
import ssl
import re
import hashlib
import os
from pathlib import Path
from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit
try:from .browser_policy import public_endpoint,public_url
except ImportError:from browser_policy import public_endpoint,public_url


class PublicProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
    def __init__(self):
        self.budget_lock=threading.Lock();self.bytes=0;self.requests=0;self.blocked=0
        self.slots=threading.BoundedSemaphore(12)
        super().__init__(('127.0.0.1',0),Tunnel)
        self.thread=threading.Thread(target=self.serve_forever,daemon=True);self.thread.start()
    def account(self,count=0,request=False):
        with self.budget_lock:
            self.bytes+=count;self.requests+=int(request)
            if self.bytes>30_000_000 or self.requests>160:raise ValueError('browser_network_budget')
    def stop(self):self.shutdown();self.server_close()


def worker_tls_context():
    """Use the host's pinned public CA bundle, with full TLS verification."""
    path=os.environ.get('GRANGER_RESEARCH_CA_BUNDLE','')
    digest=os.environ.get('GRANGER_RESEARCH_CA_SHA256','')
    if not path and not digest:return ssl.create_default_context()
    if not path or not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('invalid_browser_ca_bundle')
    source=Path(path)
    if not source.is_file() or not 0<source.stat().st_size<2_000_000:raise ValueError('invalid_browser_ca_bundle')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('changed_browser_ca_bundle')
    return ssl.create_default_context(cafile=str(source))


class RobotsPolicy:
    def __init__(self,proxy,*,tls_context=None):self.proxy=proxy;self.cache={};self.checks=[];self.tls_context=tls_context
    def allowed(self,url):
        url=public_url(url);parts=urlsplit(url);origin=parts.scheme+'://'+parts.netloc
        if origin not in self.cache:
            endpoint=origin+'/robots.txt';reader=RobotFileParser(endpoint);status='unavailable'
            connection=None;diagnostic={}
            try:
                # urllib's ProxyHandler still consults Windows proxy-bypass
                # settings. Connect to our literal proxy directly instead;
                # HTTPS CONNECT retains normal certificate/hostname validation.
                if parts.scheme=='https':
                    connection=http.client.HTTPSConnection('127.0.0.1',self.proxy.server_address[1],timeout=8,context=self.tls_context)
                    connection.set_tunnel(parts.hostname,443)
                    target='/robots.txt'
                else:
                    connection=http.client.HTTPConnection('127.0.0.1',self.proxy.server_address[1],timeout=8)
                    target=endpoint
                connection.request('GET',target,headers={'User-Agent':'Granger-OSINT/3.1 public research','Host':parts.netloc})
                response=connection.getresponse()
                if response.status==200:
                    body=response.read(500_001)
                    if len(body)>500_000:raise ValueError('robots_size_limit')
                    reader.parse(body.decode('utf-8','replace').splitlines());status='parsed'
                elif response.status in (404,410):reader.parse([]);status='absent'
                else:reader.disallow_all=True;status='http_'+str(response.status)
            except ssl.SSLError as error:
                reader.disallow_all=True;status='tls_error'
                code=getattr(error,'verify_code',None);reason=getattr(error,'reason','')
                if type(code) is int:diagnostic['tls_verify_code']=code
                if isinstance(reason,str) and re.fullmatch(r'[A-Z0-9_]{1,80}',reason):diagnostic['tls_reason']=reason
            except TimeoutError:reader.disallow_all=True;status='timeout'
            except (OSError,ValueError,http.client.HTTPException):reader.disallow_all=True
            finally:
                if connection:connection.close()
            self.cache[origin]=reader;self.checks.append({'origin':origin,'status':status,**diagnostic})
        return self.cache[origin].can_fetch('Granger-OSINT',url)


def search_post_response(proxy, tls, endpoint, body):
    parts=urlsplit(endpoint)
    connection=http.client.HTTPSConnection('127.0.0.1',proxy.server_address[1],timeout=8,context=tls)
    try:
        connection.set_tunnel(parts.hostname,443)
        connection.request('POST',parts.path,body=body.encode('ascii'),headers={
            'Host':parts.netloc,'Content-Type':'application/x-www-form-urlencoded','User-Agent':'Granger-OSINT/3.1 public research'})
        response=connection.getresponse()
        if response.status!=200:raise ValueError('search_post_refused')
        content_type=response.getheader('Content-Type','').split(';')[0].lower()
        if content_type not in ('text/html','application/json','application/xml','text/xml','text/plain'):
            raise ValueError('unsafe_search_response_type')
        content=response.read(512001)
        if len(content)>512000:raise ValueError('search_response_too_large')
        return content_type,content
    finally:
        connection.close()


class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        server=self.server
        if not server.slots.acquire(blocking=False):return
        remote=None
        try:
            self.request.settimeout(8);reader=self.request.makefile('rb',buffering=0)
            line=reader.readline(8193)
            if len(line)>8192:raise ValueError()
            method,target,version=line.decode('ascii').strip().split(' ')
            headers=[];size=0
            while True:
                h=reader.readline(8193);size+=len(h)
                if size>32768 or not h:raise ValueError()
                if h in (b'\r\n',b'\n'):break
                if h.lower().startswith((b'proxy-authorization:',b'proxy-connection:')):continue
                headers.append(h)
            server.account(request=True)
            if method=='CONNECT':
                url=public_url('https://'+target);p=urlsplit(url);host=p.hostname;port=443
                address=public_endpoint(host,port)
                remote=socket.create_connection((address,port),timeout=8)
                self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            elif method in ('GET','HEAD'):
                url=public_url(target);p=urlsplit(url)
                if p.scheme!='http':raise ValueError()
                address=public_endpoint(p.hostname,80);remote=socket.create_connection((address,80),timeout=8)
                path=p.path or '/'
                if p.query:path+='?'+p.query
                remote.sendall((method+' '+path+' HTTP/1.1\r\n').encode()+b''.join(headers)+b'Connection: close\r\n\r\n')
            else:raise ValueError('method_disabled')
            remote.settimeout(8);end=time.monotonic()+40
            while time.monotonic()<end:
                ready,_,_=select.select([self.request,remote],[],[],1)
                for current in ready:
                    block=current.recv(32768)
                    if not block:return
                    server.account(len(block));(remote if current is self.request else self.request).sendall(block)
        except (OSError,ValueError,UnicodeError):
            with server.budget_lock:server.blocked+=1
            try:self.request.sendall(b'HTTP/1.1 403 Public research policy\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:pass
        finally:
            if remote:remote.close()
            server.slots.release()
