"""Bounded real gateway/registry scenarios; no user history or pixel upload."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from grangerpet.ai import DeepSeekClient, AIError
    from grangerpet.ai_keys import resolve_deepseek_key, DEFAULT_DEEPSEEK_MODEL
    from grangerpet.agent import AgentRunner, AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.credentials import CredentialsStore
    from grangerpet.geoint import AttachmentStore
    from grangerpet.visual_models.manager import get_manager
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('readiness', 'telegram', 'ton', 'visual'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Prior paid API evidence retained; choose a new output')
    key = resolve_deepseek_key()
    if not key:
        raise SystemExit('No saved gateway key; real model test not executed')
    store, images = None, []
    if args.scenario == 'visual':
        store = AttachmentStore(args.output.parent / 'synthetic-qa-attachments',
            seal=lambda data: CredentialsStore._protect(data), open_sealed=lambda data: CredentialsStore._protect(data, decrypt=True))
        image = store.import_bytes((ROOT / 'output/integrations19/visual-photos/moscow-no-gps.jpg').read_bytes(), 'public-landmark-no-gps.jpg')
        images = [image['id']]
    goals = {
        'readiness': 'Гермиона, какие GEOINT-инструменты тебе доступны? Укажи фактическую локальную готовность GeoCLIP, Waypoint, EXIF, OCR, ShadowFinder и Panoramax из снимка backend. Это вопрос о готовности: не запускай inference или сетевые проверки и не называй локальную готовность успешным внешним запросом.',
        'telegram': 'Проведи исследование публичного проекта https://t.me/solvnox_project. Прочти публичную страницу и доступное превью, установи, какие ссылки действительно опубликованы. Для обнаруженных ссылок на GitHub проверь метаданные конкретных репозиториев инструментом github_repository. Не ищи одноимённые аккаунты без основания. Краткий итог по-русски: находки, цепочки ссылок и ограничения; общих владельцев не утверждать.',
        'ton': 'Исследуй публичный TON-адрес EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c через blockchain_gansar. Нужны реально полученные транзакции, суммы и направления, контрагенты, метки источников отдельно от владельцев. Затем evidence_graph и краткий итог по-русски. Если источник недоступен, отрази это без фиктивных результатов.',
        'visual': 'Определи вероятное место съёмки выбранного изображения ' + (images[0] if images else '') + '. Используй установленные GeoCLIP и Waypoint через visual_geoint. GPS отсутствует. Затем evidence_graph по фото и кандидатам. Покажи реальные координаты и ограничения моделей; raw_score не вероятность. Не повторяй выполненный pipeline без новых оснований и не угадывай параметры тени.'}
    registry = ToolRegistry(Settings(ai_provider='deepseek', source_root=str(ROOT)), secret_getter=lambda _: '',
        redactions=(key,), image_store=store, attachment_ids=images)
    runner = AgentRunner(DeepSeekClient(key), registry, limits=AgentLimits(max_steps=8, max_tool_calls=12,
        timeout=300, max_tokens=60000, per_request_timeout=60, per_tool_timeout=30))
    report = {'mock': False, 'scenario': args.scenario, 'user_history_read': False,
              'private_source_keys_used': False, 'images_sent_to_model': False, 'events': []}
    started = time.monotonic()
    try:
        result = runner.run(DEFAULT_DEEPSEEK_MODEL, [{'role': 'user', 'text': goals[args.scenario]}],
            cancel_event=threading.Event(), on_event=lambda event: report['events'].append({k: v for k, v in event.items()
                if k in ('type', 'tool', 'count', 'status', 'error_code', 'step')}))
        report.update(result=result, elapsed_seconds=round(time.monotonic() - started, 3))
        tools = {row.get('provenance', {}).get('tool') for row in result.get('evidence', [])}
        if args.scenario == 'readiness':
            passed = all(name in result['text'].lower() for name in ('geoclip', 'waypoint')) and not result['investigation']['tool_calls']
        elif args.scenario == 'telegram':
            discovered = {link['url'] for row in result.get('evidence', []) if row.get('provenance', {}).get('tool') == 'telegram_public'
                          for link in row.get('details', {}).get('links', []) if isinstance(link, dict)
                          and isinstance(link.get('url'), str) and link['url'].startswith('https://github.com/')
                          and len(link['url'].removeprefix('https://github.com/').strip('/').split('/')) == 2}
            checked = {row['url'] for row in result.get('evidence', []) if row.get('provenance', {}).get('tool') == 'github_repository'}
            report.update(discovered_repository_count=len(discovered), checked_repository_count=len(discovered & checked))
            passed = {'telegram_public', 'github_repository'} <= tools and discovered <= checked and result['investigation']['status'] == 'completed'
        elif args.scenario == 'ton':
            passed = any(row.get('type') == 'transaction' for row in result.get('evidence', []))
        else:
            predictions = [row for row in result.get('evidence', []) if row.get('details', {}).get('predictions')]
            passed = len(predictions) >= 2 and all(row.get('status') == 'hypothesis' for row in predictions)
        report['passed'] = bool(passed and result.get('text') and result['investigation']['status'] not in ('running', 'failed', 'error'))
    except AIError as error:
        report.update(passed=False, code=error.code, http_status=error.http_status, partial=runner.snapshot())
    finally:
        if args.scenario == 'visual':
            get_manager().close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, ensure_ascii=False, indent=2)
    if key in raw:
        raise RuntimeError('Secret in QA report; publication cancelled')
    args.output.write_text(raw + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'scenario': args.scenario, 'seconds': report.get('elapsed_seconds'),
        'status': report.get('result', {}).get('investigation', {}).get('status'),
        'calls': report.get('result', {}).get('investigation', {}).get('tool_calls'), 'code': report.get('code')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
