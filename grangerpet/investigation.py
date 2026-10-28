"""Durable investigation evidence without a small rolling execution window."""
from __future__ import annotations

from copy import deepcopy
import math

from .agent_evidence import EvidenceStore, normalize_evidence, redact


class InvestigationEvidence(EvidenceStore):
    """Keep primary evidence outside the model's bounded working context.

    Individual adapter rows remain validated and bounded by EvidenceStore.
    The optional record budget is explicit; zero means no record-count budget.
    Disk checkpoint size is checked independently by InvestigationJournal.
    """
    def __init__(self, max_records=0):
        super().__init__(max_records=1000)
        self.max_records = max_records if max_records else math.inf
        self._all_executions = []

    def add(self, envelope):
        with self._lock:
            identifiers = super().add(envelope)
            if isinstance(envelope, dict):
                self._all_executions.append({key: deepcopy(envelope[key]) for key in
                    ('tool', 'status', 'query', 'obtained_at', 'limitations', 'error') if key in envelope})
            return identifiers

    def executions(self):
        with self._lock:
            return deepcopy(self._all_executions)

    def restore(self, records, executions):
        """Revalidate provenance before exposing a saved row to tools/models."""
        with self._lock:
            for value in records if isinstance(records, list) else []:
                if not isinstance(value, dict):
                    raise ValueError('Invalid saved evidence')
                origin = value.get('provenance', {})
                try:
                    normalized = normalize_evidence(value, str(origin['tool']), str(origin['query']), origin.get('obtained_at'))
                    if normalized['evidence_id'] != value.get('evidence_id'):
                        raise ValueError()
                except (TypeError, ValueError, KeyError):
                    raise ValueError('Invalid saved evidence provenance') from None
                # Validated saved observations retain their original timestamps
                # and contradictory statuses; do not turn them into new reads.
                safe = redact(value)
                self._records[normalized['evidence_id']] = safe
            self._all_executions = [redact(row) for row in executions if isinstance(row, dict)] if isinstance(executions, list) else []
