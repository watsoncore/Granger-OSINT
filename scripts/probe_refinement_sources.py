"""Read-only endpoint research with no credentials or personal identifiers.

Never queries the COMB credential-dump endpoint. The invalid id0 routes only
check whether the supplied templates are actual APIs or site shells.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import httpx


URLS = (
    'https://raw.githubusercontent.com/VKCOM/vk-api-schema/master/package.json',
    'https://raw.githubusercontent.com/VKCOM/vk-api-schema/master/users/methods.json',
    'https://dev.vk.ru/ru/api/api-requests',
    'https://dev.vk.ru/versions',
    'https://api.vk.com/method/users.get?v=5.199',
    'https://looka.one/', 'https://looka.one/robots.txt', 'https://looka.one/vk_user/id0',
    'https://api.murix.ru/', 'https://murix.ru/', 'https://murix.ru/robots.txt',
    'https://v1.220vk.ru/0', 'https://220vk.ru/', 'https://v1.220vk.ru/robots.txt',
    'https://www.proxynova.com/tools/comb',
    'https://www.avito.ru/rossiya/telefony?q=Granger-OSINT',
    'https://www.avito.ru/robots.txt', 'https://developers.avito.ru/',
    'https://ok.ru/dk?', 'https://ok.ru/robots.txt',
    'https://apiok.ru/dev/methods/rest/users/users.search',
    'https://apiok.ru/dev/methods/rest/users/users.getInfo',
    'https://api.aikeysforyou.com/', 'https://api.aikeysforyou.com/v1/balance',
)


def probe(url):
    row = {'url': url}
    if urlsplit(url).hostname=='looka.one' and urlsplit(url).path.startswith('/vk_user/'):
        return {**row,'not_requested':'robots.txt disallows /vk_user/; no further route probes'}
    try:
        with httpx.Client(timeout=12, follow_redirects=True, max_redirects=3,
                          headers={'User-Agent': 'Granger-OSINT/3.1 documentation check'},
                          trust_env=False) as client:
            with client.stream('GET', url) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 400_000:
                        break
                text = bytes(body[:400_000]).decode('utf-8', errors='replace')
                title = re.search(r'<title[^>]*>(.*?)</title>', text, re.S | re.I)
                links = re.findall(r'(?:href|src)=[\"\']([^\"\']+)', text, re.I)
                row.update(status=response.status_code, final_url=str(response.url),
                    content_type=response.headers.get('content-type', ''),
                    bytes_read=len(body), sha256=hashlib.sha256(body).hexdigest(),
                    title=re.sub(r'\s+', ' ', title[1])[:160] if title else None,
                    links=[value.split('?')[0] for value in links if
                        any(term in urlsplit(value).path.lower() for term in ('doc','terms','rules','legal','search'))
                        or urlsplit(value).path.lower().endswith(('.js','.css'))][:25])
                if 'json' in row['content_type'] or text.lstrip().startswith('{'):
                    try:
                        value = json.loads(text)
                        if 'vk-api-schema' in url:
                            row['schema_version'] = value.get('version')
                            row['users_get'] = next((m for m in value.get('methods', []) if m.get('name') == 'users.get'), None)
                        elif 'error' in value:
                            error = value['error']
                            row['api_error'] = {key: error.get(key) for key in ('error_code', 'error_msg')} if isinstance(error, dict) else str(error)[:120]
                        else:
                            row['json_keys'] = list(value)[:25]
                    except (ValueError, AttributeError):
                        row['invalid_json'] = True
                elif url.endswith('/robots.txt'):
                    row['robots_excerpt'] = text[:6000]
    except httpx.TimeoutException:
        row['error'] = 'timeout'
    except httpx.HTTPError as error:
        row['error'] = type(error).__name__
    return row


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(probe, URLS))
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'output/refinement-qa/source-probes.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in rows:
        print(json.dumps({key: row[key] for key in ('url','status','title','error','api_error') if key in row}, ensure_ascii=False))


if __name__ == '__main__':
    main()
