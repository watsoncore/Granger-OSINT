"""Actual unread state, Qt pixel renderer, encrypted restart and exact routing."""
import os
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint,QRect,QSize,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from grangerpet.config import Settings,SettingsStore
from grangerpet.pet import PetWindow
from grangerpet.pet_notifications import PetNotification,NotificationPayload,UnreadLedger,notification_pose,notification_position

@pytest.fixture(scope='module')
def app():
    application=QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application

@pytest.fixture
def letter(app):
    now=[100.];widget=PetNotification(clock=lambda:now[0]);widget.apply_settings(SimpleNamespace())
    yield widget,now
    widget.dismiss();widget.deleteLater();app.processEvents()

@pytest.fixture
def pet(app,tmp_path):
    window=PetWindow(Settings(ai_provider='none'),SettingsStore(tmp_path/'settings.json'))
    window.frame_timer.stop();window.cursor_timer.stop();window.show();app.processEvents()
    yield window
    window.shutdown();window.panel.deleteLater();window.deleteLater();app.processEvents()

def test_short_entrance_then_persistent_static_letter():
    assert notification_pose(0).opacity==0
    assert 0<notification_pose(.1).opacity<1
    assert notification_pose(.28)==notification_pose(100000)
    assert notification_pose(0,False)==notification_pose(10000,False)

def test_unread_count_is_completed_messages_not_stream_chunks(letter):
    widget,now=letter
    assert widget.notify('reply','m1',conversation_id='c1')
    assert not widget.notify('reply','m1',conversation_id='c1')
    assert widget.notify('investigation','m2',conversation_id='c1')
    assert widget.unread_count==2
    now[0]+=600;widget.tick()
    assert widget.isVisible() and not widget._timer.isActive()
    assert widget.payload.message_id=='m1'

@pytest.mark.parametrize('setting,kind',[('notifications_enabled','reply'),('notifications_reply','reply'),('notifications_investigation','investigation'),('notifications_errors','error')])
def test_disabled_setting_suppresses_letter_without_faking_seen(letter,setting,kind):
    widget,_=letter;widget.apply_settings(SimpleNamespace(**{setting:False}))
    assert not widget.notify(kind,'m1',conversation_id='c1')
    assert not widget.isVisible() and ('c1','m1') in widget.ledger.unread
    widget.apply_settings(SimpleNamespace())
    assert widget.isVisible()

def test_error_attention_is_not_counted_as_completed_answer(letter):
    widget,_=letter;widget.notify('error','e1',conversation_id='c1')
    assert widget.unread_count==0 and widget.payload.kind=='error'
    assert widget.isVisible()

def test_only_actual_seen_ids_clear_and_duplicates_remain_deduplicated(letter):
    widget,_=letter
    for conversation,message in [('c1','m1'),('c1','m2'),('c2','m1')]:widget.notify('reply',message,conversation_id=conversation)
    assert widget.mark_seen('c1',['m1'])==1 and widget.unread_count==2
    assert not widget.notify('reply','m1',conversation_id='c1')
    assert widget.mark_seen('wrong',['m2'])==0 and widget.unread_count==2
    assert widget.mark_seen('c1',['m2'])==1 and widget.payload.conversation_id=='c2'
    widget.mark_seen('c2',['m1'])
    assert widget.unread_count==0 and not widget.isVisible()

def test_viewing_one_conversation_does_not_hide_other_unread(letter):
    widget,_=letter;widget.set_context('c1')
    widget.notify('reply','m1',conversation_id='c1');assert not widget.isVisible()
    widget.notify('reply','m2',conversation_id='c2');assert widget.isVisible()
    assert widget.payload.conversation_id=='c2'
    widget.set_context(None);assert widget.payload.conversation_id=='c1'

def test_click_routes_oldest_unread_but_does_not_claim_seen(letter):
    widget,_=letter;events=[];widget.activated.connect(lambda kind,payload:events.append((kind,payload)))
    widget.notify('investigation','m1',conversation_id='c1',index=7)
    QTest.mouseClick(widget,Qt.MouseButton.LeftButton,pos=QPoint(24,28))
    assert events[0][1]==NotificationPayload('investigation','m1',7,'c1')
    assert widget.unread_count==1
    assert not widget.mask().contains(QPoint(0,0))

def test_drag_does_not_activate(letter):
    widget,_=letter;events=[];widget.activated.connect(lambda *args:events.append(args));widget.notify('reply','m1')
    QTest.mousePress(widget,Qt.MouseButton.LeftButton,pos=QPoint(20,28));QTest.mouseRelease(widget,Qt.MouseButton.LeftButton,pos=QPoint(40,28))
    assert not events

def test_reduced_motion_does_not_start_a_timer(letter,monkeypatch):
    widget,_=letter;monkeypatch.setattr('grangerpet.pet_notifications.reduced_motion',lambda:True)
    widget.apply_settings(SimpleNamespace(notifications_animate=True));widget.notify('reply','m1')
    assert widget._pose.opacity==1 and not widget._timer.isActive()

def test_restart_keeps_unread_and_seen_ids_encrypted(tmp_path):
    path=tmp_path/'unread.dpapi';ledger=UnreadLedger(path)
    ledger.add(NotificationPayload('reply','opaque_message_1',1,'opaque_conversation'))
    ledger.add(NotificationPayload('reply','opaque_message_2',2,'opaque_conversation'))
    ledger.mark_seen('opaque_conversation',['opaque_message_1'])
    assert b'opaque_message' not in path.read_bytes()
    restored=UnreadLedger(path)
    assert list(restored.unread)==[('opaque_conversation','opaque_message_2')]
    assert not restored.add(NotificationPayload('reply','opaque_message_1',1,'opaque_conversation'))
    assert not restored.persistence_error

def test_corrupt_archive_does_not_invent_unread_or_prevent_new_notifications(tmp_path):
    path=tmp_path/'unread.dpapi';path.write_bytes(b'corrupt')
    ledger=UnreadLedger(path);assert ledger.persistence_error and not ledger.unread
    assert ledger.add(NotificationPayload('reply','m1',None,'c1'))
    assert not ledger.persistence_error

def test_storage_failure_retains_in_memory_count(tmp_path,monkeypatch):
    from grangerpet.credentials import CredentialError
    def fail(*args,**kwargs):raise CredentialError('unavailable')
    monkeypatch.setattr('grangerpet.pet_notifications.CredentialsStore._protect',fail)
    ledger=UnreadLedger(tmp_path/'unread.dpapi');ledger.add(NotificationPayload('reply','m1',None,'c1'))
    assert len(ledger.unread)==1 and ledger.persistence_error

@pytest.mark.parametrize('dpr',[1.,1.25,1.5])
@pytest.mark.parametrize('count',[1,2,12,100])
def test_compact_pixel_envelope_red_counter_and_dpi(app,dpr,count):
    image=QImage(round(64*dpr),round(48*dpr),QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(dpr);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);PetNotification.paint_letter(painter,'reply',notification_pose(1),count);painter.end()
    assert image.pixelColor(0,0).alpha()==0
    assert image.pixelColor(round(10*dpr),round(20*dpr)).alpha()==255
    assert image.pixelColor(round(46*dpr),round(6*dpr)).red()>100
    assert image.pixelColor(round(46*dpr),round(6*dpr)).green()<130
    assert set(bytes(image.constBits())[3::4]).issubset({0,255})

@pytest.mark.parametrize('character',[QRect(0,0,219,219),QRect(781,581,219,219),QRect(400,300,219,219)])
def test_anchor_inside_screen_without_overlapping_character(character):
    bounds=QRect(0,0,1000,800);size=QSize(64,48);rect=QRect(notification_position(character,bounds,size),size)
    assert bounds.contains(rect) and not rect.intersects(character)

def test_dock_clamped_to_screen_without_changing_original_size():
    screen=QRect(0,0,1280,800);main=QRect(0,0,1280,800);size=QSize(219,219)
    dock=QRect(1040,600,240,350)
    position=PetWindow._safe_overlay_position(QPoint(),size,main,screen,dock)
    assert position is None  # partial offscreen dock is not accepted as a fit
    dock=QRect(1040,500,240,300);position=PetWindow._safe_overlay_position(QPoint(),size,main,screen,dock)
    assert screen.contains(QRect(position,size))

def test_real_terminal_signal_and_cancel_do_not_count_incomplete_messages(pet):
    chat=pet.panel.chat_widget;pet.panel.showMinimized()
    for kind in ['paused','cancelled']:
        chat.turn_completed.emit({'kind':kind,'message_id':'incomplete','conversation_id':chat.conversation_id})
    assert pet.notification.unread_count==0
    chat.turn_completed.emit({'kind':'reply','message_id':'actual_final','conversation_id':chat.conversation_id})
    assert pet.notification.unread_count==1
    chat.turn_completed.emit({'kind':'cancelled'})
    assert pet.notification.unread_count==1

def test_exact_encrypted_conversation_receiver_then_viewport_ack(pet,app,monkeypatch):
    chat=pet.panel.chat_widget;chat._append('user','Первый тестовый диалог');chat._append('model','Сохранённый ответ')
    conversation=chat.conversation_id;message=chat.messages[-1]['id'];chat._save_archive();chat.new_conversation()
    pet.panel.showMinimized();chat.turn_completed.emit({'kind':'reply','message_id':message,'index':1,'conversation_id':conversation})
    assert pet.notification.unread_count==1 and pet.notification.isVisible()
    QTest.mouseClick(pet.notification,Qt.MouseButton.LeftButton,pos=QPoint(24,28));app.processEvents()
    assert chat.conversation_id==conversation and chat.messages[-1]['id']==message
    assert pet.panel.isVisible() and not pet.panel.isMinimized()
    assert pet.notification.unread_count==1
    monkeypatch.setattr(pet.panel,'notification_context',lambda:{'active':True,'conversation_id':conversation})
    assert not pet.panel.report_messages_seen('wrong',[message])
    assert not pet.panel.report_messages_seen(conversation,['fake'])
    assert pet.panel.report_messages_seen(conversation,[message])
    assert pet.notification.unread_count==0

def test_explicit_successful_clear_removes_stale_message_references(pet):
    pet.notify('reply','to_delete',conversation_id='c1');assert pet.notification.unread_count==1
    pet.panel.report_messages_removed('c1',['to_delete'])
    assert pet.notification.unread_count==0

def test_seen_ack_cannot_premark_streaming_message_before_completion(pet,monkeypatch):
    chat=pet.panel.chat_widget;chat._append('model','Ещё не завершено')
    identifier=chat.messages[-1]['id'];chat._busy=True;chat._stream_index=len(chat.messages)-1
    monkeypatch.setattr(pet.panel,'notification_context',lambda:{'active':True,'conversation_id':chat.conversation_id})
    assert not pet.panel.report_messages_seen(chat.conversation_id,[identifier])
    chat._busy=False;chat._stream_index=None
    pet.notify('reply',identifier,conversation_id=chat.conversation_id)
    assert pet.notification.unread_count==1

def test_dock_does_not_persist_temporary_position(pet,monkeypatch):
    pet.move(220,300);home=pet.pos();state={'active':True,'geometry':QRect(0,0,800,800),'dock':QRect(560,0,240,800)}
    monkeypatch.setattr(pet.panel,'desktop_window_state',lambda:state)
    pet._sync_overlay_placement();assert pet.pos()!=home
    pet._save_position();saved=pet.store.load();assert (saved.x,saved.y)==(home.x(),home.y())
    state['active']=False;pet._sync_overlay_placement();assert pet.pos()==home


def test_owned_modal_keeps_inactive_main_docked_but_unrelated_dialog_does_not(pet,monkeypatch):
    panel=pet.panel;owned=QMessageBox(panel);unrelated=QMessageBox()
    modal=[owned];foreground=[None]
    monkeypatch.setattr(panel,'desktop_surface',object())
    monkeypatch.setattr(panel,'isVisible',lambda:True)
    monkeypatch.setattr(panel,'isMinimized',lambda:False)
    monkeypatch.setattr(panel,'isActiveWindow',lambda:False)
    monkeypatch.setattr(panel,'hermione_dock_geometry',lambda:QRect(560,0,240,800))
    monkeypatch.setattr(QApplication,'activeWindow',staticmethod(lambda:foreground[0]))
    monkeypatch.setattr(QApplication,'activeModalWidget',staticmethod(lambda:modal[0]))
    try:
        state=panel.desktop_window_state()
        assert state['active'] and state['obstructions']==[owned.frameGeometry()]
        modal[0]=unrelated
        state=panel.desktop_window_state()
        assert not state['active'] and state['obstructions']==[]
        modal[0]=None
        assert not panel.desktop_window_state()['active']
        foreground[0]=owned
        assert panel.desktop_window_state()['active']
        foreground[0]=unrelated
        assert not panel.desktop_window_state()['active']
    finally:
        owned.deleteLater();unrelated.deleteLater()


def test_modal_overlap_suppresses_overlay_then_restores_without_losing_home_or_unread(pet,monkeypatch):
    bounds=pet.screen().availableGeometry()
    home=QPoint(bounds.left()+20,bounds.top()+20);pet.move(home)
    state={'active':True,'geometry':QRect(bounds),
        'dock':QRect(bounds.right()-239,bounds.top(),240,bounds.height()),'obstructions':[]}
    monkeypatch.setattr(pet.panel,'desktop_window_state',lambda:state)
    pet.notify('reply','held_while_modal',conversation_id='modal_conversation')
    pet._sync_overlay_placement();docked=pet.pos()
    assert docked!=home and pet.isVisible() and pet.notification.isVisible()
    state['obstructions']=[QRect(docked,pet.size())]
    pet._sync_overlay_placement()
    assert pet._dock_suppressed and not pet.isVisible() and not pet.notification.isVisible()
    assert pet._dock_home==home and pet.notification.unread_count==1
    pet._save_position();saved=pet.store.load()
    assert (saved.x,saved.y)==(home.x(),home.y())
    state['obstructions']=[];pet._sync_overlay_placement()
    assert not pet._dock_suppressed and pet.isVisible() and pet.pos()==docked
    assert pet.notification.isVisible() and pet.notification.unread_count==1
    state['active']=False;pet._sync_overlay_placement()
    assert pet.pos()==home and pet._dock_home is None and pet.isVisible()
    state['active']=True;state['obstructions']=[QRect(docked,pet.size())]
    pet._sync_overlay_placement();assert pet._dock_suppressed
    stopped=[];pet.stopped.connect(lambda:stopped.append(True))
    pet.shutdown();pet.shutdown();pet._sync_overlay_placement()
    assert stopped==[True] and not pet.isVisible() and not pet.notification.isVisible()
    assert pet.pos()==home and not pet.frame_timer.isActive() and not pet.cursor_timer.isActive()
    saved=pet.store.load();assert (saved.x,saved.y)==(home.x(),home.y())
