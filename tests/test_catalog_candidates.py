"""Candidate metadata cannot manufacture implemented or verified tools."""
import json
from urllib.parse import urlsplit

from grangerpet.catalog_candidates import catalog_audit, catalog_candidates
from grangerpet.agent_tools import _SPECS


def test_candidates_have_unique_ids_urls_and_documented_explicit_access_modes():
    rows = catalog_candidates()
    assert len(rows) == 9
    assert len({row['id'] for row in rows}) == len(rows)
    assert len({row['source_url'] for row in rows}) == len(rows)
    for row in rows:
        assert row['description'] and row['reason'] and row['accepted_inputs']
        assert row['access_mode'] in {'OFFICIAL_API','LOCAL_CLI','OPEN_DATASET','PERMITTED_HTTP','PERMITTED_BROWSER','MANUAL_ONLY','NOT_SUPPORTED'}
        assert row['provenance'] == 'official_documentation'
        for key in ('source_url','documentation_url'):
            parsed = urlsplit(row[key])
            assert parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password


def test_candidate_metadata_is_not_execution_readiness_or_agent_schema():
    installed = {spec.name for spec in _SPECS}
    for row in catalog_candidates():
        assert row['id'] not in installed
        assert row['status'] == row['readiness_status'] == row['state'] == 'catalog_only'
        assert row['implemented'] is row['available'] is row['live_verified'] is False
        assert row['from_osint4all'] is False
    retired = next(row for row in catalog_candidates() if 'bing_visual' in row['id'])
    assert retired['access_mode'] == 'NOT_SUPPORTED'


def test_exact_requested_collection_is_not_substituted_or_counted_as_scraped():
    audit = catalog_audit()
    assert audit['url'] == 'https://start.me/p/L1rEYQ/osint4all'
    assert audit['extracted_candidates'] == 0 and audit['status'] == 'content_unavailable'
    assert 'Void' not in json.dumps(catalog_candidates())


def test_returned_metadata_cannot_mutate_catalog_or_audit():
    rows = catalog_candidates(); rows[0]['implemented'] = True; rows[0]['accepted_inputs'].append('arbitrary')
    audit = catalog_audit(); audit['extracted_candidates'] = 100
    assert catalog_candidates()[0]['implemented'] is False
    assert 'arbitrary' not in catalog_candidates()[0]['accepted_inputs']
    assert catalog_audit()['extracted_candidates'] == 0
