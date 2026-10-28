"""Reproducible UI/DPI fixtures; no network, real credentials or fake API calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE='''# ТЕСТОВЫЙ отчёт: публичные источники

Это **локальный тест интерфейса**, не результат живого API. Есть *курсив*, `inline-code` и [безопасная ссылка](https://example.org/).

## Сведения

1. Первый пункт.
   - Вложенный пункт со свидетельством `ev_0123456789abcdef0123`.
2. Второй пункт.

> Совпадение никнейма не доказывает общего владельца.

| Источник | Статус | Свидетельство | URL | Дата |
| --- | --- | --- | --- | --- |
| Публичная страница | Прочитана | ev_0123456789abcdef0123 | https://example.org/ | 2026-10-28 |
| Поисковая выдача | Сниппет | ev_1123456789abcdef0123 | https://example.org/long-path | 2026-10-28 |

## Код

```python
print("Привет, Гермиона!")
```

---

Исходные свидетельства не изменяются при правке отчёта в Canvas.
'''


def child(scale):
    os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_SCALE_FACTOR']=str(scale)
    sys.path.insert(0,str(ROOT))
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from grangerpet.panel import OsintPanel
    from grangerpet.config import Settings
    from grangerpet.typography import apply_app_font
    app=QApplication([]);app.setStyle('Fusion')
    for name in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf','SegUIVar.ttf'):
        p=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name
        if p.is_file():QFontDatabase.addApplicationFont(str(p))
    apply_app_font(app)
    out=ROOT/f'output/master-qa/ui-{round(scale*100)}';out.mkdir(parents=True,exist_ok=True)
    if(out/'report.json').exists():raise RuntimeError('Preserve previous UI reports')
    checks=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def settle():app.processEvents();QTest.qWait(220);app.processEvents()
    def capture(name,widget):check('capture_'+name,widget.grab().save(str(out/(name+'.png'))))
    with tempfile.TemporaryDirectory(prefix='GrangerPet-master-fixture-') as temp:
        os.environ['APPDATA']=temp
        panel=OsintPanel(Settings());panel.resize(1000,740);panel.show();panel.show_chat();settle()
        chat=panel.chat_widget;chat._append('user','Покажи ТЕСТОВЫЙ отчёт.');bubble=chat._append('model',SOURCE);settle()
        capture('markdown-chat',panel)
        check('headings',bubble.text_view.document().begin().blockFormat().headingLevel()==1)
        check('table',len(list(bubble.text_view._tables()))==1)
        check('markdown_rendered','**локальный' not in bubble.text_view.toPlainText())
        check('original_source_retained',bubble.message_text==SOURCE)
        check('readable_bubble_width',bubble.width()<=900)
        bubble.canvas_button.click();settle();check('canvas_opened_from_real_message',panel.workspace.currentWidget() is panel.canvas)
        capture('canvas-view',panel)
        canvas=panel.canvas;check('outline',canvas.heading_list.count()==3)
        canvas.edit_button.setChecked(True);canvas.editor.appendPlainText('\n\n## Правка\nТЕСТОВАЯ правка документа.')
        saved=canvas.save_document();exported=canvas.export_document(out/'exported.md');settle();capture('canvas-edit',panel)
        check('save_and_export_real',saved.is_file() and 'ТЕСТОВАЯ правка' in exported.read_text(encoding='utf-8'))
        check('chat_original_immutable',bubble.message_text==SOURCE)
        canvas.back.click();settle();check('back_keeps_chat',panel.workspace.currentWidget() is panel.mode_tabs)
        panel.resize(460,420);settle();capture('minimum-chat',panel)
        panel.open_canvas(SOURCE);settle();capture('minimum-canvas',panel)
        check('minimum_does_not_expand',panel.width()==460 and panel.height()==420)
        panel.resize(1450,850);settle();capture('large-canvas',panel)
        panel.show_chat();chat.history.update_message(bubble,SOURCE+'\n\n**Потоковая допись**');chat.history.flush_updates();settle()
        check('one_streaming_bubble',len(chat.history.bubbles)==2)
        capture('stream-completed',panel)
        panel.shutdown();panel.close()
    report={'mode':'offscreen Qt scale fixture, not Windows DPI change','scale':scale,'actual_dpr':panel.devicePixelRatioF(),
            'fixture_content':True,'real_api_called':False,'checks':checks,'passed':all(c['passed'] for c in checks)}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'scale':scale,'checks':len(checks),'passed':report['passed']}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scale',type=float);args=parser.parse_args()
    if args.scale:child(args.scale)
    else:
        for scale in (1,1.25,1.5):
            subprocess.run([sys.executable,__file__,'--scale',str(scale)],cwd=ROOT,check=True,timeout=90)


if __name__=='__main__':main()
