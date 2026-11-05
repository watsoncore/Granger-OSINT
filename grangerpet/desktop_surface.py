"""Sandboxed local React surface with a private in-process Qt WebChannel.

The renderer may load only bundled assets and Qt's WebChannel bootstrap. Remote
pages are never loaded into this privileged view; reports are inert Markdown.
"""
from __future__ import annotations

from pathlib import Path
import sys
import mimetypes
import json

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt, QFile, QIODevice
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob, QWebEngineScript)
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView

from .desktop_bridge import DesktopBridge


def frontend_directory():
    if getattr(sys,'frozen',False): return Path(sys._MEIPASS)/'frontend'
    return Path(__file__).resolve().parents[1]/'frontend'/'dist'


def bundled_url(url, root):
    if url.scheme()=='qrc': return url.path()=='/qtwebchannel/qwebchannel.js'
    if url.scheme()=='data': return url.toString().startswith(('data:image/','data:font/'))
    if url.scheme()!='granger' or url.host()!='app' or url.userName() or url.password(): return False
    try:
        path = (root/url.path().lstrip('/')).resolve()
        path.relative_to(root.resolve())
        return path.is_file()
    except (OSError,ValueError): return False


def register_desktop_scheme():
    """Call before QApplication; trusted assets have their own secure origin."""
    if QWebEngineUrlScheme.schemeByName(b'granger').name(): return
    scheme=QWebEngineUrlScheme(b'granger')
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setDefaultPort(443)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme |
        QWebEngineUrlScheme.Flag.CorsEnabled | QWebEngineUrlScheme.Flag.FetchApiAllowed)
    QWebEngineUrlScheme.registerScheme(scheme)


class BundledAssets(QWebEngineUrlSchemeHandler):
    def __init__(self,root,parent=None): super().__init__(parent); self.root=root

    def requestStarted(self,job):
        url=job.requestUrl()
        if job.requestMethod()!=b'GET' or not bundled_url(url,self.root):
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied); return
        path=(self.root/url.path().lstrip('/')).resolve()
        file=QFile(str(path),job)
        if not file.open(QIODevice.OpenModeFlag.ReadOnly):
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound); return
        mime={'.js':'text/javascript','.css':'text/css','.html':'text/html'}.get(path.suffix,
            mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        job.reply(mime.encode('ascii'),file)


class AssetOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self,root,parent=None):
        super().__init__(parent); self.root=root

    def interceptRequest(self,info):
        if not bundled_url(info.requestUrl(),self.root): info.block(True)


class TrustedPage(QWebEnginePage):
    def __init__(self,profile,root,parent=None):
        super().__init__(profile,parent); self.root=root; self.diagnostics=[]

    def acceptNavigationRequest(self,url,kind,is_main):
        # Relative fragments remain on the same bundled document. All source
        # hyperlinks go through the finite bridge action and system browser.
        return bundled_url(url,self.root) and (not is_main or url.path()=='/index.html')

    def createWindow(self,kind): return None

    def chooseFiles(self,*args): return []

    def javaScriptConsoleMessage(self,level,message,line,source):
        # Model/user text and React component props must never become logs.
        if not self.property('qa_diagnostics'): return
        self.diagnostics.append({'level':level.value,'message':message[:500],'line':line})
        self.diagnostics=self.diagnostics[-10:]


class DesktopSurface(QWebEngineView):
    def __init__(self,host,surface='main'):
        super().__init__(host)
        self.host = host
        self._closing = False
        self._renderer_visible = False
        self.setObjectName('DesktopSurface')
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setAcceptDrops(True)
        self.root=frontend_directory()
        if not (self.root/'index.html').is_file():
            raise RuntimeError('Сначала соберите интерфейс: npm ci и npm run build в frontend/.')
        self.profile=QWebEngineProfile(self)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.assets_handler=BundledAssets(self.root,self.profile)
        self.profile.installUrlSchemeHandler(b'granger',self.assets_handler)
        self.interceptor=AssetOnlyInterceptor(self.root,self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(self._deny_download)
        self.trusted_page=TrustedPage(self.profile,self.root,self)
        self.trusted_page.setProperty('qa_diagnostics', '--interaction-qa' in sys.argv)
        self.load_ok=None
        self.loadFinished.connect(self._load_finished)
        self.setPage(self.trusted_page)
        from .theme import PALETTES
        selected=getattr(host.settings,'ui_theme','dark')
        selected=selected if selected in PALETTES else 'dark'
        self.trusted_page.setBackgroundColor(QColor(PALETTES[selected]['background']))
        theme_script=QWebEngineScript()
        theme_script.setName('granger-initial-theme')
        theme_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        theme_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        theme_script.setSourceCode("globalThis.__GRANGER_THEME__="+json.dumps(selected)+";(()=>{const apply=()=>{if(!document.documentElement)return false;document.documentElement.dataset.theme=globalThis.__GRANGER_THEME__;return true};if(!apply()){const o=new MutationObserver(()=>{if(apply())o.disconnect()});o.observe(document,{childList:true})}})();")
        effects=getattr(host.settings,'ui_effects','full')
        if effects in ('reduced','off'):
            theme_script.setSourceCode(theme_script.sourceCode()+';globalThis.__GRANGER_EFFECTS__='+json.dumps(effects)+';')
        if '--interaction-qa' in sys.argv:
            theme_script.setSourceCode(theme_script.sourceCode()+';globalThis.__GRANGER_QA_GRAPH__=true;')
        self.trusted_page.scripts().insert(theme_script)
        settings=self.settings()
        for attribute in (QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled):
            settings.setAttribute(attribute,False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled,True)
        self.trusted_page.permissionRequested.connect(self._deny_permission)
        self.bridge=DesktopBridge(host,surface)
        self.bridge.rendererReady.connect(lambda:QTimer.singleShot(0,self._sync_visibility))
        host.installEventFilter(self)
        self.qa_last_response={}
        self.bridge.response.connect(self._qa_response)
        self.channel=QWebChannel(self.trusted_page)
        self.channel.registerObject('desktop',self.bridge)
        self.trusted_page.setWebChannel(self.channel)
        url=QUrl('granger://app/index.html')
        url.setQuery('surface='+surface)
        self.setUrl(url)
        QTimer.singleShot(0,self._sync_visibility)

    def _load_finished(self,ok):
        self.load_ok=bool(ok)
        self._sync_visibility()

    def _graph_drop_path(self,event):
        if self.bridge.route!='search' or not event.mimeData().hasUrls():
            return None
        from pathlib import PureWindowsPath
        urls=event.mimeData().urls()
        if len(urls)!=1 or not urls[0].isLocalFile():
            return None
        path=urls[0].toLocalFile()
        if PureWindowsPath(path).suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
            return None
        return path

    def _graph_drop_feedback(self,phase,point=None,token=None):
        if phase=='hover':
            import time
            now=time.monotonic()
            if now-getattr(self,'_last_graph_drop_feedback',0)<.016:
                return
            self._last_graph_drop_feedback=now
        position=[point.x(),point.y()] if point is not None else [0,0]
        args=json.dumps([phase,*position,self.width(),self.height(),token],ensure_ascii=True)
        self.trusted_page.runJavaScript('globalThis.grangerGraphFileDrop?.(...'+args+')')

    def dragEnterEvent(self,event):
        if self._graph_drop_path(event):
            event.acceptProposedAction()
            self._graph_drop_feedback('hover',event.position())
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        if self._graph_drop_path(event):
            event.acceptProposedAction()
            self._graph_drop_feedback('hover',event.position())
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self,event):
        if self.bridge.route=='search':
            self._graph_drop_feedback('leave')
        super().dragLeaveEvent(event)

    def dropEvent(self,event):
        path=self._graph_drop_path(event)
        if not path:
            return super().dropEvent(event)
        import time
        import uuid
        token=uuid.uuid4().hex
        self.bridge._canvas_native_drop=(token,path,time.monotonic()+10)
        event.acceptProposedAction()
        self._graph_drop_feedback('drop',event.position(),token)

    def eventFilter(self,watched,event):
        if watched is self.host and event.type() in (QEvent.Type.Show,QEvent.Type.Hide,QEvent.Type.WindowStateChange):
            QTimer.singleShot(0,self._sync_visibility)
        return super().eventFilter(watched,event)

    def _sync_visibility(self):
        if self._closing:return
        visible=bool(self.host.isVisible() and not self.host.isMinimized() and self.isVisible())
        self._renderer_visible=visible
        if visible:
            self.trusted_page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
        self.trusted_page.setVisible(visible)
        self.bridge.set_publication_visible(visible)
        # Explicit Frozen caused higher visible-window CPU in our native A/B
        # measurements. Page visibility already enables Chromium background
        # scheduling; no bridge snapshots are sent while hidden. Retain DOM,
        # drafts and Python work without forcing Frozen or Discarded.

    def _qa_response(self,identifier,value):
        if identifier=='qa' and '--interaction-qa' in sys.argv:
            import json
            try: self.qa_last_response=json.loads(value)
            except (ValueError,TypeError): self.qa_last_response={}

    @staticmethod
    def _deny_download(download): download.cancel()

    @staticmethod
    def _deny_permission(permission): permission.deny()

    def shutdown(self):
        if self._closing or getattr(self,'_shutdown_draining',False):return
        # Keep QWebChannel and queued durable ACKs alive before closing the page.
        from .canvas_pending import flush_canvas_pending
        self._shutdown_draining=True
        try:self.canvas_shutdown=flush_canvas_pending(self)
        finally:self._shutdown_draining=False
        self._closing=True
        self.host.removeEventFilter(self)
        self.bridge.shutdown()
        self.stop()
        self.trusted_page.setWebChannel(None)
