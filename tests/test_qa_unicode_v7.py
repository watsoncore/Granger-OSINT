from PySide6.QtWidgets import QApplication,QLineEdit
from grangerpet.qa_input import deliver


def test_native_input_method_delivers_russian_without_global_clipboard():
    app=QApplication.instance() or QApplication([])
    edit=QLineEdit();edit.show();edit.setFocus();app.processEvents()
    deliver(edit,{'kind':'text','text':'Русский текст · UTF-8'})
    assert edit.text()=='Русский текст · UTF-8'
    edit.close()
