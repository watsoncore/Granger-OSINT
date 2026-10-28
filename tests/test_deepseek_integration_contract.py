"""Migration and packaging boundaries; no external API or user credentials."""
import ast
import os
from pathlib import Path
import subprocess
import sys

from grangerpet.ai_keys import DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL, deepseek_credentials
from grangerpet.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_new_gateway_credentials_never_fall_back_to_prior_provider_or_environment(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'UNUSED-OLD-PROVIDER-TEST-FIXTURE')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'UNUSED-ENVIRONMENT-TEST-FIXTURE')
    reads = []
    def getter(name):
        reads.append(name)
        return 'OLD-PROVIDER-TEST-FIXTURE' if name == 'gemini_api_key' else ''
    assert not deepseek_credentials(secret_getter=getter).available
    assert reads == ['deepseek_api_key']


def test_legacy_profile_migrates_provider_without_old_model_or_embedded_credentials():
    old = {'ai_provider': 'gemini', 'gemini_model': 'old-provider-model',
           'gemini_api_key': 'SHOULD-NOT-MIGRATE-TEST-FIXTURE',
           'size': 100, 'fps': 20, 'x': 31, 'y': 55, 'source_root': 'existing-tools'}
    settings = Settings.from_dict(old)
    assert settings.ai_provider == 'deepseek'
    assert settings.deepseek_model == DEFAULT_DEEPSEEK_MODEL == 'deepseek-v4-flash'
    assert (settings.size, settings.fps, settings.x, settings.y, settings.source_root) == (100, 20, 31, 55, 'existing-tools')
    payload = settings.to_dict()
    assert 'gemini_model' not in payload
    assert 'gemini_api_key' not in payload
    assert 'SHOULD-NOT-MIGRATE-TEST-FIXTURE' not in str(payload)


def test_active_ai_backend_imports_without_google_sdk_or_dotenv():
    # A clean interpreter prevents prior test imports from hiding a dependency.
    code = '''
import importlib.abc
import sys
class BlockLegacySDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'dotenv' or fullname.startswith(('google.genai', 'google.generativeai')):
            raise ImportError('Legacy SDK deliberately unavailable')
sys.meta_path.insert(0, BlockLegacySDK())
from grangerpet.ai import DeepSeekClient, analyze_results
from grangerpet.ai_keys import DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL
assert DEEPSEEK_BASE_URL == 'https://api.aikeysforyou.com/v1'
assert DEFAULT_DEEPSEEK_MODEL == 'deepseek-v4-flash'
assert not any(name.startswith(('google.genai', 'google.generativeai', 'dotenv')) for name in sys.modules)
print('active-backend-import-ok')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'active-backend-import-ok'


def test_release_bundle_uses_httpx_and_excludes_legacy_google_sdk():
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').lower()
    assert 'httpx==' in requirements
    assert 'google-genai' not in requirements and 'google-generativeai' not in requirements
    tree = ast.parse((ROOT / 'GrangerPet.spec').read_text(encoding='utf-8-sig'))
    analyses = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Analysis']
    assert len(analyses) == 1
    exclusions = next(keyword.value for keyword in analyses[0].keywords if keyword.arg == 'excludes')
    assert {'google.genai', 'google.generativeai'}.issubset(set(ast.literal_eval(exclusions)))
    copied_metadata = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name) and node.func.id == 'copy_metadata'
                       and node.args and isinstance(node.args[0], ast.Constant)]
    assert 'httpx' in copied_metadata
    assert 'google-genai' not in copied_metadata
    assert DEEPSEEK_BASE_URL == 'https://api.aikeysforyou.com/v1'
