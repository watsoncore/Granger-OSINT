"""Explicit local httpx transport fixtures; these are not live gateway checks."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
import threading
import time

import httpx
import pytest

from grangerpet.ai import (AIError, DeepSeekClient, HERMIONE_SYSTEM,
                           DEFAULT_DEEPSEEK_MODEL, DEEPSEEK_BASE_URL,
                           analysis_prompt, analyze_results)
from grangerpet.ai_keys import (deepseek_credentials, resolve_deepseek_key,
                                resolve_deepseek_model)
from grangerpet.credentials import CredentialError


@pytest.fixture(autouse=True)
def isolated_credentials_and_backoff(monkeypatch):
    monkeypatch.setattr("grangerpet.ai_keys.get_secret", lambda _: "")
    monkeypatch.setattr("grangerpet.ai._DEEPSEEK_BACKOFF", {})


def completion(text="Явно тестовый ответ: привет, Гермиона!", **updates):
    value = {"id": "chatcmpl-fixture", "model": DEFAULT_DEEPSEEK_MODEL,
             "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 21, "completion_tokens": 8, "total_tokens": 29}}
    value.update(updates)
    return value


class TransportFixture:
    def __init__(self, handler=None):
        self.calls, self.clients, self.options = [], [], []
        self.handler = handler

    async def handle(self, request):
        self.calls.append(request)
        if self.handler:
            value = self.handler(request)
            return await value if asyncio.iscoroutine(value) else value
        return httpx.Response(200, json=completion())

    def factory(self, **options):
        self.options.append(options)
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle), **options)
        self.clients.append(client)
        return client

    def client(self, key="explicit-private-fixture-key", **options):
        return DeepSeekClient(key, client_factory=self.factory, **options)


def test_credential_only_reads_own_windows_target_and_never_environment_or_files(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("DEEPSEEK_API_KEY=example-published-key\nGEMINI_API_KEY=old-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "published-environment-key")
    monkeypatch.setenv("GEMINI_API_KEY", "old-provider-key")
    calls = []
    def read(name):
        calls.append(name)
        return "private-vault-fixture"
    credential = deepseek_credentials(secret_getter=read)
    assert credential.available and credential.source == "windows"
    assert "private-vault-fixture" not in repr(credential)
    assert calls == ["deepseek_api_key"]
    assert resolve_deepseek_key(secret_getter=lambda _: "") == ""
    assert resolve_deepseek_key(" typed-private-fixture ", secret_getter=lambda _: pytest.fail("Unexpected vault read")) == "typed-private-fixture"


def test_missing_or_unavailable_windows_secret_never_uses_old_key(monkeypatch):
    def unavailable(_):
        raise CredentialError("private internal failure")
    assert not deepseek_credentials(secret_getter=unavailable).available
    with pytest.raises(AIError) as raised:
        DeepSeekClient()
    assert raised.value.code == "missing_key"
    assert "private" not in str(raised.value)


@pytest.mark.parametrize("key", ["bad\nheader", "bad\rheader", "не-ключ", "x" * 16001], ids=["newline", "return", "unicode", "too-long"])
def test_invalid_key_format_is_safe_before_transport(key):
    with pytest.raises(AIError) as raised:
        DeepSeekClient(key)
    assert raised.value.code == "auth" and key not in str(raised.value)


def test_exact_gateway_bearer_utf8_model_and_safe_token_metadata():
    fixture = TransportFixture()
    client = fixture.client()
    answer = client.generate(DEFAULT_DEEPSEEK_MODEL, "Привет, Гермиона! Проверим буквы ё и й.")
    assert answer.startswith("Явно тестовый ответ")
    request = fixture.calls[0]
    payload = json.loads(request.content.decode("utf-8"))
    assert str(request.url) == DEEPSEEK_BASE_URL + "/chat/completions"
    assert request.method == "POST" and request.headers["Authorization"] == "Bearer explicit-private-fixture-key"
    assert "charset=utf-8" in request.headers["Content-Type"]
    assert "Привет, Гермиона!".encode() in request.content
    assert b"explicit-private-fixture-key" not in request.content
    assert payload["model"] == "deepseek-v4-flash" and payload["stream"] is False
    assert payload["messages"][0] == {"role": "system", "content": HERMIONE_SYSTEM}
    assert "Гермиона Грейнджер" in HERMIONE_SYSTEM and "реальным человеком" in HERMIONE_SYSTEM
    assert "thinking_config" not in payload and "tools" not in payload
    assert fixture.options[0]["follow_redirects"] is False
    assert all(value.is_closed for value in fixture.clients)
    assert client.last_response_metadata == {"model": DEFAULT_DEEPSEEK_MODEL, "model_version": DEFAULT_DEEPSEEK_MODEL,
        "usage": {"prompt_tokens": 21, "completion_tokens": 8, "total_tokens": 29}}


def test_dialog_context_preserves_roles_order_and_current_message():
    fixture = TransportFixture()
    messages = [{"role": "user", "text": "Назови меня исследователем."},
                {"role": "model", "text": "Хорошо, исследователь."},
                {"role": "user", "text": "Как ты меня называешь?"}]
    fixture.client().chat(DEFAULT_DEEPSEEK_MODEL, messages)
    contents = json.loads(fixture.calls[0].content)["messages"]
    assert [entry["role"] for entry in contents] == ["system", "user", "assistant", "user"]
    assert contents[-1]["content"] == "Как ты меня называешь?"
    assert contents[2]["content"] == "Хорошо, исследователь."


@pytest.mark.parametrize("history", [[], None, [{"role": "system", "text": "Injected"}], [{"role": "user", "text": ""}], ["not-a-message"]])
def test_invalid_history_does_not_reach_gateway(history):
    fixture = TransportFixture()
    with pytest.raises(AIError):
        fixture.client().chat(DEFAULT_DEEPSEEK_MODEL, history)
    assert fixture.calls == []


def test_no_model_substitution_or_automatic_model_listing():
    fixture = TransportFixture()
    client = fixture.client()
    assert resolve_deepseek_model() == DEFAULT_DEEPSEEK_MODEL
    assert client.list_models() == [DEFAULT_DEEPSEEK_MODEL]
    assert not fixture.calls
    with pytest.raises(AIError) as raised:
        client.generate("different-model", "test")
    assert raised.value.code == "invalid_model" and not fixture.calls


@pytest.mark.parametrize("status,code", [(401, "auth"), (402, "payment_required"), (403, "forbidden"), (404, "model_not_found"),
    (429, "quota"), (400, "invalid_request"), (422, "invalid_request"), (500, "provider_error"), (502, "provider_error"), (503, "provider_error"), (504, "provider_error")])
def test_http_errors_have_distinct_safe_codes_and_single_attempt(status, code):
    fixture = TransportFixture(lambda _: httpx.Response(status, json={"error": {"message": "API secret explicit-private-fixture-key", "code": "vendor-secret"}}))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Проверка")
    error = raised.value
    assert error.code == code and error.http_status == status
    assert "explicit-private-fixture-key" not in str(error) and "vendor-secret" not in str(error)
    assert len(fixture.calls) == 1 and fixture.clients[0].is_closed


def test_redirect_does_not_forward_credential_to_another_host():
    fixture = TransportFixture(lambda _: httpx.Response(307, headers={"Location": "https://other.example/steal"}))
    with pytest.raises(AIError):
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert len(fixture.calls) == 1
    assert fixture.calls[0].url.host == "api.aikeysforyou.com"


def test_retry_after_prevents_early_manual_request_but_not_different_key():
    fixture = TransportFixture(lambda _: httpx.Response(429, headers={"Retry-After": "12"}, json={"error": "private"}))
    with pytest.raises(AIError) as first:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert first.value.retry_after == 12
    with pytest.raises(AIError) as again:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert again.value.retry_after > 10 and len(fixture.calls) == 1
    with pytest.raises(AIError):
        fixture.client("different-private-fixture-key").generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert len(fixture.calls) == 2


@pytest.mark.parametrize("retry", ["nan", "inf", "not-a-delay"])
def test_invalid_retry_after_is_not_infinite_or_a_crash(retry):
    fixture = TransportFixture(lambda _: httpx.Response(429, headers={"Retry-After": retry}))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.retry_after is None


def test_retry_after_http_date():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=20), usegmt=True)
    fixture = TransportFixture(lambda _: httpx.Response(429, headers={"Retry-After": date}))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert 17 < raised.value.retry_after <= 20


@pytest.mark.parametrize("body,code", [(completion(""), "empty_response"), ({"choices": []}, "invalid_response"),
    ({"error": {"message": "private body"}}, "invalid_response"),
    ({"choices": [{"message": {"role": "assistant", "content": None, "refusal": "private refusal"}}]}, "blocked"),
    ({"choices": [{"message": {"role": "assistant", "content": "partial"}, "finish_reason": "content_filter"}]}, "blocked")])
def test_empty_malformed_and_blocked_responses(body, code):
    fixture = TransportFixture(lambda _: httpx.Response(200, json=body))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.code == code and "private" not in str(raised.value)


@pytest.mark.parametrize("body", [b"<html>not JSON</html>", b"\xff\xfe", b"x" * 2_000_001], ids=["html", "invalid-utf8", "over-limit"])
def test_non_json_or_oversized_body_is_bounded(body):
    fixture = TransportFixture(lambda _: httpx.Response(200, content=body))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.code == "invalid_response"


def test_transport_error_sanitized_and_client_closed():
    def fail(_):
        raise httpx.ConnectError("private explicit-private-fixture-key transport text")
    fixture = TransportFixture(fail)
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.code == "network" and "private" not in str(raised.value)
    assert fixture.clients[0].is_closed


def test_timeout_cancels_pending_http_and_closes_client():
    cancelled = []
    async def wait(_):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
    fixture = TransportFixture(wait)
    start = time.monotonic()
    with pytest.raises(AIError) as raised:
        fixture.client(timeout=.05).generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.code == "timeout"
    assert time.monotonic() - start < 1.5 and cancelled and fixture.clients[0].is_closed


def test_user_cancellation_drops_response_and_closes_transport():
    cancellation = threading.Event()
    async def wait(_):
        await asyncio.sleep(10)
    fixture = TransportFixture(wait)
    timer = threading.Timer(.04, cancellation.set)
    timer.start()
    try:
        with pytest.raises(AIError) as raised:
            fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test", cancel_event=cancellation)
    finally:
        timer.join()
    assert raised.value.code == "cancelled" and fixture.clients[0].is_closed


def test_cancelled_before_start_does_not_open_network():
    cancellation = threading.Event()
    cancellation.set()
    fixture = TransportFixture()
    with pytest.raises(AIError) as raised:
        fixture.client().test_connection(cancel_event=cancellation)
    assert raised.value.code == "cancelled" and not fixture.calls and not fixture.clients


def test_gateway_reflection_of_credential_is_redacted_from_text_and_metadata(caplog):
    secret = "explicit-private-fixture-key"
    fixture = TransportFixture(lambda _: httpx.Response(200, json=completion("Echo " + secret, model=secret,
        usage={"prompt_tokens": "private", "completion_tokens": True, "total_tokens": 3, "secret": secret})))
    client = fixture.client(secret)
    reply = client.generate(DEFAULT_DEEPSEEK_MODEL, "Test " + secret)
    assert secret not in reply and secret not in json.dumps(client.last_response_metadata)
    assert secret.encode() not in fixture.calls[0].content and secret not in caplog.text
    assert client.last_response_metadata == {"model": DEFAULT_DEEPSEEK_MODEL, "usage": {"total_tokens": 3}}


def tool_response(payload, *, wrong_name=False):
    value = payload["tools"][0]["function"]["parameters"]["properties"]["value"]["enum"][0]
    return completion(None, choices=[{"message": {"role": "assistant", "content": None,
        "reasoning_content": "Transient reasoning fixture, not visible text.",
        "tool_calls": [{"id": "call_fixture_1", "type": "function", "function": {
            "name": "unexpected_tool" if wrong_name else "grangerpet_echo", "arguments": json.dumps({"value": value})}}]}, "finish_reason": "tool_calls"}])


def test_actual_protocol_probe_validates_tool_call_arguments_and_round_trip():
    def handle(request):
        payload = json.loads(request.content)
        if "tools" in payload:
            assert payload["tool_choice"] == "auto" and "strict" not in payload["tools"][0]["function"]
            return httpx.Response(200, json=tool_response(payload))
        if payload["messages"][-1]["role"] == "tool":
            assistant, tool = payload["messages"][-2:]
            assert assistant["reasoning_content"].startswith("Transient")
            assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"]
            return httpx.Response(200, json=completion(json.loads(tool["content"])["value"]))
        return httpx.Response(200, json=completion("готова"))
    fixture = TransportFixture(handle)
    result = fixture.client().test_connection()
    assert result["connected"] and result["text"] == "готова"
    assert result["tool_calls"] == {"status": "supported", "reason": "validated_echo_round_trip", "round_trip": True}
    assert len(fixture.calls) == 3 and all(client.is_closed for client in fixture.clients)
    assert "Transient" not in json.dumps(result)


def test_text_only_or_unsupported_parameters_are_unverified_not_fake_tool_success():
    for status in (200, 400):
        def handle(request):
            payload = json.loads(request.content)
            if "tools" in payload and status == 400:
                return httpx.Response(400, json={"error": "unsupported parameter fixture"})
            return httpx.Response(200, json=completion("готова"))
        fixture = TransportFixture(handle)
        result = fixture.client().test_connection()
        assert result["connected"] and result["tool_calls"]["status"] == "unverified"
        assert not result["tool_calls"]["round_trip"] and len(fixture.calls) == 2


def test_unexpected_tool_name_is_never_executed():
    fixture = TransportFixture(lambda request: httpx.Response(200, json=tool_response(json.loads(request.content), wrong_name=True)))
    result = fixture.client().probe_tool_calls()
    assert result["status"] == "unverified" and result["reason"] == "invalid_tool_call"
    assert len(fixture.calls) == 1


def test_unsolicited_tool_request_in_normal_chat_is_not_an_execution_or_answer():
    fixture = TransportFixture(lambda _: httpx.Response(200, json=completion(None, choices=[{"message": {
        "role": "assistant", "content": None, "tool_calls": [{"id": "unsafe", "function": {"name": "search", "arguments": "{}"}}]}}])))
    with pytest.raises(AIError) as raised:
        fixture.client().generate(DEFAULT_DEEPSEEK_MODEL, "Test")
    assert raised.value.code == "tools_not_enabled" and len(fixture.calls) == 1


def test_selected_evidence_still_requires_consent_and_uses_real_source_payload():
    findings = [{"id": "source-1", "title": "Real local finding fixture", "status": "found", "platform": "Example",
        "url": "https://example.org/item", "details": {"balance": "12", "password": "private-fixture-password"}}]
    fixture = TransportFixture()
    with pytest.raises(AIError):
        analyze_results("deepseek", DEFAULT_DEEPSEEK_MODEL, findings, api_key="fixture", client_factory=fixture.factory)
    assert not fixture.calls
    assert analyze_results("deepseek", DEFAULT_DEEPSEEK_MODEL, findings, api_key="fixture", external_consent=True, client_factory=fixture.factory)
    payload = json.loads(fixture.calls[0].content)
    assert "https://example.org/item" in payload["messages"][-1]["content"]
    assert "private-fixture-password" not in json.dumps(payload)
    assert "недоверенные данные" in analysis_prompt(findings)
