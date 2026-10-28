"""Bounded, secret-free evidence snapshots, separate from model summaries.

A source detecting a profile proves the source's observation, not an identity.
Only exact resources are deduplicated; a nickname is never a person merge key.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import threading

from .engine.models import Result, canonical_url, is_confirmed, result_key

_SECRET = re.compile(r"(?i)(?:api.?key|authorization|password|passwd|access.?token|refresh.?token|session|cookie|credential|secret|private.?key)")
_INTERNAL = frozenset({"source_root", "tools_root", "runtime_python", "local_path", "cwd", "working_directory", "stderr", "stdout", "traceback", "command", "options"})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def redact(value, secrets=(), *, _depth=0, _budget=None):
    """Keep public JSON data, remove credential fields and exact secret values."""
    if _budget is None:
        _budget = [6000]
    _budget[0] -= 1
    if _depth > 8 or _budget[0] < 0:
        return "[ограничено]"
    if isinstance(value, dict):
        return {str(key)[:160]: redact(item, secrets, _depth=_depth + 1, _budget=_budget)
                for key, item in list(value.items())[:150] if not _SECRET.search(str(key)) and str(key).casefold() not in _INTERNAL}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets, _depth=_depth + 1, _budget=_budget) for item in value[:150]]
    if isinstance(value, str):
        for secret in secrets:
            if isinstance(secret, str) and len(secret) >= 4:
                value = value.replace(secret, "[скрыто]")
        value = re.sub(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/_=.-]+", "[скрытая авторизация]", value)
        value = re.sub(r"AIza[A-Za-z0-9_-]{25,}", "[скрытый ключ]", value)
        value = re.sub(r"(?i)\b(?:api[_ -]?key|password|access[_ -]?token|session|cookie)\s*[:=]\s*[^\s,;]+", "[скрыто]", value)
        value = re.sub(r"(?i)\b[A-Z]:[\\/][^\s\"<>|]+", "[локальный путь]", value)
        return value[:16000]
    if type(value) is float and not math.isfinite(value):
        return None
    if value is None or type(value) in (bool, int, float):
        return value
    return None


def normalize_evidence(value, tool, query, obtained_at=None, secrets=()):
    """Validate a real adapter finding before adding provenance or model access."""
    safe = redact(value.to_dict() if isinstance(value, Result) else value, secrets)
    result = Result.from_dict(safe, tool)
    record = result.to_dict()
    when = obtained_at or utc_now()
    resource = json.dumps(result_key(result), ensure_ascii=False, separators=(",", ":"))
    identifier = hashlib.sha256((tool + "\0" + str(query) + "\0" + resource).encode("utf-8")).hexdigest()[:20]
    record["evidence_id"] = "ev_" + identifier
    record["resource_id"] = "res_" + hashlib.sha256(resource.encode("utf-8")).hexdigest()[:20]
    record["verification"] = "source_reported" if is_confirmed(result) else "unconfirmed"
    record["provenance"] = {"tool": tool, "query": redact(str(query), secrets), "obtained_at": when,
                            "source_url": canonical_url(record.get("url", "")), "source_status": result.status,
                            "basis": redact(result.details.get("verification") or result.description, secrets)[:2000],
                            "identity_verified": False}
    return record


class EvidenceStore:
    """Thread-safe snapshots. Compact views refer back to these complete records."""
    def __init__(self, *, max_records=300):
        self.max_records = max(1, min(1000, int(max_records)))
        self._records, self._executions = {}, []
        self._lock = threading.RLock()

    def add(self, envelope):
        identifiers = []
        if not isinstance(envelope, dict):
            return identifiers
        with self._lock:
            self._executions.append({name: deepcopy(envelope.get(name)) for name in
                                     ("tool", "status", "query", "obtained_at", "limitations", "error") if name in envelope})
            self._executions = self._executions[-100:]
            for value in envelope.get("results", [])[:50]:
                if not isinstance(value, dict):
                    continue
                try:
                    origin = value.get("provenance", {})
                    if isinstance(origin, dict) and value.get("evidence_id") and (origin.get("tool") == envelope.get("tool") or envelope.get("tool") == "evidence_get"):
                        record = normalize_evidence(value, str(origin.get("tool", "unknown")),
                                                    str(origin.get("query", "")), origin.get("obtained_at"))
                        if record["evidence_id"] != value.get("evidence_id"):
                            continue
                    else:
                        record = normalize_evidence(value, str(envelope.get("tool", "unknown")),
                                                    str(envelope.get("query", "")), envelope.get("obtained_at"))
                except (ValueError, TypeError):
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
