"""Explicit live gateway check; no keys from env/files and no automatic execution.

This script spends gateway balance when a real key is supplied. Fake transport
fixtures live in pytest, not here. No OSINT tool is executed by this probe.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved-key', action='store_true', help='Explicitly use only the DeepSeek key in Windows Credential Manager')
    parser.add_argument('--output', type=Path, help='Write a secret-free JSON report; an existing file is never overwritten')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Use a new output path; prior live attempts are never overwritten')

    from grangerpet.ai import AIError, DeepSeekClient
    from grangerpet.ai_keys import DEFAULT_DEEPSEEK_MODEL, DEEPSEEK_BASE_URL, resolve_deepseek_key
    key = resolve_deepseek_key() if args.saved_key else getpass('DeepSeek gateway API key (hidden): ').strip()
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
              'provider': 'deepseek', 'model': DEFAULT_DEEPSEEK_MODEL,
              'base_url': DEEPSEEK_BASE_URL, 'transport': 'actual HTTPS; no mock replies',
              'api_success': False, 'tool_calls': {'status': 'unverified'},
              'osint_tools_executed': False}
    if not key:
        report.update(code='missing_key', request_executed=False)
        exit_code = 2
    else:
        client = DeepSeekClient(key)
        try:
            result = client.test_connection(DEFAULT_DEEPSEEK_MODEL)
            report.update(api_success=result.get('connected') is True,
                          request_executed=True,
                          received_nonempty_text=isinstance(result.get('text'), str) and bool(result['text'].strip()),
                          elapsed_seconds=result.get('elapsed_seconds'))
            capability = result.get('tool_calls')
            if isinstance(capability, dict):
                report['tool_calls'] = {name: capability[name] for name in ('status', 'round_trip', 'reason') if name in capability}
            else:
                report['tool_calls'] = client.probe_tool_calls(DEFAULT_DEEPSEEK_MODEL)
            usage = client.last_response_metadata.get('usage', {})
            if isinstance(usage, dict):
                report['usage'] = {name: value for name, value in usage.items()
                                   if name in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                   and isinstance(value, int) and not isinstance(value, bool) and value >= 0}
            report['code'] = 'ok' if report['api_success'] and report['received_nonempty_text'] else 'invalid_response'
            exit_code = 0 if report['code'] == 'ok' else 1
        except AIError as error:
            report.update(code=error.code, http_status=error.http_status,
                          retry_after=error.retry_after, request_executed=True)
            exit_code = 1
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if key and key in serialized:
        raise RuntimeError('Refusing to serialize a secret-bearing report')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + '\n', encoding='utf-8')
    print(serialized)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
