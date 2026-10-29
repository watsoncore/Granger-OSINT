"""Real cryptographic and filesystem tests; all values are synthetic fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from grangerpet.portable_vault import (ARTIFACT_MAGIC, KDF, PortableVault,
                                      VAULT_MAGIC, VaultError)
from grangerpet import credentials


PASSWORD = "Синтетическая фраза 2026"
NEW_PASSWORD = "Другая тестовая фраза 2026"


def test_real_argon2_aes_unicode_secrets_and_unique_nonces(tmp_path):
    vault = PortableVault(tmp_path / "secrets.gpx")
    vault.create(PASSWORD)
    original = vault.path.read_bytes()
    vault.set("deepseek_api_key", "NOT-REAL-SECRET русский")
    first = vault.path.read_bytes()
    vault.set("deepseek_api_key", "NOT-REAL-SECRET русский")
    second = vault.path.read_bytes()
    assert len({original, first, second}) == 3
    assert b"NOT-REAL-SECRET" not in second and "русский".encode() not in second
    assert second.startswith(VAULT_MAGIC)
    assert vault.get("deepseek_api_key") == "NOT-REAL-SECRET русский"
    vault.set("deepseek_api_key", "")
    assert vault.get("deepseek_api_key") == ""


def test_lock_wrong_password_restart_and_tamper_detection(tmp_path):
    vault = PortableVault(tmp_path / "secrets.gpx")
    vault.create(PASSWORD, secrets={"fixture": "private fixture"})
    encrypted = vault.seal("Переносимая история".encode())
    assert vault.open(encrypted) == "Переносимая история".encode()
    vault.lock()
    with pytest.raises(VaultError):
        vault.get("fixture")
    with pytest.raises(VaultError):
        vault.open(encrypted)
    restarted = PortableVault(vault.path)
    with pytest.raises(VaultError):
        restarted.unlock("Definitely wrong password")
    assert not restarted.unlocked
    restarted.unlock(PASSWORD)
    assert restarted.get("fixture") == "private fixture"
    corrupted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(VaultError):
        restarted.open(corrupted)
    for position in (0, len(encrypted) // 2, len(encrypted) - 1):
        changed = encrypted[:position] + bytes([encrypted[position] ^ 1]) + encrypted[position+1:]
        with pytest.raises(VaultError):
            restarted.open(changed)


def test_container_integrity_and_bounded_kdf_reject_untrusted_parameters(tmp_path):
    vault = PortableVault(tmp_path / "secrets.gpx")
    vault.create(PASSWORD)
    raw = vault.path.read_bytes()
    envelope = json.loads(raw[len(VAULT_MAGIC):])
    envelope["header"]["kdf"]["memory_kib"] = 2 ** 40
    vault.path.write_bytes(VAULT_MAGIC + json.dumps(envelope).encode())
    with pytest.raises(VaultError, match="параметры"):
        PortableVault(vault.path).unlock(PASSWORD)
    vault.path.write_bytes(raw[:-2] + b"xx")
    with pytest.raises(VaultError):
        PortableVault(vault.path).unlock(PASSWORD)


def test_password_change_preserves_data_key_and_old_ciphertext(tmp_path):
    vault = PortableVault(tmp_path / "secrets.gpx")
    vault.create(PASSWORD, secrets={"fixture": "secret"})
    artifact = vault.seal(b"historical artifact")
    old = vault.path.read_bytes()
    vault.change_password(PASSWORD, NEW_PASSWORD)
    assert vault.path.read_bytes() != old
    restarted = PortableVault(vault.path)
    with pytest.raises(VaultError):
        restarted.unlock(PASSWORD)
    restarted.unlock(NEW_PASSWORD)
    assert restarted.get("fixture") == "secret"
    assert restarted.open(artifact) == b"historical artifact"


def test_interrupted_atomic_write_preserves_previous_container(tmp_path, monkeypatch):
    vault = PortableVault(tmp_path / "secrets.gpx")
    vault.create(PASSWORD, secrets={"fixture": "original"})
    original = vault.path.read_bytes()
    def fail(*args):
        raise OSError("Synthetic filesystem failure")
    monkeypatch.setattr("grangerpet.portable_vault.os.replace", fail)
    with pytest.raises(OSError):
        vault.set("fixture", "replacement")
    assert vault.path.read_bytes() == original
    assert not list(tmp_path.glob(".granger-cipher-*"))
    assert vault.get("fixture") == "original"


def test_concurrent_unlocked_instances_preserve_each_others_changes(tmp_path):
    first = PortableVault(tmp_path / "secrets.gpx")
    first.create(PASSWORD)
    second = PortableVault(first.path)
    second.unlock(PASSWORD)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pair: pair[0].set(pair[1], pair[1]), [(first, "one"), (second, "two")]))
    assert first.get("one") == "one" and first.get("two") == "two"
    assert second.get("one") == "one" and second.get("two") == "two"


def test_format_roundtrip_is_portable_without_any_windows_api(tmp_path, monkeypatch):
    vault = PortableVault(tmp_path / "source" / "secrets.gpx")
    vault.create(PASSWORD, secrets={"fixture": "portable"})
    artifact = vault.seal(b"independent of Windows account")
    target = tmp_path / "other-os" / "secrets.gpx"
    target.parent.mkdir()
    shutil.copyfile(vault.path, target)
    monkeypatch.setattr(credentials.WindowsLegacyStore, "_windows", lambda: pytest.fail("Windows API called"))
    monkeypatch.setattr(credentials.WindowsLegacyStore, "_protect", lambda *a, **k: pytest.fail("DPAPI called"))
    opened = PortableVault(target)
    opened.unlock(PASSWORD)
    assert opened.get("fixture") == "portable"
    assert opened.open(artifact) == b"independent of Windows account"


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    store = credentials.CredentialsStore(prefix="GrangerPet/Tests/PortableFixture", directory=root / "vault", data_root=root)
    monkeypatch.setattr(credentials, "_STORE", store)
    return store


def test_new_profile_facade_has_no_plaintext_or_windows_fallback(store, monkeypatch):
    credentials.create_portable_vault(PASSWORD, migrate=False)
    monkeypatch.setattr(credentials.WindowsLegacyStore, "_windows", lambda: pytest.fail("Legacy API called"))
    monkeypatch.setattr(credentials.WindowsLegacyStore, "_protect", lambda *a, **k: pytest.fail("DPAPI called"))
    credentials.set_secret("deepseek_api_key", "NOT-A-REAL-KEY")
    assert credentials.get_secret("deepseek_api_key") == "NOT-A-REAL-KEY"
    sealed = credentials.seal_bytes(b"fixture")
    assert sealed.startswith(ARTIFACT_MAGIC) and credentials.open_bytes(sealed) == b"fixture"
    credentials.lock_portable_vault()
    with pytest.raises(VaultError):
        credentials.get_secret("deepseek_api_key")
    with pytest.raises(VaultError):
        credentials.set_secret("vk_token", "fixture")
    credentials.unlock_portable_vault(PASSWORD)
    credentials.delete_secret("deepseek_api_key")
    assert credentials.get_secret("deepseek_api_key") == ""
    with pytest.raises(VaultError):
        credentials.get_secret("unrelated-system-password")
    with pytest.raises(VaultError):
        credentials.open_bytes(b"plain legacy fallback prohibited")


@pytest.mark.skipif(sys.platform != "win32", reason="Real legacy DPAPI/WCM migration only on Windows")
def test_real_windows_migration_preserves_originals_and_dynamic_archive_paths(store):
    from grangerpet.chat_archive import ChatArchive
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.conversations import ConversationLibrary
    legacy = credentials.WindowsLegacyStore(prefix=store.prefix, directory=store.directory)
    legacy.set("deepseek_api_key", "SYNTHETIC-MIGRATION-KEY")
    try:
        archive = ChatArchive(store.data_root / "chat-history.dpapi")
        rows = [{"id": "one", "role": "user", "text": "Синтетический личный диалог"}]
        archive.save(rows, rows)
        library = ConversationLibrary(archive)
        library.seal()
        journal = InvestigationJournal(store.data_root / "investigations")
        checkpoint = {"version": 1, "id": "a"*32, "record": {"id": "a"*32, "status": "paused", "resumable": True}}
        journal.save_checkpoint(checkpoint)
        journal.save({"id": "a"*32, "status": "paused", "evidence": [{"title": "Публичный факт"}]})
        attachment = store.data_root / 'attachments' / ('img_' + 'a'*64 + '.gpi')
        attachment.parent.mkdir()
        attachment.write_bytes(credentials.WindowsLegacyStore._protect(b'SYNTHETIC ATTACHMENT BYTES'))
        originals = {p: p.read_bytes() for p in store.data_root.rglob("*") if p.is_file()}
        result = credentials.create_portable_vault(PASSWORD)
        assert result["migration_complete"] and result["migrated_secrets"] == 1
        assert all(p.read_bytes() == old for p, old in originals.items())
        assert archive.path.is_relative_to(store.data_root / "portable-data")
        assert archive.load()["messages"] == rows
        assert library.list()[0]["title"] == rows[0]["text"]
        assert journal.load_checkpoint("a"*32) == checkpoint
        assert journal.load("a"*32)["evidence"][0]["title"] == "Публичный факт"
        assert credentials.get_secret("deepseek_api_key") == "SYNTHETIC-MIGRATION-KEY"
        assert credentials.open_bytes(credentials.protected_path(attachment).read_bytes()) == b'SYNTHETIC ATTACHMENT BYTES'
        archive.save(rows + [{"role": "model", "text": "Новый ответ"}], [])
        assert all(p.read_bytes() == old for p, old in originals.items())
        assert len(archive.load()["messages"]) == 2
    finally:
        legacy.delete("deepseek_api_key")


@pytest.mark.skipif(sys.platform != "win32", reason="Actual failed legacy DPAPI read")
def test_corrupt_legacy_data_never_activates_or_deletes(store):
    store.data_root.mkdir(parents=True)
    path = store.data_root / "chat-history.dpapi"
    path.write_bytes(b"corrupt original fixture")
    with pytest.raises(VaultError):
        credentials.create_portable_vault(PASSWORD)
    assert not store.portable.exists
    assert path.read_bytes() == b"corrupt original fixture"
    assert not (store.data_root / "portable-data").exists()


def test_migration_write_failure_rolls_back_activation(store, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("Synthetic failure")
    monkeypatch.setattr(store.portable, "create", fail)
    with pytest.raises(VaultError):
        credentials.create_portable_vault(PASSWORD, migrate=False)
    assert not store.portable.exists and not (store.data_root / "portable-data").exists()
    assert not list(store.data_root.glob(".portable-stage-*"))


def test_recovery_after_crash_before_activation_keeps_orphan_ciphertext(store):
    orphan = store.data_root / "portable-data"
    orphan.mkdir(parents=True)
    (orphan / "fixture").write_bytes(b"previous interrupted encrypted fixture")
    credentials.create_portable_vault(PASSWORD, migrate=False)
    recovery = list(store.data_root.glob(".portable-recovery-*"))
    assert len(recovery) == 1
    assert (recovery[0] / "fixture").read_bytes() == b"previous interrupted encrypted fixture"
    assert credentials.vault_status()["enabled"]


def test_portable_journal_checkpoint_and_ciphertext_reject_locked_read(store):
    from grangerpet.agent_journal import InvestigationJournal
    credentials.create_portable_vault(PASSWORD, migrate=False)
    journal = InvestigationJournal(store.data_root / "investigations")
    value = {"id": "b"*32, "status": "paused", "evidence": [{"title": "Личный синтетический факт"}]}
    path = journal.save(value)
    assert path.is_relative_to(store.data_root / 'portable-data')
    assert path.read_bytes().startswith(ARTIFACT_MAGIC)
    assert 'Личный'.encode() not in path.read_bytes()
    assert journal.load("b"*32)['evidence'][0]['title'] == 'Личный синтетический факт'
    credentials.lock_portable_vault()
    with pytest.raises(VaultError):
        journal.load("b"*32)
    with pytest.raises(VaultError):
        journal.save(value)


def test_portable_canvas_internal_files_encrypted_but_export_is_explicit_utf8(store):
    from PySide6.QtWidgets import QApplication
    from grangerpet.canvas import CanvasWorkspace
    app = QApplication.instance() or QApplication([])
    credentials.create_portable_vault(PASSWORD, migrate=False)
    canvas = CanvasWorkspace(directory=store.data_root / "canvas")
    canvas.open_document("# Личный синтетический отчёт\nДанные для теста", "test-document-01")
    path = canvas.save_document()
    assert path.is_relative_to(store.data_root / "portable-data")
    assert path.read_bytes().startswith(ARTIFACT_MAGIC)
    metadata = path.with_suffix('.json').read_bytes()
    assert metadata.startswith(ARTIFACT_MAGIC) and 'Личный'.encode() not in metadata
    second = CanvasWorkspace(directory=store.data_root / "canvas")
    second.open_document("fallback", "test-document-01")
    assert second.editor.toPlainText() == canvas.editor.toPlainText()
    exported = store.data_root / "explicit-export.md"
    second.export_document(exported)
    assert exported.read_text(encoding='utf-8') == canvas.editor.toPlainText()
    second.shutdown(); second.close(); canvas.shutdown(); canvas.close()


def test_portable_unread_ledger_survives_restart(store):
    from grangerpet.pet_notifications import NotificationPayload, UnreadLedger
    credentials.create_portable_vault(PASSWORD, migrate=False)
    path = store.data_root / "unread-messages.dpapi"
    ledger = UnreadLedger(path)
    ledger.add(NotificationPayload('reply', 'test-message-01', 1, 'test-conversation-01'))
    assert ledger.path.is_relative_to(store.data_root / "portable-data")
    assert ledger.path.read_bytes().startswith(ARTIFACT_MAGIC)
    assert b"test-message-01" not in ledger.path.read_bytes()
    assert len(UnreadLedger(path).unread) == 1


@pytest.mark.parametrize("value", ["", "short", "x" * 4097, None])
def test_invalid_passphrase_cannot_create_container(tmp_path, value):
    vault = PortableVault(tmp_path / "secrets.gpx")
    with pytest.raises(VaultError):
        vault.create(value)
    assert not vault.path.exists()
