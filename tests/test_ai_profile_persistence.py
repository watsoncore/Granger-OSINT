"""Regression: pet movement and Launcher messages must not revert saved AI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from grangerpet.config import Settings, with_pet_preferences


def test_launcher_appearance_message_cannot_revert_deepseek_provider_or_model():
    current = Settings(ai_provider='deepseek', deepseek_model='deepseek-v4-flash', source_root='kept-tools', x=75, y=25)
    # Also cover an older Launcher sending its complete stale settings object.
    stale = Settings(size=125, fps=15, cursor_reaction=False).to_dict()
    result = with_pet_preferences(current, stale)
    assert result.ai_provider == 'deepseek'
    assert result.deepseek_model == 'deepseek-v4-flash'
    assert result.source_root == 'kept-tools'
    assert (result.x, result.y) == (75, 25)
    assert (result.size, result.fps, result.cursor_reaction) == (125, 15, False)


def test_legacy_gemini_provider_migrates_only_selection_not_model_or_key():
    legacy = {'ai_provider': 'gemini', 'gemini_model': 'legacy-google-model',
              'gemini_api_key': 'legacy-fixture-secret', 'deepseek_model': 'not-the-gateway-model',
              'source_root': 'existing-tools', 'size': 125, 'x': 60, 'y': 75}
    settings = Settings.from_dict(legacy)
    assert settings.ai_provider == 'deepseek'
    assert settings.deepseek_model == 'deepseek-v4-flash'
    assert settings.source_root == 'existing-tools'
    assert (settings.size, settings.x, settings.y) == (125, 60, 75)
    serialized = str(settings.to_dict())
    assert 'legacy-google-model' not in serialized and 'legacy-fixture-secret' not in serialized
    assert 'gemini_model' not in settings.to_dict()
