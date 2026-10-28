from types import SimpleNamespace

import pytest

from grangerpet.engine import platforms
from grangerpet.engine.blockchain import normalize_report


@pytest.mark.parametrize(("text", "platform", "expected"), [
    ("https://t.me/s/example_channel/19", "telegram", "example_channel"),
    ("@example_user", "telegram", "example_user"),
    ("https://www.instagram.com/example.user/?hl=en", "instagram", "example.user"),
    ("https://vk.com/id12345", "vk", "id12345"),
])
def test_public_platform_identifiers(text, platform, expected):
    assert platforms._username(text, platform) == expected


@pytest.mark.parametrize("url", ["https://t.me/+privateinvite", "https://t.me/c/12345/8", "https://other.example/example_user", "https://name:password@t.me/example_user"])
def test_telegram_rejects_private_or_unrelated_links(url):
    with pytest.raises(ValueError):
        platforms._username(url, "telegram")


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "https://192.168.1.1/", "http://localhost/", "http://server.internal/", "https://user:secret@example.org/"])
def test_archive_accepts_only_public_targets(url):
    with pytest.raises(ValueError):
        platforms._public_url(url)


def test_missing_authorization_is_explicit_and_does_not_try_login(monkeypatch):
    def forbidden(*args):
        pytest.fail("No vendor or login may start when required credentials are missing")
    monkeypatch.setattr(platforms, "_load", forbidden)
    query = {"text": "public_example", "limit": 3, "timeout": 5}
    assert platforms.run_adapter("telegram", query, {})["status"] == "auth_required"
    assert platforms.run_adapter("vk", query, {})["status"] == "auth_required"


def test_instagram_reads_profile_metadata_without_downloading_private_posts(monkeypatch):
    profile = SimpleNamespace(username="public_example", userid=12345, full_name="Fixture Profile",
        followers=2, followees=4, mediacount=6, is_private=True, is_verified=False,
        external_url=None, biography="Explicitly mocked profile metadata")
    calls = []
    class Loader:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.context = object()
        def close(self):
            calls.append("closed")
    module = SimpleNamespace(Instaloader=Loader, Profile=SimpleNamespace(from_username=lambda context, username: profile))
    monkeypatch.setattr(platforms, "_load", lambda *args: module)
    outcome = platforms.run_adapter("instagram", {"text": "public_example", "timeout": 5}, {})
    assert outcome["status"] == "complete"
    assert outcome["results"][0]["details"]["private"] is True
    assert outcome["results"][0]["url"] == "https://www.instagram.com/public_example/"
    assert not calls[0]["download_pictures"] and not calls[0]["download_videos"]
    assert calls[-1] == "closed"


def test_blockchain_normalization_keeps_exact_zero_and_qualifies_hypotheses():
    fixture = {"target_address": "fixture-address", "balances": [{"chain": "eth", "asset": "ETH", "amount_decimal": "0", "source": "fixture_rpc"}],
        "transactions": [{"chain": "eth", "tx_hash": "fixture-tx", "amount": 0, "direction": "out", "source": "fixture_rpc"}],
        "tokens": [{"chain": "eth", "contract": "fixture-contract", "symbol": "TEST", "amount": 0, "holding_status": "unknown", "source": "fixture_api"}],
        "labels": [{"chain": "eth", "address": "fixture-address", "label": "Possible service", "confidence": 0.4, "source": "fixture_labels"}],
        "counterparties": [{"chain": "eth", "address": "fixture-other-address", "tx_count": 2}],
        "coverage": {"status": "partial"}, "source_health": [{"source": "fixture_rpc", "status": "partial"}]}
    items = normalize_report(fixture, 5)
    assert len(items) == 5
    assert {item["type"] for item in items} == {"balance", "transaction", "asset", "label", "relationship"}
    assert "0" in next(item for item in items if item["type"] == "balance")["title"]
    token = next(item for item in items if item["type"] == "asset")
    assert "количество: 0" in token["description"]
    assert token["status"] == "check"
    assert next(item for item in items if item["type"] == "label")["status"] == "check"
    assert next(item for item in items if item["type"] == "relationship")["status"] == "check"
    assert items[0]["details"]["coverage"] == {"status": "partial"}


def test_blockchain_empty_report_never_becomes_a_found_address():
    assert normalize_report({"target_address": "syntactically-valid-input", "detected_chains": ["eth"], "sources_used": ["unavailable_source"]}) == []
