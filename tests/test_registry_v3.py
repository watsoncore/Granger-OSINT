"""V3 integration contracts with deterministic adapters; no network or profile."""
import threading
import time

import pytest

from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings


def finding(index):
    return {"id": "fixture:" + str(index), "type": "profile", "platform": "Example",
        "title": "Профиль " + str(index), "url": "https://example.com/user/" + str(index),
        "details": {"extracted_metadata": {"fullname": "Имя " + str(index)}}, "status": "detected"}


class Maigret:
    id = "maigret"
    def __init__(self, status="complete", cancellation=None):
        self.status, self.cancellation = status, cancellation
        self.calls = []

    def run(self, query, context):
        self.calls.append((query, context))
        rows = [finding(n) for n in range(57)]
        for row in rows[:23]:
            context.event({"event": "result", "result": row})
        coverage = {"mode": "full", "database_total": 8232, "scheduled": 57, "found": 57,
            "checked": 57, "pending": 0, "complete": self.status == "complete"}
        context.event({"event": "maigret_progress", "source": "maigret", "progress": coverage})
        if self.cancellation:
            self.cancellation.set()
        return {"source": "maigret", "status": self.status, "results": rows, "checked": 57,
            "source_diagnostics": {"coverage": coverage,
                "site_checks": [{"site": str(n), "status": "found"} for n in range(57)],
                "resumption": {"native_durable_resume": False, "remaining_sites": []}}}


def registry(adapter):
    return ToolRegistry(Settings(), adapters={adapter.id: adapter},
        secret_getter=lambda name: "", readiness=lambda *args, **kwargs: {"runtime_ready": True})


@pytest.mark.parametrize("status", ["complete", "partial", "cancelled", "timeout"])
def test_maigret_all57_findings_and_coverage_survive_registry_without20_result_cap(status):
    stopped = threading.Event() if status == "cancelled" else None
    adapter = Maigret(status, stopped)
    reg, events = registry(adapter), []
    result = reg.execute("username_maigret", {"username": "solvnox", "mode": "full", "time_budget": 300},
        cancel_event=stopped, on_event=events.append)
    assert result["status"] == status and result["result_count"] == 57
    assert len(result["results"]) == len(result["data"]["results"]) == len(reg.evidence.records()) == 57
    assert len(set(result["evidence_ids"])) == 57
    assert result["results"][-1]["details"]["extracted_metadata"]["fullname"] == "Имя 56"
    diagnostics = result["source_diagnostics"]
    assert diagnostics["coverage"]["found"] == 57 and len(diagnostics["site_checks"]) == 57
    assert diagnostics["resumption"]["native_durable_resume"] is False
    progress = [event for event in events if event["type"] == "progress"]
    assert len(progress) == 1 and progress[0]["progress"]["mode"] == "full"
    query, context = adapter.calls[0]
    assert query.timeout > 90 and context.options["maigret"]["mode"] == "full"


def test_maigret_exception_after_live_evidence_is_partial_and_diagnostic_not_empty_error():
    class FailingMaigret:
        id='maigret'
        def run(self,query,context):
            context.event({'event':'result','result':finding(0)})
            raise RuntimeError('private vendor exception text')
    reg=registry(FailingMaigret());events=[]
    result=reg.execute('username_maigret',{'username':'solvnox','mode':'full'},on_event=events.append)
    assert result['status']=='partial' and result['result_count']==1
    assert result['error_code']=='tool_execution_failed'
    assert len(reg.evidence.records())==1 and any(event['type']=='evidence' for event in events)
    assert 'private vendor exception' not in str(result)


def test_mode_time_budget_is_honored_and_manifest_does_not_offer_legacy_limit():
    adapter = Maigret()
    reg = registry(adapter)
    schemas = {row["function"]["name"]: row["function"]["parameters"] for row in reg.schemas()}
    properties = schemas["username_maigret"]["properties"]
    assert properties["mode"]["enum"] == ["quick", "standard", "full", "custom"]
    assert "include_mirrors" in properties and "limit" not in properties
    assert reg.timeout_for("username_maigret", 25, {"username": "solvnox", "mode": "full"}) == 1805
    assert reg.timeout_for("username_maigret", 25, {"username": "solvnox", "mode": "custom", "time_budget": 1200}) == 1205
    result = reg.execute("username_maigret", {"username": "solvnox", "mode": "full", "site_count": 20})
    assert result["status"] == "invalid_arguments" and not adapter.calls


def test_ip_cannot_launch_gansar_adapter_even_with_forced_chain():
    adapter = Maigret()
    adapter.id = "blockchain"
    reg = registry(adapter)
    result = reg.execute("blockchain_gansar", {"address": "66.249.67.41", "chain": "ton", "operation": "profile"})
    assert result["status"] == "invalid_arguments" and not adapter.calls


def test_maigret_2201_findings_keep_full_checks_through_manual_journal_save_load_and_restore(tmp_path,monkeypatch):
    from grangerpet.agent_evidence import safe_maigret_diagnostics,redact
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.investigation import InvestigationEvidence
    from grangerpet.investigation_workspace import InvestigationWorkspace
    from grangerpet.tool_contracts import sanitize_outcome
    from grangerpet.credentials import CredentialsStore
    import json
    monkeypatch.setenv('APPDATA',str(tmp_path/'appdata'))
    secret='PRIVATE-MAIGRET-COVERAGE-SECRET'
    checks=[{'site':f'Site{n:05d}','status':'found','http_status':200,
             'reason':f'Наблюдение {n} '+secret,'api_key':secret} for n in range(2201)]
    remaining=[f'Remaining{n:05d}' for n in range(201)]
    diagnostics={'coverage':{'mode':'full','database_total':8232,'scheduled':2402,'checked':2201,
                            'found':2201,'pending':201,'complete':False},
        'site_checks':checks,'resumption':{'native_durable_resume':False,'remaining_sites':remaining},
        'api_key':secret,'source_root':'C:/private/runtime'}
    class BulkMaigret:
        id='maigret'
        def run(self,query,context):
            return {'source':'maigret','status':'partial','results':[finding(n) for n in range(2201)],
                    'source_diagnostics':diagnostics,'checked':2201}
    reg=registry(BulkMaigret());reg._redactions.add(secret)
    arguments={'username':'solvnox','mode':'full','time_budget':300}
    outcome=reg.execute('username_maigret',arguments)
    assert outcome['status']=='partial' and outcome['result_count']==2201
    assert len(outcome['source_diagnostics']['site_checks'])==2201
    assert outcome['source_diagnostics']['resumption']['remaining_sites']==remaining
    safe=sanitize_outcome(outcome,(secret,))
    assert len(safe['results'])==len(safe['data']['results'])==len(safe['evidence_ids'])==2201
    assert len(safe['source_diagnostics']['site_checks'])==2201
    workspace=InvestigationWorkspace(InvestigationJournal(tmp_path/'investigations'))
    snapshot=workspace.manual_result('solvnox',outcome,arguments,reg,'f'*32)
    assert len(snapshot['evidence'])==2201
    assert len(snapshot['executions'])==1
    checkpoint=workspace.journal.load_checkpoint(snapshot['id'])
    public=workspace.journal.load(snapshot['id'])
    reopened=InvestigationWorkspace(InvestigationJournal(tmp_path/'investigations')).load(snapshot['id'])
    for value in (snapshot,checkpoint,public,reopened):
        assert len(value['evidence'])==2201
        assert len(value['executions'][0]['source_diagnostics']['site_checks'])==2201
        assert value['executions'][0]['source_diagnostics']['resumption']['remaining_sites']==remaining
        assert value['executions'][0]['source_diagnostics']['coverage']['found']==2201
        assert secret not in json.dumps(value,ensure_ascii=False)
    cached=next(iter(checkpoint['call_cache'].values()))['outcome']
    assert len(cached['results'])==len(cached['source_diagnostics']['site_checks'])==2201
    assert secret not in json.dumps(checkpoint,ensure_ascii=False)
    path=tmp_path/'investigations'/(snapshot['id']+'.checkpoint.dpapi')
    assert b'Site02200' not in path.read_bytes()
    decoded=CredentialsStore._protect(path.read_bytes(),decrypt=True)
    assert b'Site02200' in decoded and secret.encode() not in decoded
    restored=InvestigationEvidence()
    assert restored.restore(checkpoint['evidence'],checkpoint['executions'])==[]
    assert len(restored.records())==2201
    assert len(restored.executions()[0]['source_diagnostics']['site_checks'])==2201
    # The exception is scoped to the original-engine contract; unrelated source
    # arrays retain existing redaction/input batch limits.
    assert len(redact(diagnostics)['site_checks'])==150
    generic=InvestigationEvidence()
    generic.add({'tool':'username_blackbird','status':'complete','query':'fixture','results':[finding(n) for n in range(2201)]})
    assert len(generic.records())==2000


def test_full_maigret_diagnostic_redaction_rejects_oversize_and_invalid_rows_explicitly():
    from grangerpet.agent_evidence import safe_maigret_diagnostics,EvidenceContractError
    for value in ({'site_checks':[{'site':'x','status':{}}]},
                  {'site_checks':[{'site':'x','status':'found','http_status':True}]},
                  {'site_checks':[{'site':'x','status':'found'}]*10001},
                  {'resumption':{'remaining_sites':['site']*10001}}):
        with pytest.raises(EvidenceContractError):safe_maigret_diagnostics(value)
