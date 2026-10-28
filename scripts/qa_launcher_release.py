"""Record native UI Launcher lifecycle observations, without driving the UI."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication
from grangerpet.ipc import send_command
from grangerpet.config import SettingsStore
from grangerpet.credentials import CredentialsStore
from qa_packaged_search import process_image


def main():
    app = QCoreApplication([])
    output = ROOT / 'output/deepseek-qa/launcher-final'
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'report.json'
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'tested_at_utc': datetime.now(timezone.utc).isoformat(),
        'exe_sha256': hashlib.sha256((ROOT / 'dist/GrangerPet.exe').read_bytes()).hexdigest(),
        'method': 'Actual final EXE buttons/Alt+F4 via Computer Use; IPC observes the independent process',
        'checks': [],
    }
    stage = sys.argv[1]
    launcher, pet = send_command('launcher', 'status'), send_command('pet', 'status')
    if stage == 'before':
        passed = bool(launcher) and not pet
    elif stage == 'started':
        passed = bool(launcher and pet and pet.get('running'))
        if passed:
            report['pet_pid'] = pet['pid']
            report['pet_image'] = str(process_image(pet['pid']))
            passed = Path(report['pet_image']).resolve() == (ROOT / 'dist/GrangerPet.exe').resolve()
    elif stage == 'closed':
        passed = not launcher and bool(pet) and pet['pid'] == report['pet_pid']
    elif stage == 'reopened':
        passed = bool(launcher and pet) and pet['pid'] == report['pet_pid']
    elif stage == 'exited':
        passed = not launcher and not pet
        settings = SettingsStore().load()
        report['saved_ai_retained_after_launcher'] = settings.ai_provider == 'deepseek' and settings.deepseek_model == 'deepseek-v4-flash' and bool(CredentialsStore().get('deepseek_api_key'))
        passed = passed and report['saved_ai_retained_after_launcher']
    else:
        raise ValueError(stage)
    report['checks'].append({'name': stage, 'passed': bool(passed)})
    report['passed'] = all(item['passed'] for item in report['checks'])
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(stage, 'passed' if passed else 'FAILED')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
