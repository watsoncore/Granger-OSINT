"""Owned Windows appearance and canvas acceptance with native file dialogs.

The three dialog prompts in dialog-request.json refer only to generated local QA
files. A desktop operator selects those files in the Windows dialogs. No user
profile, media, network request, or credential participates.
"""
from __future__ import annotations

import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.qa_clean_release import QaFailure, isolated_environment, wait_for
from scripts.qa_workspace_v7 import V7Session


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class AppearanceSession(V7Session):
    def find(self, label, *, role=None):
        element, dom = super().find(label, role=role)
        if element:
            return element, dom
        first_option = {'Расположение':'Заполнить','Где использовать':'Все расследования'}.get(label)
        element = next((entry for entry in dom.get('elements', []) if entry.get('width', 0) > 0 and (
            role=='button' and entry.get('type')=='button' and entry.get('text','').startswith(label)
            or first_option and entry.get('type')=='select-one' and entry.get('text','').startswith(first_option))), None)
        return element, dom

    def select_option(self, label, index):
        self.click(label)
        self.action('input', {'kind': 'key', 'key': 'home'})
        for _ in range(index):
            self.action('input', {'kind': 'key', 'key': 'down'})
        self.action('input', {'kind': 'key', 'key': 'enter'})


def run(exe, output, *, source=False):
    from PIL import Image, ImageDraw
    from PySide6.QtCore import QCoreApplication
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.research_canvas import CanvasStore, add_node, apply, new_document, record_canvas_event
    from grangerpet.credentials import open_bytes, seal_bytes
    from grangerpet.geoint.images import AttachmentStore

    app = QCoreApplication.instance() or QCoreApplication([])
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / 'report.json'
    marker = output / 'dialog-request.json'
    result = {'origin': 'native-source' if source else 'frozen-Windows-EXE', 'checks': [], 'captures': [], 'passed': False}
    if not source:
        with exe.open('rb') as stream:
            result['exe_sha256'] = file_digest(stream, 'sha256').hexdigest()
    fixture = output / 'synthetic-wallpaper.png'
    with Image.new('RGB', (1800, 1020), '#397888') as photo:
        draw = ImageDraw.Draw(photo)
        draw.rectangle((0, 0, 880, 1020), fill='#79c6b8')
        draw.ellipse((520, 120, 1280, 900), fill='#c2f2cb')
        draw.polygon([(0, 1020), (920, 555), (1800, 1020)], fill='#284364')
        photo.save(fixture)
    wallpaper_bytes = fixture.read_bytes()
    result['wallpaper_fixture_sha256'] = sha256(wallpaper_bytes).hexdigest()

    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        write_json(report_path, result)
        print(json.dumps(result['checks'][-1]), flush=True)
        if not condition:
            raise QaFailure(name)

    with tempfile.TemporaryDirectory(prefix='appearance-profile-', dir=output) as name:
        directory = Path(name)
        with isolated_environment(directory):
            settings = SettingsStore()
            settings.save(Settings(source_root=str(ROOT), ai_provider='none', cursor_reaction=False, reduced_motion=True))
            profile = directory / 'appdata/GrangerPet'
            store = CanvasStore(InvestigationJournal(profile / 'investigations'))
            images = AttachmentStore(profile / 'wallpapers', seal=seal_bytes, open_sealed=open_bytes)
            first = new_document('V8 QA · Связи и личный фон')
            node_ids = [add_node(first, {'type':'analyst_note','label':f'Синтетическая карточка {i + 1}',
                                       'position':{'x':(i % 3) * 330, 'y':(i // 3) * 220}}) for i in range(5)]
            for a, b in zip(node_ids[:3], node_ids[1:4]):
                first = apply(first, 'edge', {'from_id':a, 'to_id':b})
            record_canvas_event(first, 'node', node_ids[:1], 1)
            first = store.save(first, 0)
            second = store.save(new_document('V8 QA · Независимый фон'), 0)
            session = AppearanceSession(exe, directory, source)

            def snapshot(name):
                session.command('qa_snapshot', {'name':name})
                path = directory / (name + '-search.png')
                def ready():
                    try:
                        with Image.open(path) as image:
                            image.verify()
                        return True
                    except (OSError,ValueError):
                        return False
                wait_for(ready, 12)
                target = output / (name + '.png')
                shutil.copyfile(path, target)
                with Image.open(target) as image:
                    image.verify()
                result['captures'].append({'name':target.name, 'sha256':sha256(target.read_bytes()).hexdigest()})

            def prefs():
                raw = settings.load().workspace_appearance
                return json.loads(raw) if raw else {}

            def appearance():
                session.click('Настройки')
                session.click('Оформление')

            def canvas(identifier):
                session.click('Поиск')
                session.click('Моё полотно')
                session.open_document(identifier)

            def prompt(kind, path):
                write_json(marker, {'kind':kind, 'path':str(path)})
                print('DIALOG ' + kind, flush=True)

            def close_marker():
                marker.unlink(missing_ok=True)

            try:
                session.start(0)
                appearance()
                session.click('Тема: Midnight Azure')
                check('theme_preview_does_not_save', not prefs() and session.dom().get('theme')=='azure')
                session.click('Отмена')
                check('theme_cancel_keeps_saved_preferences', not prefs() and session.dom().get('theme')=='dark')
                session.click('Тема: Midnight Azure')
                session.click('Применить')
                wait_for(lambda: prefs().get('theme') == 'azure', 15)
                snapshot('theme-editor-azure')
                session.click('Гермиона')
                snapshot('main-azure')
                appearance()
                session.click('Тема: Crimson Noir')
                session.click('Применить')
                wait_for(lambda: prefs().get('theme') == 'crimson', 15)
                session.click('Гермиона')
                snapshot('main-crimson')
                appearance()
                session.click('Цвета, свечение и поверхности', role='button')
                session.fill('Выбранная карточка HEX', '#43d9bd')
                session.fill('Выбранная связь HEX', '#95adff')
                session.select_option('Режим свечения', 0)
                session.click('Применить')
                wait_for(lambda: prefs().get('colors', {}).get('node') == '#43d9bd', 15)
                check('custom_selection_colors_and_glow_persist', prefs()['colors']['edge'] == '#95adff' and prefs()['glow'] == 0)
                session.click('Обои полотна', role='button')
                session.click('Выбрать изображение')
                prompt('choose-wallpaper', fixture)
                wait_for(lambda: session.find('Убрать изображение')[0], 210)
                close_marker()
                session.select_option('Расположение', 1)
                session.click('Размытие')
                session.action('input', {'kind':'key','key':'home'})
                for _ in range(6):
                    session.action('input', {'kind':'key','key':'right'})
                snapshot('wallpaper-editor')
                session.click('Применить')
                wallpaper = wait_for(lambda: prefs().get('wallpaper') if prefs().get('wallpaper', {}).get('image') else None, 18)
                check('native_wallpaper_picker_stores_original_encrypted', images.read_bytes(wallpaper['image']) == wallpaper_bytes
                      and wallpaper_bytes not in next((profile / 'wallpapers').glob('*.gpi')).read_bytes())
                check('wallpaper_adjustments_persist', wallpaper['fit'] == 'contain' and wallpaper['blur'] == 6)
                check('wallpaper_is_not_graph_entity', len(store.load(first['id'])['entities']) == 5)
                session.select_option('Где использовать', 1)
                scope = session.find('Где использовать')[0]['value']
                session.select_option('Фон полотна', 5)
                session.click('Применить')
                wait_for(lambda: prefs().get('overrides', {}).get(scope, {}).get('source') == 'black', 15)
                check('investigation_override_separate_from_global', len(prefs()['overrides']) == 1 and prefs()['wallpaper']['image'] == wallpaper['image'])
                target = first['id'] if scope != first['id'] else second['id']
                canvas(target)
                time.sleep(1)
                snapshot('canvas-with-wallpaper')
                session.click('Проект')
                session.click('Снимок полотна')
                png = output / 'private-wallpaper-masked.png'
                prompt('save-masked-screenshot', png)
                wait_for(lambda: png.is_file() and png.stat().st_size, 210)
                close_marker()
                with Image.open(png) as hidden, Image.open(output / 'canvas-with-wallpaper.png') as visible:
                    def teal_area(image):
                        pixels=image.convert('RGB')
                        return sum(g>r+12 and b>r+8 and g>40 for x in range(0,pixels.width,16)
                                   for y in range(0,pixels.height,16) for r,g,b in (pixels.getpixel((x,y)),))
                    check('wallpaper_pixels_excluded_from_app_screenshot',teal_area(visible)>teal_area(hidden)+80)
                if not session.find('Снимок полотна')[0]:
                    session.click('Проект')
                session.click('Экспорт')
                package = output / 'investigation.granger.zip'
                prompt('save-private-free-package', package)
                wait_for(lambda: package.is_file() and package.stat().st_size, 210)
                close_marker()
                with zipfile.ZipFile(package) as archive:
                    check('wallpaper_and_local_history_excluded_from_portable_export', all(
                        wallpaper_bytes not in archive.read(name) and wallpaper['image'].encode() not in archive.read(name)
                        and b'"activity"' not in archive.read(name) for name in archive.namelist()))
                canvas(scope)
                snapshot('canvas-black-override')
                canvas(first['id'])
                session.click('Показать всё')
                session.idle()
                session.select(node_ids[0])
                session.click('Фокус')
                def count():
                    return int(session.metrics()['canvas'].get('modelNodes', 0))
                for depth in range(1, 4):
                    if depth > 1:
                        session.select_option('Глубина фокуса', depth - 1)
                    wait_for(lambda: count() == depth + 1, 15)
                    check(f'focus_depth_{depth}_uses_actual_neighbors', True)
                snapshot('canvas-focus')
                session.click('Выйти из фокуса')
                wait_for(lambda: count() == 5, 15)
                before = store.load(first['id'])
                session.click('История расследования')
                check('history_has_saved_action_with_node', bool(session.find('Показать связанные объекты')[0]))
                session.click('Закрыть историю')
                session.click('Чистое расследование')
                session.click('Полноэкранное окно Windows')
                wait_for(lambda: session.snapshot()['window']['fullscreen'], 15)
                snapshot('clean-fullscreen')
                viewport = session.metrics()['canvas']
                session.click('Показать редактор')
                inspector = session.metrics()['canvas']
                session.click('Закрыть редактор')
                check('clean_inspector_leaves_canvas_geometry', (viewport['width'], viewport['height']) == (inspector['width'], inspector['height']))
                session.click('Полноэкранное окно Windows')
                wait_for(lambda: not session.snapshot()['window']['fullscreen'], 15)
                colors = session.metrics()['canvas']
                check('canvas_uses_custom_node_edge_and_zero_glow', colors['selectedColor'] == '#43d9bd'
                      and colors['selectedEdgeColor'] == '#95adff' and colors['selectionGlow'] == '0')
                session.stop()
                session.start(1)
                canvas(first['id'])
                after = store.load(first['id'])
                check('restart_keeps_preferences_original_and_graph', prefs()['theme'] == 'crimson'
                      and prefs()['wallpaper']['image'] == wallpaper['image']
                      and prefs()['overrides'][scope]['source'] == 'black'
                      and images.read_bytes(wallpaper['image']) == wallpaper_bytes
                      and all(after[key] == before[key] for key in ('entities','relations','evidence','activity')))
                result['passed'] = True
            except BaseException as error:
                result.update(error_type=type(error).__name__, error=str(error)[:160])
                raise
            finally:
                close_marker()
                session.stop()
                write_json(report_path, result)
    result['temporary_profile_removed'] = not directory.exists()
    write_json(report_path, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to((ROOT / 'dist').resolve()):
        parser.error('QA artifacts must stay outside dist.')
    run(args.exe.resolve(), output, source=args.source)
