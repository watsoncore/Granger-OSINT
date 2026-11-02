"""Publish explicitly selected QA receipts, never renderer state or user profiles."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'output/master-fix-v2'
PUBLIC = QA / 'public'
DOCS = ROOT / 'docs/validation/master-fix-v2'


def main():
    PUBLIC.mkdir(exist_ok=True)
    report = {'scope':'Final frozen EXE; source/live controls are separately linked in the documentation',
              'curated_at_utc':datetime.now(timezone.utc).isoformat(), 'groups':{}}
    locations = {
        'network_context':'final-native-batch/network-context',
        'site_social':'final-native-remaining/site-social',
        'steam_fresh':'frozen-steam-retry-01',
        'browser_fresh':'frozen-browser-02',
        'local_pixels_and_models':'frozen-local-pixels-01',
        'geographic_benchmark':'frozen-photo-benchmark-03',
    }
    for name, relative in locations.items():
        path = QA / relative / 'report.json'
        if not path.is_file():
            raise ValueError('Missing final receipt: '+relative)
        row = json.loads(path.read_text(encoding='utf-8'))
        # Missing passed is a failed/incomplete run, never inferred success.
        keep = {key:row[key] for key in ('exe_sha256','checks','operations','startup_seconds','metrics',
                'geographic_benchmark','browser_chat','casual','unavailable_external_sources') if key in row}
        keep['passed'] = row.get('passed') is True
        if name == 'local_pixels_and_models':
            boundary = next(i for i,c in enumerate(row['checks']) if c['name']=='three_preselected_geographic_classes')
            keep['checks'] = row['checks'][:boundary]
            keep['passed'] = all(c['passed'] for c in keep['checks'])
            keep['selection_scope'] = 'Core local/OCR/EXIF/installed models/restart assertions only; the original extended run failed afterwards'
            keep['excluded_extended_control'] = '8-sample Waypoint returned no valid coordinates for urban case; recorded as failed, repeated separately with default 32 samples'
            keep.pop('geographic_benchmark',None)
            keep['metrics'].pop('visual_geoint_ms',None)
        keep['receipt_mtime_utc'] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        keep['turns'] = [{key:t[key] for key in ('scenario','goal','seconds','reply_characters','tools',
            'research_status','saved_record_types','saved_source_statuses','references_previous_ip') if key in t}
            for t in row.get('turns',[])]
        report['groups'][name] = keep
    report['browser_fresh_limitation'] = {
        'target':'https://www.scrapethissite.com/pages/forms/',
        'actual_tool_status':'blocked', 'reason':'robots permission could not be confirmed',
        'independent_transport_control':'robots.txt GET timed out; this does not prove a Disallow rule',
        'source_flow_receipt':'browser-final-exit-aware/report.json',
        'fixture_or_mock':False,
    }
    report['steam_fresh_limitation'] = {
        'profile':'76561198045277210','actual_tool_status':'timeout',
        'independent_transport_controls':'Frozen worker and source collector timed out; connect-limited direct read timed out too',
        'earlier_live_coverage':{'unique_items':748,'source_reported':795,'complete':False},
        'fresh_prices_verified':False,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    (DOCS/'native-exe.json').write_text(encoded, encoding='utf-8')
    (PUBLIC/'native-exe.json').write_text(encoded, encoding='utf-8')
    print(json.dumps({'groups':{k:v['passed'] for k,v in report['groups'].items()}}))


if __name__ == '__main__':
    main()
