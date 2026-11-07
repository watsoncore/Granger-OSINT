import json
import pytest
from grangerpet.appearance import normalize_appearance
from grangerpet.crypto_icons import validate_svg


def test_independent_profiles_only_keep_presentation_fields():
    raw={'graphStyle':'minimal','graphProfiles':{'minimal':{'cardRadius':3,'shadow':0,'glow':0,'arrows':False,'entities':['discard']},'glass':{'cardRadius':19,'glow':8},'unsafe':{}}}
    saved=json.loads(normalize_appearance(json.dumps(raw)))
    assert saved['graphStyle']=='minimal'
    assert saved['graphProfiles']['minimal']['arrows'] is False
    assert saved['graphProfiles']['glass']['cardRadius']==19
    assert 'entities' not in saved['graphProfiles']['minimal']
    assert set(saved['graphProfiles'])=={'glass','minimal'}


@pytest.mark.parametrize('payload',[
    '<script>alert(1)</script>', '<image href="https://example.com/a"/>',
    '<path onload="alert(1)"/>', '<foreignObject/>', '<style>@import "external";</style>',
    '<path fill="url(https://example.com/a)"/>', '<a href="file:///secret"/>',
])
def test_svg_rejects_active_content(payload):
    with pytest.raises(ValueError):
        validate_svg(('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'+payload+'</svg>').encode())


def test_safe_svg_remains_vector_until_rasterization():
    assert b'path' in validate_svg(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1L9 9" fill="#000"/></svg>')
