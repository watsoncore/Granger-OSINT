"""Regression fixtures for wallpaper fidelity, typed targets and GitHub insertion."""
import base64
import io
import json

import httpx
import pytest
from PIL import Image, ImageCms

from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_tools import _SPECS
from grangerpet.canvas_capabilities import target_value
from grangerpet.evidence_graph import build
from grangerpet.geoint.images import AttachmentStore
from grangerpet.github_enrichment import execute
from grangerpet.research_canvas import CanvasError, add_node, merge_evidence, new_document, validate
from grangerpet.wallpapers import render_asset


@pytest.mark.parametrize('size',[(3840,2160),(1200,900),(900,900),(800,1300)])
@pytest.mark.parametrize('format',['PNG','JPEG','WEBP'])
def test_original_wallpaper_returns_exact_source_bytes_and_dimensions(tmp_path,size,format):
    output=io.BytesIO()
    with Image.new('RGB',size,'#547382') as image:
        image.save(output,format)
    original=output.getvalue()
    store=AttachmentStore(tmp_path,seal=lambda data:data,open_sealed=lambda data:data)
    identifier=store.import_bytes(original)['id']
    asset=render_asset(store,identifier,0,quality='original',size=(3840,2160))
    assert base64.b64decode(asset['url'].split(',',1)[1])==original
    assert (asset['width'],asset['height'])==size
    assert store.read_bytes(identifier)==original


def test_auto_wallpaper_adapts_to_physical_viewport_and_preserves_profile(tmp_path):
    output=io.BytesIO()
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.new('RGB',(3840,2160),'#729a83') as image:
        image.save(output,'PNG',icc_profile=profile)
    store=AttachmentStore(tmp_path,seal=lambda data:data,open_sealed=lambda data:data)
    identifier=store.import_bytes(output.getvalue())['id']
    small=render_asset(store,identifier,0,size=(1366,768))
    large=render_asset(store,identifier,0,size=(3840,2160))
    assert (small['width'],small['height'])==(1920,1080)
    assert (large['width'],large['height'])==(3840,2160)
    with Image.open(io.BytesIO(base64.b64decode(large['url'].split(',',1)[1]))) as rendered:
        assert rendered.info['icc_profile']==profile


def test_original_wallpaper_exif_orientation_keeps_original_bytes(tmp_path):
    output=io.BytesIO()
    with Image.new('RGB',(600,900),'#729a83') as image:
        exif=Image.Exif();exif[274]=6
        image.save(output,'JPEG',exif=exif)
    store=AttachmentStore(tmp_path,seal=lambda data:data,open_sealed=lambda data:data)
    identifier=store.import_bytes(output.getvalue())['id']
    asset=render_asset(store,identifier,0,quality='original')
    assert (asset['sourceWidth'],asset['sourceHeight'])==(900,600)
    assert base64.b64decode(asset['url'].split(',',1)[1])==output.getvalue()


def test_typed_phone_reports_specific_error_and_keeps_canonical_machine_value():
    document=new_document()
    with pytest.raises(CanvasError,match='международный'):
        add_node(document,{'type':'phone','value':'77001234567','label':'Номер'})
    assert not document['entities']
    identifier=add_node(document,{'type':'phone','value':'+7 (700) 123-45-67','label':'Номер'})
    assert next(node for node in document['entities'] if node['id']==identifier)['attributes']['value']=='+77001234567'
    validate(document)


def test_github_target_uses_typed_url_when_legacy_maigret_has_no_username():
    spec=next(spec for spec in _SPECS if spec.name=='github_profile')
    node={'type':'public_profile','label':'GitHub · unrelated title',
          'attributes':{'platform':'github','url':'https://github.com/octocat'}}
    assert target_value(node,spec)[:2]==('octocat','ready')
    node['attributes']['url']='https://t.me/octocat'
    assert target_value(node,spec)[0] is None


@pytest.fixture
def github_transport():
    from grangerpet import agent_browser, public_sources
    public_sources._NEXT.clear();public_sources._COOLDOWN.clear()
    public_sources._CACHE.clear();public_sources._HISTORY.clear();agent_browser._DOMAIN_NEXT.clear()
    requests=[]

    def response(request):
        requests.append(request)
        route=request.url.path
        data={
            '/users/octocat':{'login':'octocat','id':1,'name':'Synthetic public fixture','public_repos':1,'blog':'https://example.org'},
            '/users/octocat/repos':[{'full_name':'octocat/project','private':False,'description':'Synthetic fixture',
                                    'language':'Python','license':{'spdx_id':'MIT'},'default_branch':'main'}],
            '/users/octocat/orgs':[{'login':'fixture-org','id':2,'description':'Synthetic organization'}],
            '/repos/octocat/project/languages':{'Python':1200},
            '/repos/octocat/project/releases':[{'name':'v1','tag_name':'v1','draft':False,
                                                'html_url':'https://github.com/octocat/project/releases/tag/v1',
                                                'published_at':'2026-01-01T00:00:00Z'}],
        }[route]
        return httpx.Response(200,json=data)

    def factory(**kwargs):
        kwargs['transport']=httpx.MockTransport(response)
        return httpx.AsyncClient(**kwargs)

    async def resolver(host,port):
        return ['93.184.216.34']
    return factory,resolver,requests


def test_github_enrichment_normalizes_and_inserts_related_findings(github_transport):
    factory,resolver,requests=github_transport
    result=execute('octocat',client_factory=factory,resolver=resolver)
    assert result['status']=='complete'
    assert len(requests)==5
    assert all('authorization' not in request.headers for request in requests)
    records=[normalize_evidence(row,'github_profile','octocat') for row in result['results']]
    graph=build(records,full=True,limit=5000)
    relations={edge['relation_type'] for edge in graph['relations']}
    assert {'repository_namespace','public_organization_membership','has_public_release','profile_publishes_url'}<=relations
    repository=next(node for node in graph['entities'] if node['type']=='repository')
    assert repository['attributes']['languages']=={'Python':1200}
    assert repository['attributes']['license']['spdx_id']=='MIT'
    document=new_document()
    owner=add_node(document,{'type':'public_profile','value':'https://github.com/octocat','label':'Профиль'})
    position=dict(document['view']['positions'][owner])
    merge_evidence(document,records)
    validate(document)
    assert document['view']['positions'][owner]==position
    assert any(node['type']=='repository' for node in document['entities'])
    assert not any(node['attributes'].get('identity_verified') is True for node in document['entities'])
