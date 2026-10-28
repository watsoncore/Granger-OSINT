"""Narrow native secret editor; renderer receives presence flags only."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout,
                               QLabel, QLineEdit, QCheckBox)

from .credentials import CredentialError, get_secret, set_secret


SERVICES = {
    'deepseek': ('DeepSeek — ключ шлюза', (('deepseek_api_key', 'API-ключ'),)),
    'google': ('Google Search API', (('google_api_key', 'API-ключ'),)),
    'vk': ('VK — официальный API', (('vk_token', 'Access token'),)),
    'telegram': ('Telegram — разрешённая сессия', (('telegram_api_hash', 'API hash'), ('telegram_session', 'StringSession'))),
    'instagram': ('Instagram — разрешённая сессия', (('instagram_session', 'Cookies JSON'),)),
}


def credential_presence(*, getter=get_secret):
    result = {}
    for service, (_, names) in SERVICES.items():
        try:
            result[service] = all(bool(getter(name)) for name, _ in names)
        except CredentialError:
            result[service] = False
    return result


class CredentialDialog(QDialog):
    def __init__(self, service, parent=None, *, getter=get_secret, setter=set_secret):
        if service not in SERVICES:
            raise ValueError('Неизвестный источник учётных данных.')
        super().__init__(parent)
        self.service, self.getter, self.setter = service, getter, setter
        title, names = SERVICES[service]
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setModal(True)
        self.fields, self.deletions = {}, {}
        layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setStyleSheet('font-size:19px;font-weight:600;color:#f2f3f6')
        layout.addWidget(label)
        note = ('Секрет вводится только в этом окне и хранится в Windows Credential Manager. '
                'Пустое поле сохраняет текущий ключ. Проверка подключения доступна в настройках приложения.')
        if service == 'vk':
            note += ' Ранее опубликованный VK-токен необходимо отозвать и перевыпустить. Введите новый собственный токен.'
        if service in ('telegram', 'instagram'):
            note += ' Используйте только свою уже авторизованную сессию.'
        info = QLabel(note)
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        for name, caption in names:
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setMaxLength(500_000 if name.endswith('session') else 12_000)
            edit.setPlaceholderText('Сохранено в Windows' if getter(name) else 'Не настроено')
            form.addRow(caption, edit)
            remove = QCheckBox('Удалить сохранённое значение')
            form.addRow('', remove)
            self.fields[name], self.deletions[name] = edit, remove
        layout.addLayout(form)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Сохранить в Windows')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet('QDialog{background:#191c23;color:#edf0f6} QLabel,QCheckBox{color:#cbd0db;font-size:14px} '
            'QLineEdit{background:#10131a;border:1px solid #424958;border-radius:7px;padding:9px;color:#f4f5f8;font-size:15px} '
            'QPushButton{background:#303849;color:#f4f5f8;border:1px solid #525c70;border-radius:7px;padding:9px 14px;font-size:14px} '
            'QPushButton:focus{border-color:#a8b1ff} QPushButton:hover{background:#414c62}')

    def save(self):
        changes = {name: field.text().strip() for name, field in self.fields.items() if field.text().strip()}
        changes.update({name: '' for name, check in self.deletions.items() if check.isChecked() and name not in changes})
        previous, applied = {}, []
        try:
            previous = {name: self.getter(name) for name in changes}
            for name, value in changes.items():
                applied.append(name)
                self.setter(name, value)
                if self.getter(name) != value:
                    raise CredentialError('Windows не подтвердила сохранение.')
        except Exception:
            for name in reversed(applied):
                try:
                    self.setter(name, previous[name])
                except Exception:
                    pass
            self.status.setText('Windows не смогла сохранить учётные данные. Проверьте доступ к защищённому хранилищу.')
            return
        self._clear()
        self.accept()

    def _clear(self):
        for field in self.fields.values():
            field.clear()

    def reject(self):
        self._clear()
        super().reject()
