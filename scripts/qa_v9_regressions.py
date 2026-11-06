"""Native V9 regression diagnostics in an owned, encrypted QA profile."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.qa_clean_release import isolated_environment, wait_for
from scripts.qa_workspace_v7 import V7Session


def run(exe, output, observations, *, baseline=False, source=False):
    from PIL import Image
    from PySide6.QtCore import QCoreApplication
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.research_canvas import CanvasStore
    from scripts.qa_canvas_stress import observed_document

    app = QCoreApplication.instance() or QCoreApplication([])
    output.mkdir(parents=True, exist_ok=False)
    result = {
        'origin': 'native-source' if source else 'frozen-Windows-EXE',
        'exe_sha256': None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
        'baseline': baseline,
        'data_origin': 'replay_of_saved_public_Maigret_observations',
        'fresh_Maigret_requests': 0,
        'checks': [],
        'passed': False,
    }

    def save():
        (output / 'report.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        save()
        print(json.dumps(result['checks'][-1]), flush=True)

    with tempfile.TemporaryDirectory(prefix='native-', dir=output) as name:
        directory = Path(name)
        with isolated_environment(directory):
            SettingsStore().save(Settings(
                source_root=str(ROOT), ai_provider='none', cursor_reaction=False, reduced_motion=True))
            store = CanvasStore(InvestigationJournal(directory / 'appdata/GrangerPet/investigations'))
            document, _ = observed_document(observations, 'username_maigret')
            document['view']['ui']['initial_layout'] = 'identity'
            document = store.save(document, 0)
            github = next(node for node in document['entities']
                          if node['type'] == 'public_profile' and node['attributes'].get('platform') == 'github')
            session = V7Session(exe, directory, source=source)

            def capture(name):
                session.command('qa_snapshot', {'name': name})
                path = directory / (name + '-search.png')

                def ready():
                    try:
                        with Image.open(path) as image:
                            image.verify()
                        return True
                    except (OSError, ValueError):
                        return False

                wait_for(ready, 12)
                (output / (name + '.png')).write_bytes(path.read_bytes())

            try:
                session.start(0)
                session.click('Поиск')
                session.click('Моё полотно' if baseline else 'Мой граф')
                session.open_document(document['id'])
                session.select(github['id'])
                before = deepcopy(session.document())
                for _ in range(3):
                    session.action('input', {'kind': 'double_click', 'at': session.point(github['id'])})
                    time.sleep(.35)
                time.sleep(1)
                state = session.canvas()
                check('github_double_click_keeps_process_and_graph',
                      session.process.poll() is None and len(session.document()['entities']) == len(before['entities']))
                check('github_double_click_has_no_bridge_error', not state.get('error'))
                result['double_click_error'] = str(state.get('error') or '')[:240]
                result['double_click_queue_pending'] = session.metrics()['queue_pending']
                viewer_open = bool(session.find('Закрыть изображение')[0])
                check('profile_double_click_opens_details_instead_of_avatar_viewer', not viewer_open)
                capture('github-double-click')
                if viewer_open:
                    result['double_click_diagnostics'] = session.status().get('desktop', {}).get('diagnostics', [])
                    (output / 'double-click-dom-private.json').write_text(
                        json.dumps(session.dom(), ensure_ascii=False), encoding='utf-8')
                    session.stop()
                    session.start(1)
                    session.click('Поиск')
                    session.click('Моё полотно' if baseline else 'Мой граф')
                    session.open_document(document['id'])
                if result['double_click_queue_pending']:
                    result['phone_check_skipped_due_to_existing_failed_queue'] = True
                else:
                    session.click('Новый объект')
                    session.pick('Тип нового узла', 'Телефон', 'Телефон')
                    session.fill('Телефон', '77001234567')
                    session.click('Добавить объект')
                    time.sleep(1)
                    result['invalid_phone_queue_pending'] = session.metrics()['queue_pending']
                    result['invalid_phone_error'] = str(session.canvas().get('error') or '')[:240]
                    session.fill('Телефон', '+77001234567')
                    session.click('Добавить объект')
                    time.sleep(1.5)
                    check('corrected_phone_saves_after_validation_failure', any(
                        node['type'] == 'phone' and node['attributes'].get('value') == '+77001234567'
                        for node in session.document()['entities']))
                    check('phone_validation_does_not_block_mutation_queue', session.metrics()['queue_pending'] == 0)
                    capture('phone-correction')
                result['passed'] = all(check['passed'] for check in result['checks'])
            except BaseException as error:
                result.update(error_type=type(error).__name__, error=str(error)[:240])
                for path in directory.glob('process-*.log'):
                    (output / path.name).write_bytes(path.read_bytes())
                for index, path in enumerate((directory / 'appdata/GrangerPet/logs').glob('*.log')):
                    (output / f'runtime-{index}-private.log').write_bytes(path.read_bytes())
                save()
                raise
            finally:
                session.stop()
                save()
    result['temporary_profile_removed'] = not directory.exists()
    save()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--source', action='store_true')
    args = parser.parse_args()
    run(args.exe.resolve(), args.output.resolve(), args.observations.resolve(), baseline=args.baseline, source=args.source)
