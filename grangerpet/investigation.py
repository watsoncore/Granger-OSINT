"""Durable investigation evidence without a small rolling execution window."""
from __future__ import annotations

from copy import deepcopy
import math

from .agent_evidence import EvidenceStore, EvidenceContractError, validate_saved_evidence, redact


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
        """Restore intact rows and diagnose isolated damage without inventing facts.

        This is an in-memory projection. Original journals/checkpoints are never
        rewritten here, so a rejected legacy row remains available for recovery.
        """
        restored = {}
        if not isinstance(records, list):
            self._diagnose(EvidenceContractError('evidence', records))
            records = []
        for value in records:
            try:
                normalized = validate_saved_evidence(value)
            except EvidenceContractError as error:
                self._diagnose(error)
                continue
            except (TypeError, ValueError, KeyError):
                self._diagnose(EvidenceContractError('evidence[]', value))
                continue
            restored[normalized['evidence_id']] = normalized
        if not isinstance(executions, list):
            self._diagnose(EvidenceContractError('executions', executions))
            executions = []
        safe_executions = []
        for row in executions:
            if not isinstance(row, dict):
                self._diagnose(EvidenceContractError('executions[]', row))
                continue
            safe_executions.append(redact(row))
        with self._lock:
            self._records.update(restored)
            self._all_executions = safe_executions
        return self.diagnostics()
