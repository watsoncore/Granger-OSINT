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

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=[handler])

    def exception_hook(kind, value, traceback):
        logging.getLogger("grangerpet").critical("Unhandled exception", exc_info=(kind, value, traceback))
        # GUI exceptions are logged; no console is needed by the packaged executable.
        if not issubclass(kind, KeyboardInterrupt) and QApplication.instance():
            QMessageBox.critical(None, PRODUCT_NAME, f"Произошла ошибка: {value}\n\nЖурнал: {directory}")

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
                                result['life'] = {'action': pet.life.action, 'active': pet.life.active}
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
                                    'last_response':surface.qa_last_response,
                                    'url':surface.url().toString(),'diagnostics':surface.trusted_page.diagnostics,
                                    'route':surface.bridge.route,'dom':getattr(surface,'qa_dom',{})}
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
                    (Path(pet._trace_path).parent/(name+'.json')).write_text(surface.bridge._json(surface.bridge.snapshot()),encoding='utf-8')
                elif payload.get('action')=='dom':
                    script="""JSON.stringify({text:document.body.innerText.slice(0,18000),title:document.title,buttons:[...document.querySelectorAll('button')].map(b=>({text:b.innerText,label:b.getAttribute('aria-label'),disabled:b.disabled})),headings:[...document.querySelectorAll('h1,h2,h3')].map(h=>h.innerText),tables:document.querySelectorAll('.markdown table').length,messages:document.querySelectorAll('[data-message-id]').length,overflow:document.documentElement.scrollWidth>innerWidth+2,width:innerWidth,height:innerHeight,font:{loaded:document.fonts.check('15px Manrope','Гермиона Ёжик'),family:getComputedStyle(document.body).fontFamily,size:getComputedStyle(document.body).fontSize},dock:(()=>{let r=document.getElementById('hermione-dock')?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null})()})"""
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
                def set_mode():
                    if mode == 'maximized': pet.panel.showMaximized()
                    elif mode == 'fullscreen': pet.panel.toggle_fullscreen()
                    elif mode == 'windowed':
                        if pet.panel.isFullScreen(): pet.panel.toggle_fullscreen()
                        pet.panel.showNormal()
                if mode not in ('maximized', 'fullscreen', 'windowed'): return {'ok': False}
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
                action = payload.get('action')
                if action not in ('reading', 'cast', 'avada', 'yawn', 'sleep', 'leave', 'return', 'wake', 'interrupt'):
                    return {'ok': False}
                if action == 'interrupt':
                    QTimer.singleShot(0, pet.notify_user_activity)
                elif not pet.panel.isVisible() and not pet._busy:
                    QTimer.singleShot(0, lambda: pet.life.start_action(action, duration=4))
                else: return {'ok': False}
                return {'ok': True}
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
            if command == "qa_snapshot" and pet is not None and args.interaction_qa and pet._trace_path:
                name = payload.get("name", "snapshot")
                if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", name):
                    return {"ok": False}
                def snapshot():
                    directory = Path(pet._trace_path).parent
                    pet._rendered.save(str(directory / f"{name}-pet.png"))
                    if pet.notification.isVisible(): pet.notification.grab().save(str(directory/f'{name}-notification.png'))
                    if pet.panel.isVisible():
                        pet.panel.grab().save(str(directory / f"{name}-search.png"))
                    if pet.panel.settings_dialog.isVisible():
                        pet.panel.settings_dialog.grab().save(str(directory / f"{name}-settings.png"))
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
