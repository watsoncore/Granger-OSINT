import io
import json

from PIL import Image

from grangerpet.appearance import normalize_appearance, referenced_wallpapers
from grangerpet.config import Settings
from grangerpet.geoint.images import AttachmentStore
from grangerpet.research_canvas import new_document, record_canvas_event, validate
from grangerpet.wallpapers import render_asset


def test_preferences_validate_colors_wallpaper_bounds_and_scopes():
    identifier = 'img_' + 'a' * 64
    canvas_id = 'b' * 32
    raw = json.dumps({'theme': 'azure', 'glow': 80, 'colors': {'node': '#7E90D8', 'edge': 'url(unsafe)'},
                      'wallpaper': {'source': 'image', 'image': identifier, 'dim': -1, 'blur': 25},
                      'overrides': {canvas_id: {'source': 'black'}, '../unsafe': {'source': 'image'}},
                      'presets': {'Profile': {'theme': 'crimson'}}, 'private_file': 'discard me'})
    settings = Settings.from_dict({'workspace_appearance': raw, 'ui_theme': 'black'})
    preferences = json.loads(settings.workspace_appearance)
    assert settings.ui_theme == 'black'
    assert preferences['colors'] == {'node': '#7e90d8'}
    assert preferences['glow'] == 36
    assert preferences['wallpaper']['dim'] == 0
    assert preferences['wallpaper']['blur'] == 20
    assert set(preferences['overrides']) == {canvas_id}
    assert preferences['presets']['Profile']['theme'] == 'crimson'
    assert preferences['hidePrivate'] is True
    assert 'private_file' not in preferences
    assert referenced_wallpapers(settings.workspace_appearance) == {identifier}
    assert normalize_appearance('{') == ''


def test_wallpaper_render_keeps_original_and_bounds_decoded_preview(tmp_path):
    output = io.BytesIO()
    with Image.new('RGB', (2048, 1024), '#6498ad') as image:
        image.save(output, 'PNG')
    original = output.getvalue()
    store = AttachmentStore(tmp_path / 'wallpapers', seal=lambda data: data, open_sealed=lambda data: data)
    identifier = store.import_bytes(original)['id']
    result = render_asset(store, identifier, 9)
    assert result['url'].startswith('data:image/webp;base64,')
    assert (result['width'], result['height']) == (1920, 960)
    assert store.read_bytes(identifier) == original


def test_local_canvas_history_has_bounded_metadata_and_accepts_legacy_data():
    document = new_document()
    validate(document)
    for _ in range(125):
        record_canvas_event(document, 'findings', ['ent_' + '0' * 24], 3, 'username_maigret')
    validate(document)
    assert len(document['activity']) == 120
    assert set(document['activity'][0]) == {'id', 'kind', 'at', 'ids', 'count', 'tool'}
