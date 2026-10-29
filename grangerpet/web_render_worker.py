"""Disposable, network-disabled Qt renderer for already fetched public HTML.

Input/output are bounded JSON over inherited anonymous pipes. No WebChannel,
credentials, persistent profile, files, direct network requests or user browser
session are available. Classic script resources were fetched by the pinned HTTP
client before this process starts; unsupported dynamic network stays blocked.
"""
from __future__ import annotations

import json
import sys

MAX_INPUT=2_500_000
MAX_HTML=1_600_000
DOCUMENT_URL='granger-render://document/index.html'


def _binary_pipe(name):
    """Windowed PyInstaller has no sys.stdin/out, but inherits explicit pipes."""
    stream=getattr(sys,name,None)
    if stream is not None:return getattr(stream,'buffer',stream)
    import os
    if os.name!='nt':raise RuntimeError('Inherited worker pipe unavailable')
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.argtypes=[wintypes.DWORD];kernel.GetStdHandle.restype=wintypes.HANDLE
    handle=kernel.GetStdHandle(-10 if name=='stdin' else -11)
    if not handle or handle==wintypes.HANDLE(-1).value:raise RuntimeError('Inherited worker pipe unavailable')
    descriptor=msvcrt.open_osfhandle(handle,os.O_BINARY|(os.O_RDONLY if name=='stdin' else os.O_WRONLY))
    return os.fdopen(descriptor,'rb' if name=='stdin' else 'wb',buffering=0)


def main():
    import os
    os.environ['QT_QPA_PLATFORM']='offscreen'
    os.environ.pop('QTWEBENGINE_REMOTE_DEBUGGING',None)
    os.environ.pop('QTWEBENGINE_DISABLE_SANDBOX',None)
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-background-networking --js-flags=--max-old-space-size=128'
    from PySide6.QtCore import QBuffer,QByteArray,QIODevice,QTimer,QUrl,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import (QWebEnginePage,QWebEngineProfile,QWebEngineSettings,
        QWebEngineScript,QWebEngineUrlRequestInterceptor,QWebEngineUrlScheme,
        QWebEngineUrlSchemeHandler,QWebEngineUrlRequestJob)
    incoming,outgoing=_binary_pipe('stdin'),_binary_pipe('stdout')
    raw=incoming.read(MAX_INPUT+1)
    if len(raw)>MAX_INPUT:return 2
    try:
        payload=json.loads(raw)
        html=payload['html'];minimum=int(payload.get('minimum_text',80));selector=payload.get('ready_selector','')
        seconds=max(1,min(15,float(payload.get('seconds',10))))
        if not isinstance(html,str) or len(html.encode('utf-8'))>MAX_HTML or not 20<=minimum<=1000:return 2
        if not isinstance(selector,str) or len(selector)>400:return 2
    except (ValueError,KeyError,TypeError):return 2
    scheme=QWebEngineUrlScheme(b'granger-render')
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort);scheme.setDefaultPort(443)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
    QWebEngineUrlScheme.registerScheme(scheme)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication([sys.argv[0]])
    app.setApplicationName('Granger-Public-Render');app.setQuitOnLastWindowClosed(False)
    profile=QWebEngineProfile()
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    rejected=[0];diagnostic={'started':0,'document_requests':0,'polls':0,'load_finished':None}
    class Interceptor(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self,info):
            if info.requestUrl().toString()!=DOCUMENT_URL:
                rejected[0]+=1;info.block(True)
    class Document(QWebEngineUrlSchemeHandler):
        def requestStarted(self,job):
            diagnostic['document_requests']+=1
            if job.requestUrl().toString()!=DOCUMENT_URL or job.requestMethod()!=b'GET':
                job.fail(QWebEngineUrlRequestJob.Error.RequestDenied);return
            body=QBuffer(job);body.setData(QByteArray(html.encode('utf-8')));body.open(QIODevice.OpenModeFlag.ReadOnly)
            job.reply(b'text/html',body)
    class Page(QWebEnginePage):
        def acceptNavigationRequest(self,url,kind,is_main):return url.toString()==DOCUMENT_URL
        def createWindow(self,kind):return None
        def chooseFiles(self,*args):return []
        def javaScriptConsoleMessage(self,*args):pass
    interceptor=Interceptor(profile);handler=Document(profile)
    profile.setUrlRequestInterceptor(interceptor);profile.installUrlSchemeHandler(b'granger-render',handler)
    page=Page(profile)
    view=QWebEngineView();view.setPage(page);view.resize(1024,768);view.show()
    page.setVisible(True)
    settings=page.settings()
    for name in ('LocalContentCanAccessRemoteUrls','LocalContentCanAccessFileUrls','JavascriptCanOpenWindows',
        'JavascriptCanAccessClipboard','JavascriptCanPaste','PluginsEnabled','FullScreenSupportEnabled',
        'ScreenCaptureEnabled','HyperlinkAuditingEnabled','DnsPrefetchEnabled','LocalStorageEnabled',
        'AllowRunningInsecureContent','ErrorPageEnabled','PdfViewerEnabled'):
        attribute=getattr(QWebEngineSettings.WebAttribute,name,None)
        if attribute is not None:settings.setAttribute(attribute,False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled,True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly,True)
    page.permissionRequested.connect(lambda request:request.deny())
    profile.downloadRequested.connect(lambda download:download.cancel())
    # Main-world, every frame, before untrusted source scripts. Network is also
    # denied natively by the interceptor and restrictive additional CSP.
    deny=QWebEngineScript();deny.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    deny.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld);deny.setRunsOnSubFrames(True)
    deny.setSourceCode("""(()=>{const blocked=()=>{throw new Error('Network capability unavailable in isolated reader')};
      for(const name of ['WebSocket','Worker','SharedWorker','RTCPeerConnection','webkitRTCPeerConnection'])
        try{Object.defineProperty(globalThis,name,{value:blocked,writable:false,configurable:false})}catch{}
      try{Object.defineProperty(navigator,'sendBeacon',{value:()=>false})}catch{}
    })();""")
    page.scripts().insert(deny)
    ended=[False];pending=[False];timer=QTimer();timer.setInterval(80)
    def finish(status,document=''):
        if ended[0]:return
        ended[0]=True;timer.stop()
        result={'status':status,'html':document[:MAX_HTML],'blocked_requests':rejected[0],
            'network_mode':'offline_pinned_prefetched_classic_scripts','dom_condition':'selector_or_useful_body_text','diagnostic':diagnostic}
        output=json.dumps(result,ensure_ascii=True,separators=(',',':')).encode('utf-8')
        if len(output)>MAX_INPUT:output=b'{"status":"rendered_document_too_large","html":""}'
        outgoing.write(output);outgoing.flush();app.quit()
    def receive(value):
        pending[0]=False
        if isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:return
        if isinstance(value,dict) and value.get('ready') and isinstance(value.get('html'),str):finish('rendered',value['html'])
    condition=json.dumps(selector)
    script=f"""JSON.stringify((()=>{{let selected=null;try{{selected={condition}?document.querySelector({condition}):null}}catch{{}}
      const body=document.body;const text=body?(body.innerText||'').trim():'';
      const ready=Boolean(body&&document.readyState==='complete'&&({condition}?selected:text.length>={minimum}));
      return ready?{{ready:true,html:document.documentElement.outerHTML.slice(0,{MAX_HTML})}}:{{ready:false}}}})())"""
    def poll():
        diagnostic['polls']+=1
        if not pending[0] and not ended[0]:pending[0]=True;page.runJavaScript(script,receive)
    timer.timeout.connect(poll)
    def loaded(ok):
        diagnostic['load_finished']=ok
        if ok:timer.start()
        else:finish('render_load_failed')
    page.loadStarted.connect(lambda:diagnostic.update(started=diagnostic['started']+1))
    page.loadFinished.connect(loaded)
    QTimer.singleShot(round(seconds*1000),lambda:finish('render_timeout'))
    page.setUrl(QUrl(DOCUMENT_URL))
    try:return app.exec()
    finally:
        timer.stop();view.close();page.deleteLater();app.processEvents();profile.deleteLater();app.processEvents()


if __name__=='__main__':raise SystemExit(main())
