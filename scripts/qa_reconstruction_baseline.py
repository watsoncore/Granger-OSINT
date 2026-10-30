"""Reproduce reconstruction defects; fixtures are explicitly distinguished from live reads."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]


def main():
    out = ROOT / 'output/reconstruction/baseline'
    out.mkdir(parents=True, exist_ok=True)
    os.environ['APPDATA'] = str(out / 'appdata')
    from grangerpet.agent import AgentRunner
    from grangerpet.agent_browser import PublicPageReader
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.evidence_graph import build
    from grangerpet.geoint_tools import attachment_store
    from grangerpet.visual_models.pipeline import execute
    from grangerpet.config import Settings
    from test_agent_lifecycle import Client, Registry, HISTORY, response, tool
    runner = AgentRunner(Client([response(tool(str(i))) for i in range(5)]), Registry())
    stopped = runner.run('fixture', HISTORY)
    (out / 'stopped-report.txt').write_text(stopped['text'], encoding='utf-8')
    report = {'no_progress': {'mode': 'controlled orchestration fixture, no gateway',
        'stop_reason': stopped['investigation'].get('stop_reason'),
        'raw_source_list': '**Сведения источников**' in stopped['text'],
        'synthesis_phase': stopped['investigation'].get('report_status')}}
    reader = PublicPageReader(allow_browser=False)
    url = 'https://github.com/solvnox'
    reader.allow_url(url)
    page = reader.read(url)
    (out / 'public-page.json').write_text(json.dumps(page, ensure_ascii=False), encoding='utf-8')
    graph = build([normalize_evidence(row, 'web_read', url) for row in page.get('results', [])], full=True)
    report['graph'] = {'mode': 'actual public HTTP with robots policy', 'status': page['status'],
        'error': page.get('error'), 'links': [row.get('details', {}).get('links', []) for row in page.get('results', [])],
        'publishes_links': sum(row['relation_type'] == 'publishes_link' for row in graph['relations'])}
    photograph = Path('C:/Users/Admin/Downloads/images.jpg')
    if photograph.is_file():
        store = attachment_store(out / 'local')
        imported = store.import_bytes(photograph.read_bytes(), photograph.name)
        result = execute({'attachment_id': imported['id']}, Settings(), store, deadline=time.monotonic()+300)
        (out / 'visual.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        report['visual'] = {'mode': 'actual local pixels, no image upload', 'status': result['status'],
            'stages': result['stages'], 'scene_description': any('observations' in row.get('details', {}) for row in result['results']),
            'models': [{k: row.get('details', {}).get(k) for k in ('capability', 'predictions')} for row in result['results']]}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
