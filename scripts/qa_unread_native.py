"""Native Windows unread-letter QA fixture; isolated profile, no API/secrets.

Run, then physically click the separate `Granger-OSINT QA · Конверт` window.
The fixture uses real encrypted conversations and the production receiver, but
does not claim its synthetic completion events came from a paid API response.
No IPC instance is acquired and no existing Granger-OSINT process is stopped.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QPoint,Qt,QTimer,QObject,QEvent
from PySide6.QtGui import QGuiApplication,QIcon,QCursor
from PySide6.QtWidgets import QApplication
from grangerpet import credentials
from grangerpet.config import Settings,SettingsStore
from grangerpet.pet import PetWindow

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/refinement-qa/unread-native')
    parser.add_argument('--duration',type=int,default=180)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(ROOT/'resources/Granger-OSINT.ico')))
    # Empty isolated vault target: the normal user's saved keys are not read.
    credentials._STORE=credentials.CredentialsStore(prefix='GrangerPet/QA/Unread-'+uuid.uuid4().hex)
    profile=tempfile.TemporaryDirectory(prefix='granger-unread-qa-')
    pet=PetWindow(Settings(ai_provider='none',notifications_animate=True),SettingsStore(Path(profile.name)/'settings.json'),interaction_qa=True)
    pet.setWindowTitle('Granger-OSINT QA · Гермиона')
    pet.notification.setWindowTitle('Granger-OSINT QA · Конверт')
    pet.panel.setWindowTitle('Granger-OSINT QA · Диалог уведомления')
    area=QGuiApplication.primaryScreen().availableGeometry()
    pet.move(area.left()+50,area.bottom()-pet.height()-40)
    pet.panel.resize(760,min(650,area.height()-50));pet.panel.move(area.left()+300,area.top()+20)
    chat=pet.panel.chat_widget
    events=[]
    for title,count in [('Первый QA-диалог',1),('Второй QA-диалог',2)]:
        chat._append('user',title+' — тест без API')
        for index in range(count):
            chat._append('model',f'Тестовый ответ {index+1}. Только fixture; сеть и реальные OSINT-данные не использовались.')
            events.append({'kind':'reply','message_id':chat.messages[-1]['id'],'index':len(chat.messages)-1,'conversation_id':chat.conversation_id})
        chat._save_archive();chat.new_conversation()
    pet.panel.showMinimized();pet.show()
    report={'fixture':True,'real_api_response':False,'existing_profile_modified':False,'events':[],
            'initial_unread':3,'dpr':pet.devicePixelRatioF(),'window_titles':{'letter':pet.notification.windowTitle(),'chat':pet.panel.windowTitle()}}
    def save():
        report['remaining_unread']=pet.notification.unread_count
        report['notification_geometry']=[pet.notification.x(),pet.notification.y(),pet.notification.width(),pet.notification.height()]
        report['notification_visible']=pet.notification.isVisible()
        report['cursor_global']=[QCursor.pos().x(),QCursor.pos().y()]
        if sys.platform=='win32':
            import ctypes
            user=ctypes.WinDLL('user32');user.GetWindowLongPtrW.argtypes=[ctypes.c_void_p,ctypes.c_int];user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
            style=user.GetWindowLongPtrW(int(pet.notification.winId()),-20)
            report['native_letter_flags']={'noactivate':bool(style & 0x08000000),'appwindow':bool(style & 0x00040000)}
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def after_click(kind,payload):
        report['events'].append({'event':'native_mouse_release','target':asdict(payload),
            'receiver_conversation':chat.conversation_id,'correct_conversation':chat.conversation_id==payload.conversation_id,
            'message_exists':any(row.get('id')==payload.message_id for row in chat.messages)})
        QTimer.singleShot(500,seen_visible)
        save()
    def seen_visible():
        if not pet.panel.isActiveWindow() or not pet.panel.isVisible() or pet.panel.isMinimized():return
        viewport=chat.history.viewport();ids=[]
        for row,bubble in zip(chat.messages,chat.history.bubbles):
            point=bubble.mapTo(viewport,QPoint())
            if row['role']=='model' and viewport.rect().intersects(bubble.rect().translated(point)):ids.append(row['id'])
        accepted=pet.panel.report_messages_seen(chat.conversation_id,ids)
        report['events'].append({'event':'visible_message_ack','ids':ids,'accepted':accepted,'remaining':pet.notification.unread_count})
        pet.panel.grab().save(str(args.output/f'chat-after-click-{len(report["events"])}.png'))
        save()
    def begin():
        for event in events:chat.turn_completed.emit(event)
        QTimer.singleShot(400,lambda:pet.notification.grab().save(str(args.output/'letter-initial.png')))
        save();print(json.dumps({'ready':True,'pid':__import__('os').getpid(),'letter_title':pet.notification.windowTitle(),'unread':pet.notification.unread_count}),flush=True)
    pet.notification.activated.connect(after_click)
    class MouseRecorder(QObject):
        def eventFilter(self,watched,event):
            if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease):
                report['events'].append({'event':'qt_mouse','type':int(event.type()),'local':[event.position().x(),event.position().y()]});save()
            return False
    recorder=MouseRecorder(pet.notification);pet.notification.installEventFilter(recorder)
    observer=QTimer(pet.notification);observer.setInterval(1000);observer.timeout.connect(save);observer.start()
    pet.notification.unread_changed.connect(lambda _:save())
    QTimer.singleShot(500,begin)
    QTimer.singleShot(max(15,min(600,args.duration))*1000,app.quit)
    app.aboutToQuit.connect(pet.shutdown)
    try:return app.exec()
    finally:save();profile.cleanup()

if __name__=='__main__':raise SystemExit(main())
