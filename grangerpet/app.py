"""Application entry point and independent launcher/pet process lifecycles."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import re
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .config import Settings, SettingsStore, data_directory, resource_path, with_pet_preferences
from .ipc import InstanceServer, send_command
from .theme import STYLE
from .engine.models import is_confirmed
from .product import PRODUCT_NAME, VERSION


def _setup_logging():
    directory = data_directory() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    role = "pet" if "--pet" in sys.argv else "launcher"
    handler = RotatingFileHandler(directory / f"{role}.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # basicConfig is a no-op if an imported dependency configured the root
    # logger first. Always attach this application's actual per-user log.
    for existing in list(root.handlers):
        if getattr(existing, '_granger_log', False):
            root.removeHandler(existing)
            existing.close()
    handler._granger_log = True
    root.addHandler(handler)

    def exception_hook(kind, value, traceback):
        if issubclass(kind, (KeyboardInterrupt, SystemExit)):
            return
        from .errors import error_center
        center = error_center()
        if center is not None:
            center.report(kind, value, traceback, operation='qt_callback', stop_task=True)
        else:
            logging.getLogger('grangerpet').critical('Startup failed: %s', kind.__name__)

    sys.excepthook = exception_hook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PRODUCT_NAME+' desktop assistant')
    parser.add_argument("--pet", action="store_true", help="Run the independent desktop pet")
    parser.add_argument("--smoke-test", action="store_true", help="Show the requested surface briefly and exit")
    parser.add_argument("--interaction-qa", action="store_true", help="Expose the same pet as an enumerable native window for input QA")
    args = parser.parse_args(argv)
    _setup_logging()
    try:
        import ctypes
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GrangerOSINT.Desktop.1")
    except (AttributeError, OSError):
        pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from .desktop_surface import register_desktop_scheme
    register_desktop_scheme()
    app = QApplication([sys.argv[0]])
    from .errors import error_center
    error_center()
    app.setProperty('web_desktop',True)
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName('Granger-OSINT')
    app.setApplicationVersion(VERSION)
    from .typography import apply_app_font
    apply_app_font(app)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icon_path = resource_path('resources/Granger-OSINT.ico')
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    # Explicitly isolated Windows Credential Manager namespace for packaged
    # release QA. Production startup always keeps its existing vault target.
    qa_vault = os.environ.get('GRANGERPET_QA_VAULT', '')
    qa_vault_active = bool(args.interaction_qa and os.environ.get('GRANGERPET_INTERACTION_TRACE') and re.fullmatch(r'GrangerPet/QA/[a-zA-Z0-9_-]{8,80}', qa_vault))
    if qa_vault_active:
        from . import credentials
        credentials._STORE = credentials.CredentialsStore(prefix=qa_vault)
    store = SettingsStore()
    from .theme import apply_theme
    apply_theme(app,store.load().ui_theme)

    if args.pet:
        from .pet import PetWindow
        app.setQuitOnLastWindowClosed(False)
        pet_holder = {}

        def handle_pet(command, payload):
            pet = pet_holder.get("pet")
            if command == "status":
                result = {"ok": True, "running": pet is not None, "pid": os.getpid()}
                if pet is not None:
                    result.update(state=pet.animation.state, frame=pet.animation.frame,
                                  position=[pet.x(), pet.y()], size=pet.settings.size,
                                  near=pet._near, hovered=pet._over, panel_visible=pet.panel.isVisible(),
                                  searching=pet.panel._busy, result_count=len(pet.panel._records),
                                  result_confirmed=sum(is_confirmed(item) for item in pet.panel._records.values()),
                                  search_phase=getattr(pet.panel, "phase", ""),
                                  search_status=pet.panel.status.text(), drag_reaction=pet.physics.pose.reaction,
                                  sprite_revision=pet.library.revision)
                    if args.interaction_qa or pet._trace_path:
                        result.update(pose=asdict(pet.physics.pose), measurement=dict(pet.physics.last_measurement),
                                      last_transition=dict(pet.physics.last_transition), collar_rect=pet.geometry.get("collar_rect"),
                                      dpr=pet.devicePixelRatioF(), activity=pet.animation.state)
                        chat = getattr(pet.panel, "chat_widget", None)
                        if chat is not None:
                            result.update(ai_busy=chat.busy, ai_status=chat.status.text(),
                                ai_provider_status=chat.provider_status.text(),
                                ai_model_messages=sum(item["role"] == "model" for item in chat.messages),
                                ai_request=dict(chat.last_request))
                            investigation = getattr(chat, '_last_investigation', {})
                            if investigation:
                                result['agent'] = {name: investigation.get(name) for name in
                                    ('id', 'status', 'steps', 'tool_calls', 'accounted_tokens', 'stop_reason') if name in investigation}
                                result['agent']['evidence_count'] = len(investigation.get('evidence', []))
                                result['agent']['direct_pages'] = sum(row.get('details', {}).get('reading_method') == 'direct_http'
                                    for row in investigation.get('evidence', []))
                                result['agent']['tools'] = list(dict.fromkeys(item.get('tool') for item in investigation.get('executions', []) if item.get('tool')))
                            if hasattr(pet.panel, 'ai_state'):
                                result['ai_connection'] = pet.panel.ai_state.snapshot()
                                result['chat_can_send'] = pet.panel.ai_state.can_send
                            connections = pet.panel.settings_dialog.connections
                            result['settings_ai_status'] = connections.ai_status.text()
                            result['window'] = {'maximized': pet.panel.isMaximized(), 'fullscreen': pet.panel.isFullScreen(),
                                'width': pet.panel.width(), 'height': pet.panel.height(),
                                'canvas_visible': bool(pet.panel.canvas and pet.panel.workspace.currentWidget() is pet.panel.canvas)}
                            if pet.panel.canvas is not None:
                                result['canvas'] = {'id': pet.panel.canvas.document_id,
                                    'headings': pet.panel.canvas.heading_list.count(),
                                    'chars': len(pet.panel.canvas.editor.toPlainText())}
                            bubbles = chat.history.bubbles
                            if bubbles:
                                view = bubbles[-1].text_view
                                blocks, block = [], view.document().begin()
                                while block.isValid():
                                    blocks.append(block.blockFormat().headingLevel())
                                    block = block.next()
                                result['markdown'] = {'headings': sum(level > 0 for level in blocks),
                                    'tables': len(list(view._tables())) if hasattr(view, '_tables') else 0,
                                    'source_chars': len(bubbles[-1].message_text)}
                            if hasattr(pet, 'life'):
                                result['life'] = {'action': pet.life.action, 'active': pet.life.active,
                                    'figure_idle_seconds':round(max(0,time.monotonic()-pet.life.last_activity),2),
                                    'next_due_seconds':round(pet.life.next_due-time.monotonic(),2)}
                                result['pet_render']={'signature':str(pet._render_signature),'visible':pet.isVisible(),
                                    'frame_timer':pet.frame_timer.isActive(),'cursor_timer':pet.cursor_timer.isActive(),
                                    'drag_timer':pet.drag_timer.isActive(),'width':pet.width(),'height':pet.height(),
                                    'owned_timer_count':len(pet.findChildren(QTimer))}
                                tick_times=sorted(pet._tick_times)
                                result['pet_render'].update({'render_count':pet._render_count,'dpr':pet.devicePixelRatioF(),
                                    'tick_ms_p50':tick_times[len(tick_times)//2] if tick_times else 0,
                                    'tick_ms_p95':tick_times[round((len(tick_times)-1)*.95)] if tick_times else 0})
                                result['cameo']={'visible':bool(pet.cameo and pet.cameo.isVisible()),
                                    'actor':pet.life.pose().cameo,'room_available':bool(pet.cameo and pet.cameo.available()),
                                    'room':list(pet.cameo.room().getRect()) if pet.cameo else [],
                                    'input_transparent':bool(pet.cameo and pet.cameo.windowFlags()&Qt.WindowType.WindowTransparentForInput)}
                            if hasattr(pet,'notification'):
                                note=pet.notification
                                result['notification']={'visible':note.isVisible(),'kind':note.payload.kind if note.payload else None,
                                    'message_id':note.payload.message_id if note.payload else None,
                                    'geometry':list(note.geometry().getRect()),
                                    'unread_count':getattr(note,'unread_count',None)}
                            if pet.panel.desktop_surface:
                                surface=pet.panel.desktop_surface
                                result['desktop']={'ready':surface.bridge.ui_ready,'load_ok':surface.load_ok,
                                    'visible':surface.isVisible(),'geometry':list(surface.geometry().getRect()),
                                    'page_visible':surface.trusted_page.isVisible(),
                                    'lifecycle_state':surface.trusted_page.lifecycleState().name,
                                    'recommended_state':surface.trusted_page.recommendedState().name,
                                    'render_process_pid':surface.trusted_page.renderProcessPid(),
                                    'display_size':pet._display_size,
                                    'dock_geometry':list(pet.panel.hermione_dock_geometry().getRect()),
                                    'character':pet.panel.character.snapshot(),
                                    'last_response':surface.qa_last_response,
                                    'url':surface.url().toString(),'diagnostics':surface.trusted_page.diagnostics,
                                    'route':surface.bridge.route,'dom':getattr(surface,'qa_dom',{})}
                                result['desktop']['native_escape_enabled']=bool(getattr(pet.panel,'_escape_shortcut',None) and pet.panel._escape_shortcut.isEnabled())
                return result
            if command == "stop":
                if pet is not None:
                    QTimer.singleShot(35, pet.shutdown)
                else:
                    QTimer.singleShot(35, app.quit)
                return {"ok": True}
            if command == "settings" and pet is not None:
                settings = with_pet_preferences(store.load(), payload)
                pet.apply_settings(settings)
                return {"ok": True}
            if command=='show_workspace' and pet is not None:
                route=payload.get('route','chat')
                if route not in ('chat','search','history','canvas','settings'): return {'ok':False}
                def show_workspace():
                    if pet.panel.isMinimized(): pet.panel.showNormal()
                    pet.panel.show(); pet.panel.raise_(); pet.panel.activateWindow()
                    if pet.panel.desktop_surface:
                        pet.panel.desktop_surface.bridge.route=route
                        pet.panel.desktop_surface.bridge.mark_dirty()
                    elif route=='search': pet.panel.show_search()
                    else: pet.panel.show_chat()
                QTimer.singleShot(0,show_workspace)
                return {'ok':True}
            if command=='qa_desktop' and pet is not None and args.interaction_qa and pet._trace_path and pet.panel.desktop_surface:
                surface=pet.panel.desktop_surface
                if payload.get('action')=='save_state':
                    name=payload.get('name','state')
                    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',name): return {'ok':False}
                    from .qa_input import save_snapshot
                    save_snapshot(Path(pet._trace_path).parent/(name+'.json'),surface.bridge._json(surface.bridge.snapshot()))
                elif payload.get('action')=='input' and qa_vault_active:
                    from .qa_input import deliver
                    QTimer.singleShot(0,lambda:deliver(surface,payload.get('payload',{})))
                elif payload.get('action')=='attachment_file' and qa_vault_active:
                    # Large pixels do not belong in the tiny command pipe. Read
                    # only a named QA input inside this isolated trace directory.
                    import base64
                    name=payload.get('payload',{}).get('name','')
                    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}\.(jpg|png)',name):return {'ok':False}
                    root=Path(pet._trace_path).parent.resolve();path=(root/name).resolve()
                    if path.parent!=root or not path.is_file() or path.stat().st_size>10_000_000:return {'ok':False}
                    content={'name':name,'base64':base64.b64encode(path.read_bytes()).decode('ascii')}
                    QTimer.singleShot(0,lambda:surface.bridge.request('qa','attachment_import',json.dumps(content)))
                elif payload.get('action')=='qa_media_input' and qa_vault_active:
                    params=payload.get('payload',{})
                    name=params.get('name','') if isinstance(params,dict) else ''
                    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}\.png',name):return {'ok':False}
                    root=Path(pet._trace_path).parent.resolve();path=(root/name).resolve()
                    if path.parent!=root or not path.is_file() or path.stat().st_size>2_000_000:return {'ok':False}
                    from .qa_input import deliver_media
                    QTimer.singleShot(0,lambda:deliver_media(surface,path,params))
                elif payload.get('action')=='graph_scroll' and qa_vault_active:
                    surface.page().runJavaScript("document.querySelector('.investigation-tabs')?.scrollIntoView({block:'center'})")
                elif payload.get('action')=='geoint_scroll' and qa_vault_active:
                    selector={'header':'.geoint-view > header','controls':'.geo-compare-toolbar','map':'.geo-map-wrap','gallery':'.geo-original','compare':'.geo-comparison'}.get(payload.get('payload',{}).get('section'))
                    if selector:surface.page().runJavaScript("document.querySelector("+json.dumps(selector)+")?.scrollIntoView({block:'start'})")
                elif payload.get('action')=='dom':
                    script="""JSON.stringify({text:document.body.innerText.slice(0,18000),title:document.title,theme:document.documentElement.dataset.theme,effects:document.documentElement.dataset.effects,background:getComputedStyle(document.body).backgroundColor,buttons:[...document.querySelectorAll('button')].map(b=>({text:b.innerText,label:b.getAttribute('aria-label'),disabled:b.disabled})),headings:[...document.querySelectorAll('h1,h2,h3')].map(h=>h.innerText),tables:document.querySelectorAll('.markdown table').length,messages:document.querySelectorAll('[data-message-id]').length,overflow:document.documentElement.scrollWidth>innerWidth+2,width:innerWidth,height:innerHeight,font:{loaded:document.fonts.check('15px Manrope','Гермиона Ёжик'),family:getComputedStyle(document.body).fontFamily,size:getComputedStyle(document.body).fontSize},dock:(()=>{let r=document.getElementById('hermione-dock')?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null})()})"""
                    # Fixed read-only inspection, never arbitrary script from IPC.
                    script=script.replace('title:document.title,',"title:document.title,appStyle:document.documentElement.dataset.appStyle,materials:[...document.querySelectorAll('.sidebar,.workspace-header,.chat-header,.chat-composer,.settings-section,.catalog-tool,.research-title,.searchable-select-menu')].filter(e=>e.offsetWidth&&e.offsetHeight).slice(0,24).map(e=>{let s=getComputedStyle(e);return {className:e.className,shadow:s.boxShadow,backdrop:s.backdropFilter,background:s.backgroundColor,radius:s.borderRadius}}),")
                    script=script.replace('text:document.body', "elements:[...document.querySelectorAll('button,input,select,summary,[role=tab],[role=separator]')].map(b=>{let r=b.getBoundingClientRect();return {text:(b.innerText||'').slice(0,120),label:b.getAttribute('aria-label'),type:b.type,checked:b.checked,value:b.value,x:r.x,y:r.y,width:r.width,height:r.height}}),graph:(()=>{let g=document.querySelector('.investigation-workspace'),c=document.querySelector('.investigation-graph-canvas'),r=c?.getBoundingClientRect();return g?{...g.dataset,images:[...g.querySelectorAll('.graph-node-media img')].map(i=>({loaded:i.complete&&i.naturalWidth>0,source_is_local:i.src.startsWith('data:image/jpeg;base64,')})),canvas:c?{...c.dataset,x:r.x,y:r.y,width:r.width,height:r.height}:null}:null})(),text:document.body")
                    script=script.replace('text:document.body', "geo:(()=>{let g=document.querySelector('.geoint-view');return g?{images:[...g.querySelectorAll('img')].map(i=>({loaded:i.complete&&i.naturalWidth>0,source_is_local:i.src.startsWith('data:image/'),alt:i.alt})),map:!!g.querySelector('.leaflet-map-pane'),tiles:g.querySelectorAll('.leaflet-tile-loaded').length,attribution:g.querySelector('.leaflet-control-attribution')?.textContent,comparison:!!g.querySelector('.geo-comparison'),overlays:g.querySelectorAll('.geo-match-overlay').length}:null})(),text:document.body")
                    script=script.replace('button,input,select,summary,','button,input,textarea,select,summary,')
                    from .qa_graph_geometry import GRAPH_LAYOUT_INSPECTION
                    script=script.replace('text:document.body', 'graphLayout:('+GRAPH_LAYOUT_INSPECTION+')(),text:document.body')
                    script=script.replace('[role=separator]', '[role=separator],[role=menuitemradio]')
                    script=script.replace('type:b.type,checked:',"role:b.getAttribute('role'),disabled:b.disabled||b.hasAttribute('data-disabled'),appearance:getComputedStyle(b).appearance,svgCount:b.querySelectorAll('svg').length,type:b.type,checked:")
                    script=script.replace('role:b.getAttribute',"hit:(()=>{let hit=document.elementFromPoint(r.x+r.width/2,r.y+Math.min(16,r.height/2));return hit===b||b.contains(hit)})(),role:b.getAttribute")
                    script=script.replace('hit:(()=>',"scroll:(()=>{for(let p=b.parentElement;p;p=p.parentElement){let style=getComputedStyle(p);if(/auto|scroll/.test(style.overflowY)&&p.scrollHeight>p.clientHeight+2){let r=p.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,color:style.scrollbarColor,barWidth:style.scrollbarWidth}}}return null})(),hit:(()=>")
                    def receive(value):
                        try: surface.qa_dom=json.loads(value)
                        except (ValueError,TypeError): surface.qa_dom={}
                    surface.page().runJavaScript(script,receive)
                else:
                    action=payload.get('action');params=payload.get('payload',{})
                    if not isinstance(action,str) or not isinstance(params,dict): return {'ok':False}
                    def apply_action():
                        surface.bridge.request('qa',action,json.dumps(params,ensure_ascii=False))
                    QTimer.singleShot(0,apply_action)
                return {'ok':True}
            # Same-user local commands also let packaged-release QA exercise the
            # real UI/controller/worker path, with no test-only fake results.
            if command == "panel" and pet is not None:
                QTimer.singleShot(0, pet.toggle_panel)
                return {"ok": True}
            if command == "search" and pet is not None:
                text = payload.get("text", "")
                direction = payload.get("kind", "auto")
                if not isinstance(text, str) or not text.strip() or len(text) > 1500 or pet.panel._busy:
                    return {"ok": False, "error": "invalid or busy query"}
                index = pet.panel.direction.findData(direction)
                if index < 0:
                    return {"ok": False, "error": "unknown direction"}
                def start_search():
                    pet.panel.text.setText(text)
                    pet.panel.set_query_kind(direction)
                    if not pet.panel.isVisible():
                        pet.toggle_panel()
                    pet.panel.start_search()
                QTimer.singleShot(0, start_search)
                return {"ok": True}
            if command == "cancel_search" and pet is not None:
                QTimer.singleShot(0, pet.panel.cancel_search)
                return {"ok": True}
            if command == "qa_chat" and pet is not None and args.interaction_qa and pet._trace_path:
                text = payload.get("text", "")
                if not isinstance(text, str) or not text.strip() or len(text) > 12000 or pet.panel.chat_widget.busy:
                    return {"ok": False}
                def submit_chat():
                    if not pet.panel.isVisible():
                        pet.toggle_panel()
                    pet.panel.show_chat()
                    pet.panel.chat_widget.input.setPlainText(text)
                    pet.panel.chat_widget.send_message()
                QTimer.singleShot(0, submit_chat)
                return {"ok": True}
            if command == "qa_ai_draft" and pet is not None and qa_vault_active:
                # No credential crosses IPC. The QA process receives an
                # explicitly supplied development key through its environment.
                def prepare_ai_draft():
                    from .ai_keys import DEFAULT_DEEPSEEK_MODEL
                    pane = pet.panel.settings_dialog.connections
                    pane.provider.setCurrentIndex(pane.provider.findData('deepseek'))
                    pane.model.setEditText(DEFAULT_DEEPSEEK_MODEL)
                    pane.deepseek_key.setText(os.environ.get('GRANGERPET_QA_INPUT_KEY', ''))
                    pet.panel.open_settings('ИИ')
                QTimer.singleShot(0, prepare_ai_draft)
                return {"ok": True}
            if command == "qa_ai_check" and pet is not None and qa_vault_active:
                QTimer.singleShot(0, pet.panel.settings_dialog.connections.check_connection)
                return {"ok": True}
            if command == "qa_ai_save" and pet is not None and qa_vault_active:
                QTimer.singleShot(0, pet.panel.settings_dialog.connections.save)
                return {"ok": True}
            if command == "qa_ai_close" and pet is not None and args.interaction_qa and pet._trace_path:
                QTimer.singleShot(0, pet.panel.settings_dialog.close)
                return {"ok": True}
            if command == "qa_show_chat" and pet is not None and args.interaction_qa and pet._trace_path:
                QTimer.singleShot(0, pet.panel.show_chat)
                return {"ok": True}
            if command == 'qa_window_mode' and pet is not None and args.interaction_qa and pet._trace_path:
                mode = payload.get('mode')
                size = payload.get('size')
                if mode=='size' and (not qa_vault_active or not isinstance(size,list) or len(size)!=2
                        or type(size[0]) is not int or type(size[1]) is not int
                        or not 480<=size[0]<=2560 or not 350<=size[1]<=1440):
                    return {'ok':False}
                def set_mode():
                    if mode == 'maximized': pet.panel.showMaximized()
                    elif mode == 'fullscreen': pet.panel.toggle_fullscreen()
                    elif mode == 'windowed':
                        if pet.panel.isFullScreen(): pet.panel.toggle_fullscreen()
                        pet.panel.showNormal()
                    elif mode == 'size':
                        pet.panel.showNormal()
                        pet.panel.resize(*size)
                if mode not in ('maximized', 'fullscreen', 'windowed', 'size'): return {'ok': False}
                QTimer.singleShot(0, set_mode)
                return {'ok': True}
            if command == 'qa_canvas' and pet is not None and args.interaction_qa and pet._trace_path:
                action = payload.get('action')
                if action not in ('open_last', 'edit_save', 'back'): return {'ok': False}
                def canvas_action():
                    if action == 'open_last':
                        value = next((row['text'] for row in reversed(pet.panel.chat_widget.messages) if row['role'] == 'model'), '')
                        if value: pet.panel.open_canvas(value)
                    elif action == 'edit_save' and pet.panel.canvas is not None:
                        workspace = pet.panel.canvas
                        workspace.edit_button.setChecked(True)
                        workspace.editor.appendPlainText('\n\n## Заметка проверки\nЛокальная правка Canvas; исходные свидетельства не меняются.')
                        workspace.save_document()
                        workspace.export_document(Path(pet._trace_path).parent / 'canvas-export.md')
                    elif action == 'back': pet.panel.show_chat()
                QTimer.singleShot(0, canvas_action)
                return {'ok': True}
            if command == 'qa_life' and pet is not None and args.interaction_qa and pet._trace_path:
                from .pet_life import ACTIONS
                action = payload.get('action')
                if not qa_vault_active or action not in (*ACTIONS,'interrupt','schedule'):
                    return {'ok': False}
                if action == 'interrupt':
                    QTimer.singleShot(0, pet.notify_user_activity)
                elif action=='schedule':
                    def due():
                        pet.life.last_activity=time.monotonic()-90
                        pet.life.next_due=time.monotonic()
                    QTimer.singleShot(0,due)
                else:
                    duration=payload.get('duration',4)
                    if type(duration) not in (int,float) or not .2<=duration<=180:return {'ok':False}
                    variant=payload.get('variant')
                    variants={'reading':3,'shy':3,'annoyed':3,'wand_play':4,'malfoy':2,'harry':2,'ron_chat':2}
                    if variant is not None and (type(variant) is not int or not 0<=variant<variants.get(action,1)):
                        return {'ok':False}
                    def start_local_scene():
                        pet.life.finish()
                        pet.life.start_action(action,duration=duration,variant=variant)
                    QTimer.singleShot(0,start_local_scene)
                return {'ok': True}
            if command=='qa_figure' and pet is not None and args.interaction_qa and qa_vault_active:
                action=payload.get('action')
                if action not in ('hover','away','click','drag_up','drag_down'):return {'ok':False}
                def figure_input():
                    from PySide6.QtCore import QPoint
                    from PySide6.QtGui import QCursor
                    from PySide6.QtTest import QTest
                    collar=pet.geometry.get('collar_rect',[.39,.48,.14,.09])
                    point=QPoint(round(pet._padding+pet._display_size*(collar[0]+collar[2]/2)),round(pet._padding+pet._display_size*(collar[1]+collar[3]/2)))
                    if action=='away':
                        QCursor.setPos(pet.mapToGlobal(QPoint(-150,-150)));return
                    QCursor.setPos(pet.mapToGlobal(point))
                    if action=='hover':return
                    if action=='click':QTest.mouseClick(pet,Qt.MouseButton.LeftButton,pos=point);return
                    QTest.mousePress(pet,Qt.MouseButton.LeftButton,pos=point)
                    origin=pet.mapToGlobal(point);direction=-1 if action=='drag_up' else 1
                    for i in range(1,13):
                        target=origin+QPoint(0,direction*i*12)
                        QCursor.setPos(target);QTest.qWait(9)
                    QTest.mouseRelease(pet,Qt.MouseButton.LeftButton,pos=point)
                    QCursor.setPos(pet.mapToGlobal(QPoint(-150,-150)))
                QTimer.singleShot(0,figure_input)
                return {'ok':True}
            if command == "qa_settings" and pet is not None and args.interaction_qa and pet._trace_path:
                page = payload.get("page", 2)
                if not isinstance(page, int) or isinstance(page, bool) or page not in range(4):
                    return {"ok": False}
                def open_qa_settings():
                    pet.panel.settings_dialog.connections.tabs.setCurrentIndex(page)
                    pet.panel.settings_dialog.show()
                    pet.panel.settings_dialog.raise_()
                QTimer.singleShot(0, open_qa_settings)
                return {"ok": True}
            if command=='qa_record' and pet is not None and args.interaction_qa and qa_vault_active and pet._trace_path:
                name=payload.get('name');duration=payload.get('duration',20);fps=payload.get('fps',24)
                if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',name):return {'ok':False}
                if type(duration) not in (int,float) or not .2<=duration<=182:return {'ok':False}
                if type(fps) is not int or not 1<=fps<=24:return {'ok':False}
                mode=payload.get('mode','widget')
                if mode not in ('widget','native_text'):return {'ok':False}
                from .pet_capture import start_capture
                return {'ok':start_capture(pet,name,duration,fps,mode)}
            if command == "qa_snapshot" and pet is not None and args.interaction_qa and pet._trace_path:
                name = payload.get("name", "snapshot")
                if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", name):
                    return {"ok": False}
                def snapshot():
                    directory = Path(pet._trace_path).parent
                    pet._rendered.save(str(directory / f"{name}-pet.png"))
                    if pet.cameo and pet.cameo.isVisible():
                        from PySide6.QtGui import QImage,QPainter
                        pet.cameo.grab().save(str(directory/f'{name}-cameo.png'))
                        pet.cameo.image.save(str(directory/f'{name}-pair.png'))
                    if pet.notification.isVisible(): pet.notification.grab().save(str(directory/f'{name}-notification.png'))
                    if pet.panel.isVisible():
                        pet.panel.grab().save(str(directory / f"{name}-search.png"))
                    if pet.panel.settings_dialog.isVisible():
                        pet.panel.settings_dialog.grab().save(str(directory / f"{name}-settings.png"))
                    if qa_vault_active:
                        from .media_viewer import OriginalImageViewer
                        for index,viewer in enumerate(pet.panel.findChildren(OriginalImageViewer)):
                            if viewer.isVisible():viewer.grab().save(str(directory/f'{name}-original-{index}.png'))
                QTimer.singleShot(0, snapshot)
                return {"ok": True}
            return {"ok": False, "error": "unknown command"}

        instance = InstanceServer("pet", handle_pet)
        if not instance.acquire():
            return 0
        pet = PetWindow(store.load(), store, interaction_qa=args.interaction_qa)
        pet_holder["pet"] = pet
        pet.stopped.connect(app.quit)
        app.aboutToQuit.connect(instance.close)
        pet.show()
        logging.getLogger(__name__).info("Desktop pet started")
        if args.smoke_test:
            deadline=[0]
            def smoke_ready():
                deadline[0]+=1
                surface=pet.panel.desktop_surface
                if surface and surface.bridge.ui_ready:
                    QTimer.singleShot(600,pet.shutdown)
                elif deadline[0]<100: QTimer.singleShot(150,smoke_ready)
                else: pet.shutdown()
            QTimer.singleShot(150,smoke_ready)
    else:
        from .launcher import Launcher
        launcher_holder = {}

        def handle_launcher(command, payload):
            if command in ("focus", "status"):
                launcher = launcher_holder.get("launcher")
                if launcher is not None and command == "focus":
                    QTimer.singleShot(0, launcher.focus_window)
                return {'ok':True,'pid':os.getpid(),
                    'state':getattr(launcher,'process_state','ready') if launcher else 'ready',
                    'desktop_ready':bool(launcher and launcher.desktop_surface and launcher.desktop_surface.bridge.ui_ready)}
            if command=='qa_launcher' and launcher_holder.get('launcher') is not None and args.interaction_qa and os.environ.get('GRANGERPET_INTERACTION_TRACE'):
                launcher=launcher_holder['launcher']
                surface=launcher.desktop_surface
                if not surface: return {'ok':False}
                name=payload.get('name','launcher')
                if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',name): return {'ok':False}
                def qa_launcher():
                    if payload.get('action'):
                        surface.bridge.request('qa',payload['action'],json.dumps(payload.get('payload',{}),ensure_ascii=False))
                    folder=Path(os.environ['GRANGERPET_INTERACTION_TRACE']).parent
                    launcher.grab().save(str(folder/(name+'.png')))
                    (folder/(name+'.json')).write_text(surface.bridge._json(surface.bridge.snapshot()),encoding='utf-8')
                QTimer.singleShot(0,qa_launcher)
                return {'ok':True}
            return {"ok": False}

        instance = InstanceServer("launcher", handle_launcher)
        if not instance.acquire():
            send_command("launcher", "focus", timeout=350)
            return 0
        launcher = Launcher(store)
        launcher_holder["launcher"] = launcher
        launcher.exit_requested.connect(app.quit)
        app.aboutToQuit.connect(instance.close)
        launcher.show()
        logging.getLogger(__name__).info("Launcher started")
        if args.smoke_test:
            attempts=[0]
            def launcher_smoke_ready():
                attempts[0]+=1
                if launcher.desktop_surface and launcher.desktop_surface.bridge.ui_ready:
                    QTimer.singleShot(600,launcher.close)
                elif attempts[0]<100: QTimer.singleShot(150,launcher_smoke_ready)
                else: launcher.close()
            QTimer.singleShot(150,launcher_smoke_ready)
    return app.exec()
