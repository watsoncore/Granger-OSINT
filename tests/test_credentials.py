import sys
import uuid

import pytest

from grangerpet.credentials import CredentialsStore, CredentialError


@pytest.mark.skipif(sys.platform != "win32", reason="Uses native Windows credential protection")
def test_windows_vault_and_long_dpapi_session_roundtrip(tmp_path):
    store = CredentialsStore(prefix="GrangerPet/Tests/" + uuid.uuid4().hex, directory=tmp_path)
    try:
        store.set("deepseek_api_key", "test-only-key-not-a-real-api-key")
        assert store.get("deepseek_api_key") == "test-only-key-not-a-real-api-key"
        value = '{"test_cookie":"' + "synthetic-session-" * 300 + '"}'
        store.set("instagram_session", value)
        assert store.get("instagram_session") == value
        raw = b"".join(path.read_bytes() for path in tmp_path.glob("*.dpapi"))
        assert b"synthetic-session-" not in raw
        assert b"test_cookie" not in raw
        store.set("instagram_session", "short-session")
        assert not list(tmp_path.glob("*.dpapi"))
        assert store.get("instagram_session") == "short-session"
        with pytest.raises(CredentialError):
            store.get("unrelated-system-password")
    finally:
        store.delete("deepseek_api_key")
        store.delete("instagram_session")
    assert store.get("deepseek_api_key") == ""
