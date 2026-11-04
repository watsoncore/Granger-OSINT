"""Bounded, secret-free evidence snapshots, separate from model summaries.

A source detecting a profile proves the source's observation, not an identity.
Only exact resources are deduplicated; a nickname is never a person merge key.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import re
import threading

from .engine.models import Result, canonical_url, is_confirmed, result_key

_SECRET = re.compile(r"(?i)(?:api.?key|authorization|password|passwd|access.?token|refresh.?token|session|cookie|credential|secret|private.?key)")
_INTERNAL = frozenset({"source_root", "tools_root", "runtime_python", "local_path", "cwd", "working_directory", "stderr", "stdout", "traceback", "command", "options"})
_LOG = logging.getLogger(__name__)


class EvidenceContractError(ValueError):
    """A structural failure whose diagnostic never contains source contents."""
    code = 'invalid_evidence_contract'

    def __init__(self, path, value):
        self.path, self.actual_type = path, type(value).__name__
        super().__init__(f'{self.code}: {path} ({self.actual_type})')

    def diagnostic(self):
        return {'code': self.code, 'path': self.path, 'actual_type': self.actual_type}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def current_observation(record):
    """Presentation of the latest observation, retaining the original ledger."""
    observations=record.get('observations')
    if not isinstance(observations,list) or not observations or not isinstance(observations[-1],dict):return record
    return {**record,**{key:value for key,value in observations[-1].items() if key in ('status','description','details','provenance')}}


def redact_text(value, secrets=()):
    """Redact a report without applying the evidence-field excerpt limit."""
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 4:
            value = value.replace(secret, "[скрыто]")
    value = re.sub(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/_=.-]+", "[скрытая авторизация]", value)
    value = re.sub(r"AIza[A-Za-z0-9_-]{25,}", "[скрытый ключ]", value)
    value = re.sub(r"(?i)\b(?:api[_ -]?key|password|access[_ -]?token|session|cookie)\s*[:=]\s*[^\s,;]+", "[скрыто]", value)
    return re.sub(r"(?i)\b[A-Z]:[\\/][^\s\"<>|]+", "[локальный путь]", value)


def redact(value, secrets=(), *, _depth=0, _budget=None):
    """Keep public JSON data, remove credential fields and exact secret values."""
    if _budget is None:
        _budget = [6000]
    _budget[0] -= 1
    if _depth > 12 or _budget[0] < 0:
        # A size guard is not a data conversion. In particular, changing late
        # provenance/details objects into a string broke their public contract
        # and crashed the Qt snapshot on perfectly valid large adapter results.
        if isinstance(value, dict):
            return {}
        if isinstance(value, (list, tuple)):
            return []
        return "[ограничено]" if isinstance(value, str) else None
    if isinstance(value, dict):
        return {str(key)[:160]: redact(item, secrets, _depth=_depth + 1, _budget=_budget)
                for key, item in list(value.items())[:150] if not _SECRET.search(str(key)) and str(key).casefold() not in _INTERNAL}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets, _depth=_depth + 1, _budget=_budget) for item in value[:150]]
    if isinstance(value, str):
        return redact_text(value, secrets)[:16000]
    if type(value) is float and not math.isfinite(value):
        return None
    if value is None or type(value) in (bool, int, float):
        return value
    return None


MAIGRET_DATABASE_ROW_LIMIT = 10_000


def safe_maigret_diagnostics(value, secrets=()):
    """Redact each original-engine check independently, without a 150-row cut.

    The 10,000-row structural guard covers the actual local 8,232-entry database.
    It rejects an oversized contract explicitly; it never silently slices it.
    Other sources keep their existing redaction budgets.
    """
    if not isinstance(value,dict):
        raise EvidenceContractError('maigret.source_diagnostics',value)
    safe=redact({k:v for k,v in value.items() if k not in ('site_checks','resumption')},secrets)
    if 'site_checks' in value:
        checks=value['site_checks']
        if not isinstance(checks,list) or len(checks)>MAIGRET_DATABASE_ROW_LIMIT:
            raise EvidenceContractError('maigret.site_checks',checks)
        safe['site_checks']=[]
        states={'found','not_found','unknown','blocked','unavailable','errors','skipped'}
        for row in checks:
            if (not isinstance(row,dict) or not isinstance(row.get('site'),str) or
                    not 1<=len(row['site'])<=160 or any(ord(c)<32 for c in row['site']) or
                    not isinstance(row.get('status'),str) or row['status'] not in states):
                raise EvidenceContractError('maigret.site_checks[]',row)
            if 'reason' in row and (not isinstance(row['reason'],str) or len(row['reason'])>1000):
                raise EvidenceContractError('maigret.site_checks[].reason',row.get('reason'))
            if 'http_status' in row and not (row['http_status'] in (None,'') or
                    type(row['http_status']) is int and 0<=row['http_status']<=599):
                raise EvidenceContractError('maigret.site_checks[].http_status',row['http_status'])
            safe['site_checks'].append(redact({k:row[k] for k in ('site','status','http_status','reason') if k in row},secrets))
    if 'resumption' in value:
        resume=value['resumption']
        if not isinstance(resume,dict):raise EvidenceContractError('maigret.resumption',resume)
        clean=redact({k:v for k,v in resume.items() if k!='remaining_sites'},secrets)
        if 'remaining_sites' in resume:
            sites=resume['remaining_sites']
            if (not isinstance(sites,list) or len(sites)>MAIGRET_DATABASE_ROW_LIMIT or
                    any(not isinstance(name,str) or not 1<=len(name)<=160 or any(ord(c)<32 for c in name) for name in sites)):
                raise EvidenceContractError('maigret.resumption.remaining_sites',sites)
            clean['remaining_sites']=[redact(name,secrets) for name in sites]
        safe['resumption']=clean
    return safe


def sanitize_execution(value,secrets=()):
    """Keep complete Maigret coverage in durable executions, still secret-free."""
    if not isinstance(value,dict):raise EvidenceContractError('execution',value)
    if value.get('tool')!='username_maigret' or 'source_diagnostics' not in value:
        return redact(value,secrets)
    safe=redact({k:v for k,v in value.items() if k!='source_diagnostics'},secrets)
    safe['source_diagnostics']=safe_maigret_diagnostics(value['source_diagnostics'],secrets)
    return safe


def sanitize_evidence(value, secrets=()):
    """Bound a fact's payload without spending its identity/provenance budget.

    This is redaction, not verification: callers accepting saved facts still
    require validate_saved_evidence. Each contract container has its own budget
    so a large parser result cannot erase a sibling evidence ID or its origin.
    """
    value = value.to_dict() if isinstance(value, Result) else value
    if not isinstance(value, dict):
        raise EvidenceContractError('record', value)
    for name, expected in (('details', dict), ('sources', list), ('provenance', dict), ('observations', list)):
        if name in value and not isinstance(value[name], expected):
            raise EvidenceContractError('record.' + name, value[name])
    safe = redact({name: value[name] for name in
                   ('id', 'title', 'type', 'platform', 'url', 'description', 'date', 'status', 'sources',
                    'evidence_id', 'resource_id', 'verification') if name in value}, secrets)
    for name in ('details', 'provenance'):
        if name in value:
            safe[name] = redact(value[name], secrets)
    if 'observations' in value:
        safe['observations'] = []
        for observation in value['observations'][-8:]:
            if not isinstance(observation, dict):
                raise EvidenceContractError('record.observations[]', observation)
            # Observations are shallow snapshots, never another observation
            # ledger. Discard unknown fields rather than accepting recursion.
            safe['observations'].append(sanitize_evidence({key: observation[key] for key in
                ('status', 'description', 'details', 'provenance') if key in observation}, secrets))
    return safe


def normalize_evidence(value, tool, query, obtained_at=None, secrets=()):
    """Validate a real adapter finding before adding provenance or model access."""
    value = value.to_dict() if isinstance(value, Result) else value
    if not isinstance(value, dict):
        raise EvidenceContractError('record', value)
    for name, expected in (('details', dict), ('sources', list), ('provenance', dict)):
        if name in value and not isinstance(value[name], expected):
            raise EvidenceContractError('record.' + name, value[name])
    if not isinstance(tool, str) or not tool or not isinstance(query, str):
        raise EvidenceContractError('record.provenance.tool_or_query', None)
    if obtained_at is not None and not isinstance(obtained_at, str):
        raise EvidenceContractError('record.provenance.obtained_at', obtained_at)
    # Adapter details have their own bounded tree. They must not consume the
    # budget of sibling identity/status fields or of newly added provenance.
    safe = sanitize_evidence(value, secrets)
    result = Result.from_dict(safe, tool)
    record = result.to_dict()
    when = obtained_at or utc_now()
    resource = json.dumps(result_key(result), ensure_ascii=False, separators=(",", ":"))
    identifier = hashlib.sha256((tool + "\0" + str(query) + "\0" + resource).encode("utf-8")).hexdigest()[:20]
    record["evidence_id"] = "ev_" + identifier
    record["resource_id"] = "res_" + hashlib.sha256(resource.encode("utf-8")).hexdigest()[:20]
    record["verification"] = "source_reported" if is_confirmed(result) else "unconfirmed"
    basis = result.details.get('verification')
    basis = basis if isinstance(basis, str) else result.description
    record["provenance"] = {"tool": tool, "query": redact(str(query), secrets), "obtained_at": when,
                            "source_url": canonical_url(record.get("url", "")), "source_status": result.status,
                            "basis": redact(basis, secrets)[:2000],
                            "identity_verified": False}
    record['provenance']['acquisition'] = ('direct_page' if result.details.get('reading_method') in ('direct_http','browser_dom') else
                                           'official_api' if result.details.get('acquisition')=='official_api' else
                                           'search_index' if tool == 'web_search' else 'source_adapter')
    if isinstance(record.get('details',{}).get('scrape_result'),dict):
        record['details']['scrape_result']['evidence_id']=record['evidence_id']
    return record


def validate_saved_evidence(value):
    """Rebuild a persisted fact only from intact provenance and a matching ID.

    Broken legacy rows remain in their original encrypted journal. They cannot
    become facts by guessing an origin or interpreting a truncation marker.
    """
    if not isinstance(value, dict):
        raise EvidenceContractError('record', value)
    origin = value.get('provenance')
    if not isinstance(origin, dict):
        raise EvidenceContractError('record.provenance', origin)
    for field in ('tool', 'query'):
        if not isinstance(origin.get(field), str) or (field == 'tool' and not origin[field]):
            raise EvidenceContractError('record.provenance.' + field, origin.get(field))
    normalized = normalize_evidence(value, origin['tool'], origin['query'], origin.get('obtained_at'))
    if normalized['evidence_id'] != value.get('evidence_id'):
        raise EvidenceContractError('record.evidence_id', value.get('evidence_id'))
    if value.get('verification') in ('source_reported', 'unconfirmed', 'contradictory'):
        normalized['verification'] = value['verification']
    if 'observations' in value:
        observations = value['observations']
        if not isinstance(observations, list):
            raise EvidenceContractError('record.observations', observations)
        for observation in observations:
            if not isinstance(observation, dict):
                raise EvidenceContractError('record.observations[]', observation)
            for field in ('details', 'provenance'):
                if not isinstance(observation.get(field), dict):
                    raise EvidenceContractError('record.observations[].' + field, observation.get(field))
        normalized['observations'] = sanitize_evidence({'observations': observations})['observations']
    return normalized


class EvidenceStore:
    """Thread-safe snapshots. Compact views refer back to these complete records."""
    def __init__(self, *, max_records=300):
        self.max_records = max(1, min(1000, int(max_records)))
        self._records, self._executions = {}, []
        self._diagnostics = []
        self._lock = threading.RLock()

    def _diagnose(self, error):
        diagnostic = error.diagnostic()
        with self._lock:
            if diagnostic not in self._diagnostics:
                self._diagnostics.append(diagnostic)
                del self._diagnostics[:-100]
                _LOG.warning('Evidence contract rejected: code=%s path=%s actual_type=%s',
                             diagnostic['code'], diagnostic['path'], diagnostic['actual_type'])
        return diagnostic

    def diagnostics(self):
        with self._lock:
            return deepcopy(self._diagnostics)

    def add(self, envelope):
        identifiers = []
        if not isinstance(envelope, dict):
            self._diagnose(EvidenceContractError('envelope', envelope))
            return identifiers
        values = envelope.get('results', [])
        if not isinstance(values, list):
            self._diagnose(EvidenceContractError('envelope.results', values))
            return identifiers
        with self._lock:
            if envelope.get('stream_event') is not True:
                self._executions.append({name: deepcopy(envelope.get(name)) for name in
                                         ("tool", "status", "query", "obtained_at", "limitations", "error") if name in envelope})
            self._executions = self._executions[-100:]
            for value in values[:2000]:
                if not isinstance(value, dict):
                    self._diagnose(EvidenceContractError('envelope.results[]', value))
                    continue
                try:
                    saved = self._records.get(value.get('evidence_id'))
                    if envelope.get('from_saved_data') is True and saved is not None and saved == value:
                        identifiers.append(saved['evidence_id'])
                        continue
                    origin = value.get("provenance", {})
                    if isinstance(origin, dict) and value.get("evidence_id") and (origin.get("tool") == envelope.get("tool") or envelope.get("tool") == "evidence_get"):
                        record = normalize_evidence(value, str(origin.get("tool", "unknown")),
                                                    str(origin.get("query", "")), origin.get("obtained_at"))
                        if record["evidence_id"] != value.get("evidence_id"):
                            continue
                    else:
                        record = normalize_evidence(value, str(envelope.get("tool", "unknown")),
                                                    str(envelope.get("query", "")), envelope.get("obtained_at"))
                except EvidenceContractError as error:
                    self._diagnose(error)
                    continue
                except (ValueError, TypeError):
                    self._diagnose(EvidenceContractError('envelope.results[]', value))
                    continue
                identifier = record["evidence_id"]
                existing = self._records.get(identifier)
                if existing:
                    # A later observation never silently erases the earlier proof.
                    observation = {name: deepcopy(record[name]) for name in ("status", "description", "details", "provenance")}
                    previous = {name: deepcopy(existing[name]) for name in ("status", "description", "details", "provenance")}
                    observations = existing.get("observations", [])
                    if (observations[-1] if observations else previous) != observation:
                        if not observations:
                            observations = existing.setdefault("observations", [previous])
                        observations.append(observation)
                        del observations[:-8]
                    if existing["status"] != record["status"]:
                        existing["verification"] = "contradictory"
                elif len(self._records) < self.max_records:
                    self._records[identifier] = record
                else:
                    continue
                identifiers.append(identifier)
        return identifiers

    def records(self):
        with self._lock:
            return deepcopy(list(self._records.values()))

    def executions(self):
        with self._lock:
            return deepcopy(self._executions)

    def get(self, identifier):
        with self._lock:
            return deepcopy(self._records.get(identifier))

    def compact(self, *, max_records=40, max_chars=18000):
        rows, size = [], 0
        with self._lock:
            values = list(self._records.values())
        for value in values[:max(1, min(100, int(max_records)))]:
            row = {key: deepcopy(value.get(key)) for key in
                   ("evidence_id", "resource_id", "title", "type", "platform", "url", "status", "verification", "provenance")}
            row["description"] = str(value.get("description", ""))[:700]
            row["details"] = {key: deepcopy(item) for key, item in list(value.get("details", {}).items())[:12]
                              if len(json.dumps(item, ensure_ascii=False, default=str)) <= 900}
            encoded = json.dumps(row, ensure_ascii=False)
            if size + len(encoded) > max_chars:
                break
            rows.append(row)
            size += len(encoded)
        return {"results": rows, "total_records": len(values), "omitted_records": len(values) - len(rows),
                "note": "Это сведения источников, не установление личности. Полные безопасные записи сохранены по evidence_id."}
