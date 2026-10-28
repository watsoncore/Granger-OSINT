"""Bounded real parallel-function and SSE probes, using only the saved gateway key.

At most three short authenticated requests. No OSINT or user-data transmission;
the functions return generated diagnostic markers. No credential/text is logged.
"""
from pathlib import Path
import asyncio
from datetime import datetime, timezone
import json
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def probe(client):
    from grangerpet.ai import AIError
    from grangerpet.ai_keys import DEFAULT_DEEPSEEK_MODEL
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'actual_requests': 0,
              'parallel_tool_calls': 'unverified', 'streaming': 'unverified',
              'osint_executed': False, 'model': DEFAULT_DEEPSEEK_MODEL}
    marker = uuid.uuid4().hex[:12]
    tools = [{'type': 'function', 'function': {'name': name, 'description': 'Diagnostic local echo only.',
              'parameters': {'type': 'object', 'properties': {'value': {'type': 'string', 'enum': [value]}},
                             'required': ['value'], 'additionalProperties': False}}}
             for name, value in [('probe_left', 'left-'+marker), ('probe_right', 'right-'+marker)]]
    messages = [{'role': 'user', 'content': 'Call BOTH probe_left(value="left-'+marker+'") and probe_right(value="right-'+marker+
                 '") together in this turn. After receiving both results, return their two values verbatim.'}]
    async with client._client() as http:
        try:
            report['actual_requests'] += 1
            result = await client._post(http, {'model': DEFAULT_DEEPSEEK_MODEL, 'messages': messages,
                'tools': tools, 'tool_choice': 'auto', 'stream': False, 'max_tokens': 512})
            message = client._message(result)
            calls = message.get('tool_calls', [])
            valid, returned, ids = len(calls) == 2, [], set()
            for call in calls if isinstance(calls, list) else []:
                name = call.get('function', {}).get('name')
                expected = {'probe_left': 'left-'+marker, 'probe_right': 'right-'+marker}.get(name)
                arguments = json.loads(call.get('function', {}).get('arguments', '{}'))
                call_id = call.get('id')
                valid = valid and expected is not None and arguments == {'value': expected} and isinstance(call_id, str) and call_id not in ids
                ids.add(call_id)
                if valid:
                    returned.append({'role': 'tool', 'tool_call_id': call_id, 'content': json.dumps({'value': arguments['value']})})
            report['parallel_call_count'] = len(calls) if isinstance(calls, list) else 0
            if valid and len(returned) == 2:
                assistant = {'role': 'assistant', 'content': message.get('content'), 'tool_calls': calls}
                if isinstance(message.get('reasoning_content'), str):
                    assistant['reasoning_content'] = message['reasoning_content']
                report['actual_requests'] += 1
                final = await client._post(http, {'model': DEFAULT_DEEPSEEK_MODEL, 'messages': messages+[assistant]+returned,
                    'tools': tools, 'tool_choice': 'none', 'stream': False, 'max_tokens': 128})
                text = client._text(final)
                if 'left-'+marker in text and 'right-'+marker in text:
                    report['parallel_tool_calls'] = 'supported'
                report['parallel_round_trip'] = report['parallel_tool_calls'] == 'supported'
        except (AIError, ValueError, TypeError, KeyError) as error:
            report['parallel_error'] = getattr(error, 'code', 'invalid_response')
            report['http_status'] = getattr(error, 'http_status', None)
            if report['http_status'] in (401, 402, 403, 429):
                return report
        # A genuine SSE probe, not a claim that the application already streams.
        try:
            report['actual_requests'] += 1
            data = json.dumps({'model': DEFAULT_DEEPSEEK_MODEL, 'messages': [{'role': 'user', 'content': 'Ответь одним словом: готова.'}],
                               'stream': True, 'max_tokens': 128}, ensure_ascii=False).encode('utf-8')
            chars, done, finish, count = 0, False, False, 0
            async with http.stream('POST', 'chat/completions', content=data) as response:
                response.raise_for_status()
                is_sse = 'text/event-stream' in response.headers.get('content-type', '')
                async for line in response.aiter_lines():
                    count += len(line)
                    if count > 100000:
                        break
                    if not line.startswith('data:'):
                        continue
                    raw = line[5:].strip()
                    if raw == '[DONE]':
                        done = True
                        break
                    value = json.loads(raw)
                    for choice in value.get('choices', []):
                        delta = choice.get('delta', {}).get('content')
                        if isinstance(delta, str):
                            chars += len(delta)
                        finish = finish or choice.get('finish_reason') is not None
            report.update(streaming='supported' if is_sse and chars and done and finish else 'unverified',
                          sse_content_characters=chars, sse_done_marker=done, sse_finish_reason=finish)
        except Exception as error:
            from grangerpet.ai import _safe_deepseek_error
            safe = _safe_deepseek_error(error)
            report['stream_error'] = safe.code
            report['stream_http_status'] = safe.http_status
    return report


def main():
    from grangerpet.ai_keys import resolve_deepseek_key
    from grangerpet.ai import DeepSeekClient
    path = ROOT/'output/agent-qa/gateway-extended.json'
    if path.exists():
        raise SystemExit('Prior probe preserved; do not repeat automatically')
    key = resolve_deepseek_key()
    report = asyncio.run(probe(DeepSeekClient(key))) if key else {'actual_requests': 0, 'reason': 'missing_key'}
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    assert not key or key not in encoded
    path.write_text(encoded+'\n', encoding='utf-8')
    print(encoded)


if __name__ == '__main__':
    main()
