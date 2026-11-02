import base64
import io
import threading
import time

import pytest
from PIL import Image

from grangerpet.geoint.tiles import TileStore, coordinates
from grangerpet.geoint.presentation import present
from grangerpet.geoint_tools import attachment_store


def png(size=(256,256)):
    out=io.BytesIO();Image.new('RGB',size,(91,119,131)).save(out,format='PNG');return out.getvalue()


def test_visible_tile_cache_is_encrypted_and_never_refetched(tmp_path):
    calls=[]
    async def fetch(url,**kwargs):calls.append((url,kwargs));return {'body':png()}
    store=TileStore(tmp_path)
    first=store.get(3,4,2,fetcher=fetch)
    assert first['key']=='3/4/2' and first['image'].startswith('data:image/png;base64,')
    assert first['attribution']=='© OpenStreetMap contributors'
    assert calls[0][0]=='https://tile.openstreetmap.org/3/4/2.png'
    assert 'Granger-OSINT' in calls[0][1]['user_agent']
    assert png() not in next(tmp_path.iterdir()).read_bytes()
    assert store.get(3,4,2,fetcher=fetch)==first and len(calls)==1


@pytest.mark.parametrize('args',[(True,0,0),(20,0,0),(2,4,0),(2,-1,0),(2,0,'1')])
def test_tile_coordinates_do_not_admit_urls_or_outside_world(args):
    with pytest.raises(ValueError):coordinates(*args)


@pytest.mark.parametrize('body',[b'<html>Denied</html>',png((512,256))])
def test_invalid_raster_is_never_cached(tmp_path,body):
    async def fetch(*args,**kwargs):return {'body':body}
    with pytest.raises(ValueError):TileStore(tmp_path).get(0,0,0,fetcher=fetch)
    assert not list(tmp_path.iterdir())


def test_cancel_does_not_write_completed_tile(tmp_path):
    cancelled=threading.Event()
    async def fetch(*args,**kwargs):cancelled.set();return {'body':png()}
    with pytest.raises(InterruptedError):TileStore(tmp_path).get(0,0,0,fetcher=fetch,cancel_event=cancelled)
    assert not list(tmp_path.iterdir())


def test_view_reads_actual_original_at_useful_size_and_missing_reference_without_fetch(tmp_path):
    store=attachment_store(tmp_path)
    identifier=store.import_bytes(png((800,400)),'fixture.png')['id']
    class CacheOnly:
        def cached(self,reference):return None
        def fetch(self,*args,**kwargs):raise AssertionError('Viewing evidence must not request images')
    rows=[{'type':'image_analysis','evidence_id':'ev_scene','details':{'tool':'image_understand','attachment_id':identifier,'description':'Fixture pixels, not a live scene test.'}},
        {'type':'reference_image','evidence_id':'ev_reference','url':'https://example.org/observed',
        'title':'Fixture image','details':{'attachment_id':identifier,'image_url':'https://example.org/image.png','license':'CC0'}}]
    value=present({'id':'a'*32,'evidence':rows},store=store,media_store=CacheOnly())
    assert value['has_geoint'] and value['images'][0]['attachment_id']==identifier
    assert value['images'][0]['media']['state']=='unavailable'
    assert value['scenes'][0]['description_original'].startswith('Fixture pixels')
    assert 'Локальная модель' in value['scenes'][0]['description']
    with Image.open(io.BytesIO(base64.b64decode(value['originals'][0]['thumbnail'].split(',')[1]))) as preview:
        assert preview.size==(800,400)
    assert 'data:image' not in str(rows)
