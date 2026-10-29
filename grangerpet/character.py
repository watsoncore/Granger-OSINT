"""One event reducer shared by the native companion and workspace state.

No polling, model-invented completion, or replacement sprites. Rendering remains
in the existing AnimationController/PetLifeController and their cached assets.
"""
from PySide6.QtCore import QObject, Signal

STATES=('idle','listening','thinking','searching','reading','working','happy','shy','annoyed','resting','sleeping','notification','error')
ASSET_GAPS={'shy':'dedicated shy facial frames','annoyed':'dedicated annoyed facial frames','coding':'laptop typing frames'}
_VISUAL={'idle':'idle','listening':'hover','thinking':'thinking','searching':'working','reading':'thinking',
         'working':'working','happy':'happy','shy':'idle','annoyed':'idle','resting':'idle','sleeping':'idle',
         'notification':'hover','error':'error'}


class CharacterController(QObject):
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.state='idle';self.busy=False;self.tool='';self.unread=False;self.life_action='';self.last_event='application.ready'

    def _set(self,state,event):
        before=self.snapshot()
        self.state=state;self.last_event=event
        if before!=self.snapshot(): self.changed.emit()

    def activity(self,state):
        if state in ('thinking','working'):
            self.busy=True;self.life_action='';self._set(state,'agent.task.started')
        elif state in ('happy','error'):
            self.busy=False;self.tool='';self._set(state,'agent.answer.ready' if state=='happy' else 'agent.tool.failed')
        elif state=='idle':
            self.busy=False;self.tool='';self._set('notification' if self.unread else 'idle','agent.task.cancelled')

    def handle_event(self,name,payload=None):
        payload=payload if isinstance(payload,dict) else {}
        if name=='chat.message.received':
            if not self.busy: self._set('listening',name)
        elif name=='agent.task.started':
            self.busy=True;self.life_action='';self._set('thinking',name)
        elif name=='agent.tool.started':
            self.busy=True;self.life_action='';self.tool=str(payload.get('tool',''))
            state='reading' if self.tool in ('web_read','evidence_get','image_ocr','image_metadata') else 'searching'
            self._set(state,name)
        elif name=='agent.tool.completed':
            if self.busy: self._set('thinking',name)
        elif name=='agent.tool.failed':
            # One failed source must not pretend the entire ongoing task ended.
            self._set('thinking' if self.busy else 'error',name)
        elif name in ('agent.answer.ready','agent.task.cancelled'):
            self.busy=False;self.tool='';self._set('happy' if name=='agent.answer.ready' else 'idle',name)
        elif name=='notification.created':
            self.unread=True
            if not self.busy: self._set('notification',name)
        elif name=='notification.read':
            self.unread=False
            if not self.busy: self._set('idle',name)
        elif name=='application.user_returned':
            self.life_action=''
            if not self.busy: self._set('listening',name)
        elif name.startswith('coding.'):
            # Extension seam only: no terminal, code execution or laptop art.
            if name not in ('coding.started','coding.editing','coding.testing','coding.failed','coding.completed'): return False
            self.busy=name not in ('coding.failed','coding.completed')
            self._set('working' if self.busy else 'error' if name=='coding.failed' else 'happy',name)
        else: return False
        return True

    def life(self,action):
        if action==self.life_action: return
        self.life_action=action
        if self.busy: return
        state='reading' if action=='reading' else 'sleeping' if action=='sleep' else 'resting' if action in ('yawn','settle','away') else 'listening' if action in ('return','wake') else 'idle'
        self._set(state,'application.idle' if action else 'application.user_returned')

    def terminal_finished(self):
        if not self.busy and self.state in ('happy','error'):
            self._set('notification' if self.unread else 'idle','animation.completed')

    def snapshot(self):
        return {'state':self.state,'animation':_VISUAL[self.state],'busy':self.busy,'tool':self.tool,
                'event':self.last_event,'life_action':self.life_action,'unread':self.unread,
                'missing_assets':ASSET_GAPS}
