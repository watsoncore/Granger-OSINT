"""Semantic progress and factual stop reports for the existing AgentRunner."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import re
import unicodedata

from .engine.models import canonical_url


_TELEMETRY = frozenset(('query', 'original_query', 'retrieved_at', 'obtained_at',
    'duration_ms', 'elapsed_ms', 'elapsed_seconds', 'timings', 'performance',
    'execution_id', 'evidence_id', 'resource_id', 'request_id', 'reading_method',
    'acquisition', 'agent_tool', 'source_confirmations', 'preview', 'base64',
    'content_excerpt', 'content_length', 'content_total_chars', 'observations'))


def normalized_arguments(name, arguments):
    """Conservative normalization: never case-fold a wallet or a URL path."""
    def normalize(value, key=''):
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if not isinstance(value, str):
            return value
        value = unicodedata.normalize('NFC', value.strip())
        if key in ('url', 'canonical_url', 'source_url'):
            return canonical_url(value) or value
        if key == 'domain':
            return value.rstrip('.').lower()
        if key == 'email' and '@' in value:
            local, domain = value.rsplit('@', 1)
            return local + '@' + domain.lower()
        if key == 'username' and name in ('github_profile', 'x_profile', 'telegram_public', 'vk_public', 'instagram_public'):
            return value.lstrip('@').lower()
        return value
    return normalize(arguments)


def semantic_facts(records):
    """A second HTTP200 or query spelling is not independent corroboration."""
    def content(value, depth=0):
        if depth > 12:
            return None
        if isinstance(value, dict):
            return {key: content(item, depth + 1) for key, item in value.items()
                    if key not in _TELEMETRY and not key.endswith('_duration_ms')}
        if isinstance(value, list):
            return [content(item, depth + 1) for item in value[:150]]
        return value
    facts = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        details = row.get('details') or {}
        if not isinstance(details, dict) or details.get('capability') == 'evidence_graph':
            continue
        observation = row
        if row.get('observations'):
            observation = {**row, **row['observations'][-1]}
        resource = canonical_url(row.get('url', '')) or (str(row.get('platform', '')) + '|' + str(row.get('id', '')))
        value = {'resource': resource, 'type': row.get('type'),
            'status': observation.get('status'), 'verification': row.get('verification'),
            'description': observation.get('description', ''), 'details': content(observation.get('details', {}))}
        facts.add(hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    return facts


def stop_report(snapshot, reason, introduction=''):
    """Useful even when the provider is down; every finding cites saved data."""
    records = [row for row in snapshot.get('evidence', []) if isinstance(row, dict)
               and (row.get('details') or {}).get('capability') != 'evidence_graph']
    goal = str(snapshot.get('goal') or 'Проверка публичных сведений')[:1400]
    reasons = {'no_progress': 'Дальнейшие проверки не добавляют новых сведений.',
        'cancelled': 'Работа остановлена пользователем.', 'manual_pause': 'Автоматическое продолжение отключено.',
        'step_limit': 'Достигнут выбранный бюджет шагов.', 'tool_limit': 'Достигнут выбранный бюджет инструментов.',
        'token_limit': 'Достигнут выбранный бюджет токенов.', 'time_limit': 'Достигнут выбранный бюджет времени.',
        'page_limit': 'Достигнут выбранный бюджет страниц.', 'api_error': 'Провайдер прервал анализ.',
        'data_contract_error': 'Получены данные неверного формата; ошибочная операция остановлена.',
        'checkpoint_error': 'Сохранение продолжения недоступно; пригодные сведения остаются в текущем сеансе.',
        'context_limit': 'Достигнут безопасный размер рабочего контекста.', 'interrupted': 'Предыдущее выполнение было прервано.'}
    reasons['download_limit'] = 'Достигнут бюджет полученных данных встроенных HTTP-источников.'
    lines = [f'**Цель:** {goal}', '', reasons.get(reason, introduction or 'Поиск завершён с ограничениями.'), '', '**Сведения источников**']
    if not records:
        lines.append('Пригодных доказательств не получено. Это не доказывает отсутствие объекта или сведений в интернете.')
    else:
        for row in records[:12]:
            title = str(row.get('title') or row.get('platform') or 'Наблюдение')[:220]
            description = re.sub(r'\s+', ' ', str(row.get('description') or '')).strip()[:380]
            label = 'Гипотеза; требует проверки. ' if row.get('status') in ('hypothesis', 'unconfirmed', 'unknown') else ''
            source = f"[источник]({row['url']})" if row.get('url') else str((row.get('provenance') or {}).get('tool') or row.get('platform') or '')
            lines.append(f'- {title}: {label}{description} ({source}; {row.get("evidence_id", "")}).')
        if len(records) > 12:
            lines.append(f'Ещё {len(records) - 12} записей сохранены в доказательствах расследования.')
    lines += ['', '**Ограничения и непроверенные направления**']
    failures = Counter((str(row.get('tool') or 'источник'), str(row.get('status') or 'unknown'))
                       for row in snapshot.get('executions', []) if isinstance(row, dict)
                       and row.get('status') not in ('complete', 'completed', 'success', 'empty', 'duplicate_skipped'))
    for (tool, status), count in list(failures.items())[:8]:
        lines.append(f'- {tool}: {status}; проверок с таким исходом — {count}. Результат не выдан за подтверждённый факт.')
    if not failures:
        lines.append('- Полнота открытых источников и принадлежность найденных объектов одному владельцу не установлены.')
    lines.append('- Продолжение учитывает уже выполненные запросы. Новый вызов требует нового направления или изменившихся аргументов.')
    documents = {canonical_url(row.get('url', '')) for row in records if row.get('url')}
    documents.discard('')
    lines += ['', f"Выполнено вызовов: {snapshot.get('tool_calls', 0)}. Уникальных документов: {len(documents)}. Сохранено доказательств: {len(records)}."]
    return '\n'.join(lines)
