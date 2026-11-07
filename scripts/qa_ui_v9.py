"""Inspect common controls across all settings sections in an isolated native EXE.

No provider request, credential, vault migration or pet setting is changed.
Snapshots contain only the empty QA profile and generated appearance settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.qa_clean_release import isolated_environment, wait_for, QaFailure
from scripts.qa_workspace_v7 import V7Session

CATEGORIES = ('ИИ и провайдеры', 'Расследования', 'Инструменты', 'Оформление',
              'Гермиона', 'Уведомления', 'Данные')


def run(exe: Path, output: Path, *, source=False, app_style='minimal'):
    from PIL import Image, ImageStat
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings, SettingsStore

    app = QCoreApplication.instance() or QCoreApplication([])
    output.mkdir(parents=True, exist_ok=False)
    report = {'origin': 'native-source' if source else 'frozen-Windows-EXE', 'exe_sha256': None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
              'app_style':app_style,
              'checks': [], 'categories': [], 'captures': [], 'passed': False}

    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        save()
        print(json.dumps(report['checks'][-1]), flush=True)
        if not condition:
            raise QaFailure(name)

    with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as name:
        directory = Path(name)
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT), ai_provider='deepseek' if app_style=='minimal' else 'none',
                cursor_reaction=False, reduced_motion=True,
                workspace_appearance=json.dumps({'appStyle':app_style,'theme': 'azure', 'glow': 0, 'reflection': 3})))
            session = V7Session(exe, directory,source)

            def category(label):
                # Hermione also exists in the main sidebar. Use the settings
                # category beyond the first navigation column, then real input.
                def find():
                    rows = [e for e in session.dom().get('elements', []) if (e.get('text') == label or e.get('label') == label)
                            and e.get('width', 0) > 0 and e.get('hit')]
                    return max(rows, key=lambda e: e['x']) if rows else None
                for attempt in range(3):
                    element = wait_for(find, 8)
                    session.action('input', {'kind': 'click', 'at': [element['x'] + element['width']/2,
                                                                  element['y'] + min(16, element['height']/2)]})
                    try:
                        wait_for(lambda: label in session.dom().get('headings', []), 3)
                        session.idle()
                        return
                    except QaFailure:
                        if attempt == 2:
                            raise

            def capture(label):
                session.command('qa_snapshot', {'name': label})
                source = directory / (label + '-search.png')
                def ready():
                    try:
                        with Image.open(source) as image:
                            return min(image.size) > 300 and max(ImageStat.Stat(image.convert('RGB')).stddev) > 5
                    except (ValueError, OSError):
                        return False
                wait_for(ready, 12)
                target = output / (label + '.png')
                target.write_bytes(source.read_bytes())
                report['captures'].append({'name': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
                save()

            try:
                session.start(0)
                session.click('Настройки')
                for index, label in enumerate(CATEGORIES):
                    category(label)
                    dom = session.dom()
                    if 'appStyle' in dom:
                        check('settings_'+str(index)+'_global_material',dom['appStyle']==app_style and
                            (app_style!='minimal' or bool(dom.get('materials')) and all(row['shadow']=='none' and row['backdrop']=='none' for row in dom['materials'])))
                    report.setdefault('materials',{})[label]=dom.get('materials',[])
                    elements = [e for e in dom.get('elements', []) if e.get('width', 0) > 0 and e.get('height', 0) > 0]
                    checkboxes = [e for e in elements if e.get('type') in ('checkbox', 'radio')]
                    summaries = [e for e in elements if e.get('svgCount', 0) and not e.get('type') and not e.get('role')]
                    scrolls = [e['scroll'] for e in elements if e.get('scroll')]
                    report['categories'].append({'name': label, 'viewport': [dom.get('width'), dom.get('height')],
                        'native_selects': sum(e.get('type') == 'select-one' for e in elements),
                        'checkboxes': len(checkboxes), 'custom_checkbox_appearance': all(e.get('appearance') == 'none' for e in checkboxes),
                        'svg_disclosures': len(summaries), 'themed_scroll_ancestors': len(scrolls),
                        'scrollbar_colors': sorted(set(s.get('color', '') for s in scrolls)),
                        'overflow': dom.get('overflow'), 'font': dom.get('font')})
                    check('settings_' + str(index) + '_custom_controls_and_no_page_overflow',
                          not dom.get('overflow') and not any(e.get('type') == 'select-one' for e in elements)
                          and all(e.get('appearance') == 'none' for e in checkboxes)
                          and all(s.get('color') not in ('', None, 'auto') for s in scrolls)
                          and dom.get('font', {}).get('loaded'))
                    capture('settings-' + str(index))
                    if label == 'ИИ и провайдеры' and app_style == 'minimal':
                        initial = session.snapshot()
                        check('deepseek_profile_is_isolated_and_keyless',
                              initial['connection']['provider'] == 'deepseek'
                              and not initial['connection']['canSend'] and not initial['credentials'].get('deepseek'))
                        session.click('Проверить подключение')
                        keyless = wait_for(lambda: row if (row := session.snapshot()['connection']).get('error') else None, 12)
                        check('deepseek_keyless_check_cannot_enable_chat',
                              keyless['status'] == 'not_configured' and not keyless['canSend'])
                    if label == 'Инструменты' and 'appStyle' in dom:
                        session.fill('Найти инструмент', 'Норвегия компания')
                        found = wait_for(lambda: 'Brønnøysund · компании NO' in session.dom().get('headings', []), 10)
                        check('settings_source_directory_searches_by_country_and_object', found)
                        session.pick('Категория источника', 'Компании и реестры', 'Компании')
                        capture('settings-source-directory')

                category('Расследования')
                target = 'При достижении бюджета'
                session.click(target)
                session.click('Найти: ' + target)
                session.action('input', {'kind': 'key', 'key': 'down'})
                session.action('input', {'kind': 'key', 'key': 'escape'})
                check('custom_select_escape_restores_without_change',
                      wait_for(lambda: not session.find('Найти: ' + target)[0], 8)
                      and session.find(target)[0].get('value') == 'pause')
                session.click(target)
                session.fill('Найти: ' + target, 'Завершить')
                session.action('input', {'kind': 'key', 'key': 'down'})
                session.action('input', {'kind': 'key', 'key': 'enter'})
                check('custom_select_search_and_keyboard_commit',
                      wait_for(lambda: session.find(target)[0].get('value') == 'stop', 8))
                capture('select-keyboard')
                session.command('qa_window_mode', {'mode': 'fullscreen'})
                wait_for(lambda: session.snapshot()['window']['fullscreen'])
                session.click(target)
                session.click('Найти: ' + target)
                session.action('input', {'kind': 'key', 'key': 'escape'})
                wait_for(lambda: not session.find('Найти: ' + target)[0], 8)
                check('fullscreen_escape_closes_menu_before_window', session.snapshot()['window']['fullscreen'])
                session.action('input', {'kind': 'key', 'key': 'escape'})
                check('fullscreen_escape_without_menu_exits',
                      wait_for(lambda: not session.snapshot()['window']['fullscreen'], 8))
                # This is an unsaved local QA draft; no backend agent settings
                # or provider connection is invoked by the interaction.
                session.command('qa_window_mode', {'mode': 'size', 'size': [1050, 720]})
                category('Оформление')
                check('narrow_settings_no_horizontal_overflow', not session.dom().get('overflow'))
                capture('settings-narrow')
                report['passed'] = True
                save()
            except BaseException as error:
                report.update(error_type=type(error).__name__, error=str(error)[:200])
                (output / 'failed-dom-private.json').write_text(json.dumps(session.dom(), ensure_ascii=False, indent=2), encoding='utf-8')
                save()
                raise
            finally:
                session.stop()
    report['temporary_profile_removed'] = not directory.exists()
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source',action='store_true')
    parser.add_argument('--app-style',choices=('minimal','glass'),default='minimal')
    args = parser.parse_args()
    run(args.exe.resolve(), args.output.resolve(),source=args.source,app_style=args.app_style)
