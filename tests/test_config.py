from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grangerpet.config import Settings, SettingsStore, resource_path


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.vault = {}
        reading = patch("grangerpet.credentials.get_secret", side_effect=lambda name: self.vault.get(name, ""))
        writing = patch("grangerpet.credentials.set_secret", side_effect=lambda name, value: self.vault.__setitem__(name, value))
        reading.start()
        writing.start()
        self.addCleanup(reading.stop)
        self.addCleanup(writing.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SettingsStore(Path(self.temporary.name) / "nested" / "settings.json")

    def test_missing_file_returns_defaults_without_creating_directories(self):
        self.assertEqual(self.store.load(), Settings())
        self.assertFalse(self.store.path.parent.exists())

    def test_roundtrip_preserves_all_fields_and_negative_monitor_coordinates(self):
        settings = Settings(size=312, fps=18, cursor_reaction=False,
                            x=-1730, y=210, api_key="local-key", api_cx="engine-id")
        self.store.save(settings)
        self.assertEqual(self.store.load(), settings)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])
        self.assertEqual(json.loads(self.store.path.read_text(encoding="utf-8")), settings.to_dict())

    def test_corrupt_or_non_object_json_returns_defaults(self):
        self.store.path.parent.mkdir(parents=True)
        for payload in ("{broken", "null", "[]", '"not an object"'):
            self.store.path.write_text(payload, encoding="utf-8")
            context = self.assertLogs("grangerpet.config", level="WARNING") if payload == "{broken" else nullcontext()
            with context:
                self.assertEqual(self.store.load(), Settings())

    def test_types_ranges_and_nonfinite_values_are_validated(self):
        settings = Settings.from_dict({"size": 9999, "fps": -10, "cursor_reaction": "false",
                                       "x": True, "y": "33", "api_key": "  key  ", "api_cx": 42})
        self.assertEqual(settings.size, 195)
        self.assertEqual(settings.fps, 8)
        self.assertTrue(settings.cursor_reaction)
        self.assertIsNone(settings.x)
        self.assertIsNone(settings.y)
        self.assertEqual(settings.api_key, "key")
        self.assertEqual(settings.api_cx, "")
        for number in (float("nan"), float("inf"), float("-inf")):
            self.assertEqual(Settings.from_dict({"size": number}).size, 195)
        self.assertEqual(Settings.from_dict({"size": True}).size, 195)

    def test_size_migration_and_secrets_never_persist_as_plaintext(self):
        self.store.path.parent.mkdir(parents=True)
        self.store.path.write_text(json.dumps({"size": 420, "api_key": "legacy-private-key"}), encoding="utf-8")
        settings = self.store.load()
        self.assertEqual(settings.size, 195)
        self.assertEqual(self.vault["google_api_key"], "legacy-private-key")
        self.assertNotIn("legacy-private-key", self.store.path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", settings.to_dict())
        self.assertEqual(Settings.from_dict({"size": 1}).size, 100)

    def test_failed_atomic_replace_preserves_previous_file_and_removes_temporary(self):
        original = Settings(size=180, x=50, y=80)
        self.store.save(original)
        with patch("grangerpet.config.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.store.save(Settings(size=350))
        self.assertEqual(self.store.load(), original)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_asset_resources_resolve_inside_package_in_source_and_frozen_build(self):
        source_root = Path(__file__).resolve().parent.parent
        self.assertEqual(resource_path("assets/character.png"), source_root / "grangerpet/assets/character.png")
        frozen_root = Path(self.temporary.name)
        with patch("grangerpet.config.sys._MEIPASS", str(frozen_root), create=True):
            self.assertEqual(resource_path("assets/character.png"), frozen_root / "grangerpet/assets/character.png")
            self.assertEqual(resource_path("README.md"), frozen_root / "README.md")

    def test_research_zero_budgets_and_new_settings_roundtrip(self):
        settings = Settings(agent_steps=0, agent_calls=0, agent_timeout=0, agent_tokens=0, agent_page_limit=0,
                            agent_page_depth=8, agent_parallel=4, agent_tool_timeout=43, agent_request_timeout=120,
                            agent_auto_continue=False, agent_budget_behavior='stop', notifications_enabled=False,
                            notifications_animate=False, notifications_reply=False, notifications_investigation=False,
                            notifications_errors=False)
        self.store.save(settings)
        self.assertEqual(self.store.load(), settings)

    def test_only_legacy_imposed_preset_migrates_and_explicit_budgets_survive(self):
        legacy = {'agent_steps': 10, 'agent_calls': 14, 'agent_timeout': 240, 'agent_tokens': 48000,
                  'agent_page_limit': 6, 'agent_page_depth': 2}
        migrated = Settings.from_dict(legacy)
        self.assertEqual((migrated.agent_steps, migrated.agent_calls, migrated.agent_timeout,
                          migrated.agent_tokens, migrated.agent_page_limit), (0, 0, 0, 0, 0))
        legacy['agent_calls'] = 18
        self.assertEqual(Settings.from_dict(legacy).agent_tokens, 48000)
        self.assertEqual(Settings.from_dict({**legacy, 'research_settings_version': 2}).agent_steps, 10)
        self.assertTrue(Settings.from_dict({'agent_auto_continue': 'false', 'notifications_enabled': 0}).notifications_enabled)
        self.assertEqual(Settings.from_dict({'research_settings_version': 'bad'}).research_settings_version, 2)


if __name__ == "__main__":
    unittest.main()
