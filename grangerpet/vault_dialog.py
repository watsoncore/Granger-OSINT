"""Native passphrase entry; no password ever crosses the renderer protocol."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout
from .ui_jobs import UiJob


class VaultDialog(QDialog):
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        from . import credentials
        if operation not in ('create','unlock','change'): raise ValueError('Неизвестная операция хранилища.')
        self.operation=operation
        self.setWindowTitle({'create':'Создать переносимое хранилище','unlock':'Разблокировать хранилище','change':'Сменить пароль хранилища'}[operation])
        self.setMinimumWidth(440)
        self._job=None
        layout=QVBoxLayout(self)
        note=QLabel('Парольная фраза хранится только в памяти этого процесса. Восстановить забытый пароль невозможно. '
            'Используйте не менее 12 символов. Прежние данные сохраняются при миграции.')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();self.fields={}
        names=[('password','Парольная фраза')]
        if operation=='create': names.append(('repeat','Повторите фразу'))
        if operation=='change': names=[('password','Текущая фраза'),('new','Новая фраза'),('repeat','Повторите новую фразу')]
        for name,label in names:
            field=QLineEdit();field.setEchoMode(QLineEdit.EchoMode.Password);field.setMaxLength(4096)
            self.fields[name]=field;form.addRow(label,field)
        layout.addLayout(form)
        self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.submit);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)

    def submit(self):
        if self._job: return
        from . import credentials
        password=self.fields['password'].text()
        new=self.fields.get('new');new=new.text() if new else password
        if 'repeat' in self.fields and new!=self.fields['repeat'].text():
            self.status.setText('Парольные фразы не совпадают.');return
        action={'create':lambda:credentials.create_portable_vault(password),
                'unlock':lambda:credentials.unlock_portable_vault(password),
                'change':lambda:credentials.change_vault_passphrase(password,new)}[self.operation]
        for field in self.fields.values(): field.clear();field.setEnabled(False)
        self.buttons.setEnabled(False);self.status.setText('Проверка и защищённая запись…')
        job=UiJob(action,self);self._job=job
        def done(result,error):
            self._job=None;job.function=lambda:None;job.deleteLater()
            if error:
                self.status.setText(error);self.buttons.setEnabled(True)
                for field in self.fields.values(): field.setEnabled(True)
            else: self.accept()
        job.done.connect(done);job.start()

    def reject(self):
        if self._job: return
        for field in self.fields.values(): field.clear()
        super().reject()
