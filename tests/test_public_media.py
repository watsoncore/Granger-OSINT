import asyncio
import io
import pytest
from PIL import Image
from grangerpet.public_media import MediaStore,media_reference
from grangerpet.link_relevance import technical_url


def reference():return media_reference({'evidence_id':'ev_abcdef','url':'https://example.org/observed','details':{'image_url':'https://example.org/picture.png'}})


def test_raster_cache_is_encrypted_and_restored_without_network(tmp_path):
    image=io.BytesIO();Image.new('RGB',(64,40)).save(image,format='PNG');body=image.getvalue()
    async def fetch(url,**kwargs):return {'body':body,'content_type':'image/png','final_url':url}
    store=MediaStore(tmp_path);value=asyncio.run(store.fetch(reference(),fetcher=fetch))
    assert value['thumbnail'].startswith('data:image/jpeg;base64,')
    assert (value['width'],value['height'])==(64,40)
    encrypted=next(tmp_path.iterdir()).read_bytes()
    assert b'example.org' not in encrypted and body not in encrypted
    async def no_network(*args,**kwargs):raise AssertionError('Cache must not request again')
    assert asyncio.run(store.fetch(reference(),fetcher=no_network))==value


@pytest.mark.parametrize('mime,body',[('image/svg+xml',b'<svg/>'),('image/png',b'<html>access denied</html>'),('image/jpeg',b'not an image')])
def test_untrusted_media_is_never_rendered_or_saved(tmp_path,mime,body):
    async def fetch(url,**kwargs):return {'body':body,'content_type':mime,'final_url':url}
    with pytest.raises((ValueError,OSError)):asyncio.run(MediaStore(tmp_path).fetch(reference(),fetcher=fetch))
    assert not list(tmp_path.iterdir())


def test_only_evidence_supplied_public_http_media_is_eligible():
    assert media_reference({'evidence_id':'ev_a','details':{'image_url':'file:///C:/private.png'}}) is None
    assert media_reference({'details':{'avatar_url':'https://example.org/avatar'}}) is None
    assert technical_url('https://github.com/login')
    assert technical_url('https://camo.githubusercontent.com/hash/image')
    assert not technical_url('https://github.com/watsoncore/Granger-OSINT')


def test_expected_cancel_does_not_raise_global_error_toast(monkeypatch):
    from grangerpet.ui_jobs import UiJob
    from unittest.mock import Mock
    report=Mock();monkeypatch.setattr('grangerpet.errors.report_exception',report)
    def cancelled():raise InterruptedError('cancelled')
    job=UiJob(cancelled);job.cancel();job._run()
    report.assert_not_called()
