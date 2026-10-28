import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from grangerpet.credential_dialog import CredentialDialog, credential_presence


def test_editor_never_preloads_saved_secret_and_blank_keeps_it():
    app=QApplication.instance() or QApplication([])
    values={'vk_token':'old-private-fixture'}
    dialog=CredentialDialog('vk',getter=lambda key:values.get(key,''),setter=lambda key,value:values.update({key:value}))
    field=dialog.fields['vk_token']
    assert field.text()=='' and field.echoMode()==QLineEdit.EchoMode.Password
    assert 'old-private-fixture' not in dialog.findChildren(QLineEdit)[0].placeholderText()
    dialog.save()
    assert values['vk_token']=='old-private-fixture' and dialog.result()==QDialog.DialogCode.Accepted
    dialog.deleteLater();app.processEvents()


def test_save_and_delete_use_vault_and_clear_native_fields():
    app=QApplication.instance() or QApplication([])
    values={}
    getter=lambda key:values.get(key,'')
    setter=lambda key,value:values.update({key:value})
    dialog=CredentialDialog('deepseek',getter=getter,setter=setter)
    dialog.fields['deepseek_api_key'].setText('new-private-fixture')
    dialog.save()
    assert values['deepseek_api_key']=='new-private-fixture'
    assert not dialog.fields['deepseek_api_key'].text()
    assert credential_presence(getter=getter)['deepseek'] is True
    remove=CredentialDialog('deepseek',getter=getter,setter=setter)
    remove.deletions['deepseek_api_key'].setChecked(True);remove.save()
    assert not values['deepseek_api_key']
    dialog.deleteLater();remove.deleteLater();app.processEvents()


def test_partial_write_rolls_back_and_cancel_clears_input():
    app=QApplication.instance() or QApplication([])
    values={'telegram_api_hash':'previous-hash','telegram_session':'previous-session'}
    def setter(key,value):
        values[key]=value
        if value=='failure-fixture': raise RuntimeError('untrusted body secret')
    dialog=CredentialDialog('telegram',getter=lambda key:values.get(key,''),setter=setter)
    dialog.fields['telegram_api_hash'].setText('changed-hash')
    dialog.fields['telegram_session'].setText('failure-fixture')
    dialog.save()
    assert values=={'telegram_api_hash':'previous-hash','telegram_session':'previous-session'}
    assert 'untrusted body' not in dialog.status.text()
    dialog.reject()
    assert not any(field.text() for field in dialog.fields.values())
    dialog.deleteLater();app.processEvents()
