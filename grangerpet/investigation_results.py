"""One normalized investigation projection for summary, graph and evidence."""
from __future__ import annotations
from copy import deepcopy
from collections import Counter
import hashlib
import json
import re
from urllib.parse import urlsplit

from .entity_router import route, route_goal
from .engine.models import canonical_url, result_key
from .context import terms


def _key(target):
    return (target.platform, target.canonical_url if target.entity_type in ('public_post','blockchain_transaction') else target.identifier, target.entity_type)


def relevance(records, goal):
    targets = route_goal(goal)
    seeds = {_key(target) for target in targets}
    root_urls = {target.canonical_url for target in targets if target.canonical_url}
    identifiers = {target.identifier for target in targets}
    image_ids = {target.identifier for target in targets if target.entity_type == 'image'}
    result, linked_urls, linked_targets = {}, {}, {}
    def level(row):
        identifier = row.get('evidence_id')
        details = row.get('details') if isinstance(row.get('details'), dict) else {}
        url = canonical_url(row.get('url', ''))
        target = route(url)
        direct = url in root_urls or target and _key(target) in seeds
        if target and target.platform == 'telegram':
            direct = direct or any(seed.platform == 'telegram' and seed.entity_type!='public_post' and seed.identifier == target.identifier for seed in targets)
        direct = direct or details.get('attachment_id') in image_ids or details.get('target_address') in identifiers
        if details.get('chain') == 'ton':
            from .validators.ton_address import parse_ton_address
            for field in ('target_address','address','from_address','to_address'):
                parsed = parse_ton_address(details.get(field))
                if parsed and parsed['raw'] in identifiers: direct = True
        if details.get('email') in identifiers or details.get('domain') in identifiers: direct = True
        if direct:
            return {'level':'direct','score':100,'reason':'Точный исходный идентификатор, URL или выбранное вложение.','via_evidence_ids':[]}
        if url in linked_urls or target and _key(target) in linked_targets:
            via = linked_urls.get(url) or linked_targets.get(_key(target)) or []
            return {'level':'linked','score':85,'reason':'Ссылка действительно опубликована в относящемся к цели источнике. Это не общность владельца.','via_evidence_ids':list(via)[:20]}
        return None
    # Bounded link closure; propagation is through observed anchors, never name similarity.
    for _ in range(4):
        changed = False
        for row in records:
            if not isinstance(row, dict) or not row.get('evidence_id'): continue
            identifier = row['evidence_id']
            matched = level(row)
            if not matched: continue
            if identifier not in result:
                result[identifier] = matched
                changed = True
            details = row.get('details') if isinstance(row.get('details'), dict) else {}
            links = details.get('links') if isinstance(details.get('links'), list) else []
            for link in links[:100]:
                if not isinstance(link, dict): continue
                url = canonical_url(link.get('url', ''))
                if not url or urlsplit(url).hostname in ('telegram.org','desktop.telegram.org','apps.apple.com','play.google.com'): continue
                linked_urls.setdefault(url, set()).add(identifier)
                target = route(url)
                if target: linked_targets.setdefault(_key(target), set()).add(identifier)
        if not changed: break
    exact_tokens = [value for value in identifiers if isinstance(value, str) and 3 <= len(value) <= 100]
    goal_terms = terms(goal)
    for row in records:
        if not isinstance(row, dict) or not row.get('evidence_id'): continue
        identifier = row['evidence_id']
        if identifier in result: continue
        text = str(row.get('title', '')) + ' ' + str(row.get('description', '')) + ' ' + str(row.get('url', ''))
        exact = any(re.search(r'(?<![\w])' + re.escape(token) + r'(?![\w])', text, re.I) for token in exact_tokens)
        contextual = len(terms(text) & goal_terms) >= 2
        result[identifier] = {'level':'potential' if exact or contextual or not targets else 'background',
            'score':45 if exact else 25 if contextual or not targets else 0,
            'reason':'Есть совпадение текста/идентификатора; прямая связь с целью ещё не подтверждена.' if exact or contextual or not targets else
                     'Нет точного идентификатора или доказанной цепочки ссылок к исходной цели.', 'via_evidence_ids':[]}
    return result


def readable_finding(row):
    details = row.get('details') if isinstance(row.get('details'), dict) else {}
    title, description = str(row.get('title') or row.get('platform') or 'Наблюдение'), str(row.get('description') or '')
    predictions = details.get('predictions')
    if isinstance(predictions, list) and predictions:
        coordinates = [f"{p['latitude']:.5f}, {p['longitude']:.5f}" for p in predictions[:3]
            if isinstance(p, dict) and type(p.get('latitude')) in (int,float) and type(p.get('longitude')) in (int,float)]
        title = 'Географические кандидаты · ' + str(details.get('tool') or row.get('platform'))
        description = '; '.join(coordinates) + '. Гипотезы модели; score не является вероятностью.'
    elif details.get('date_utc'):
        title, description = 'Время из идентификатора TikTok', str(details['date_utc']) + ' — кодируемое время, публикация независимо не проверена.'
    elif row.get('type') == 'repository':
        title = str(details.get('full_name') or title)
        description = str(details.get('description') or description)
    elif row.get('type') == 'transaction':
        title = 'Транзакция · ' + str(details.get('chain') or row.get('platform'))
        description = (str(details.get('from_address') or 'отправитель не указан') + ' → ' +
            str(details.get('to_address') or 'получатель не указан') + '; ' +
            str(details.get('amount_decimal', details.get('amount', 'сумма неизвестна'))) + ' ' + str(details.get('asset') or ''))
    elif details.get('capability') == 'mail_dns':
        title = 'DNS домена · ' + str(details.get('domain') or '')
        description = 'Публичные MX/SPF/DMARC домена. Существование конкретного почтового ящика не подтверждено.'
    return {'title':title[:300], 'description':description[:1000]}


def project(snapshot, goal=None, *, cancel_event=None):
    from .evidence_graph import build
    records = [row for row in snapshot.get('evidence', []) if isinstance(row, dict) and row.get('evidence_id')
               and row.get('type') != 'evidence_graph']
    goal = goal if isinstance(goal, str) else str(snapshot.get('goal') or '')
    ranking = relevance(records, goal)
    groups = {}
    for row in records:
        if cancel_event and cancel_event.is_set(): raise InterruptedError('Investigation projection cancelled')
        key = str(row.get('resource_id') or hashlib.sha256(repr(result_key(row)).encode()).hexdigest())
        group = groups.setdefault(key, [])
        group.append(row)
    evidence = []
    for key, rows in groups.items():
        def quality(row):
            details = row.get('details') if isinstance(row.get('details'), dict) else {}
            return 3 if details.get('reading_method') in ('direct_http','browser_dom') else 2 if details.get('acquisition') == 'official_api' else 1
        best = max(rows, key=quality)
        rank = max((ranking[row['evidence_id']] for row in rows), key=lambda value:value['score'])
        evidence.append({**deepcopy(best), **readable_finding(best), 'related_evidence_ids':[row['evidence_id'] for row in rows],
            'duplicate_count':len(rows)-1, 'relevance':rank})
    graph = build(records, limit=5000, full=True, goal=goal, cancel_event=cancel_event)
    for node in graph['entities']:
        ranks = [ranking[eid] for eid in node['evidence_ids'] if eid in ranking]
        rank = max(ranks, key=lambda value:value['score']) if ranks else {'level':'direct' if node['attributes'].get('is_root') else 'background','score':100 if node['attributes'].get('is_root') else 0,'reason':'Исходная область исследования.'}
        node['relevance'] = rank
    calls = snapshot.get('tool_calls')
    executions = [row for row in snapshot.get('executions', []) if isinstance(row, dict)]
    failures = [row for row in executions if row.get('status') not in ('complete','completed','empty','partial','duplicate_skipped')]
    source_urls = {canonical_url(row.get('url','')) for row in records if row.get('url')}
    source_urls.discard('')
    findings = [row for row in evidence if row['relevance']['level'] in ('direct','linked') and row.get('status') != 'hypothesis']
    hypotheses = [row for row in evidence if row.get('status') == 'hypothesis' or row['relevance']['level'] == 'potential']
    background = [row for row in evidence if row['relevance']['level'] == 'background']
    return {**graph, 'investigation_id':snapshot.get('id'), 'goal':goal, 'status':snapshot.get('status','stopped'),
        'revision':snapshot.get('checkpoint_revision') or str(len(records)) + ':' + str(len(executions)),
        'summary':{'findings':findings[:30],'hypotheses':hypotheses[:30], 'background_count':len(background),
            'limitations':list(dict.fromkeys(str(note) for row in failures[-12:] for note in row.get('limitations',[]) if isinstance(note,str)))[:12],
            'failed_sources':[{'tool':row.get('tool'),'status':row.get('status'),'error':row.get('error')} for row in failures[-12:]],
            'stop_reason':snapshot.get('stop_reason'), 'report':snapshot.get('final_report','')},
        'counts':{'tool_calls':calls if type(calls) is int else None,'raw_records':len(records),'unique_evidence':len(evidence),
            'unique_documents':len(source_urls),'errors':len(failures),'cached_results':sum(row.get('status')=='duplicate_skipped' for row in executions),
            'findings':len(findings),'hypotheses':len(hypotheses),'background':len(background),
            'verified_relations':sum(row['verification_status']=='verified' for row in graph['relations'])},
        'evidence':evidence, 'relevance':ranking, 'synthetic':snapshot.get('synthetic') is True}
