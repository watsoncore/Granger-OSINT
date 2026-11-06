"""Original-byte viewing authorized by a server-owned graph node, without uploads."""
from copy import deepcopy
import asyncio
import base64
import binascii
import hashlib
import io
from pathlib import Path, PureWindowsPath
import re
import time
from urllib.parse import unquote, urlsplit

from .async_reply import DeferredReply
from .ui_jobs import UiJob
from .geoint.images import GeointError, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS

IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/webp')
ATTACHMENT_FIELDS = ('id', 'name', 'width', 'height', 'bytes', 'mime', 'sha256')


def local_image(path):
    if not isinstance(path, str) or not re.fullmatch(r'[A-Za-z]:[\\/][^\x00-\x1f]{1,4096}', path):
        raise ValueError('Введите абсолютный путь к изображению на локальном диске.')
    candidate = PureWindowsPath(path)
    if candidate.is_reserved() or any(':' in part for part in candidate.parts[1:]):
        raise ValueError('Укажите обычный файл изображения.')
    try:
        source = Path(path).resolve(strict=True)
        if not re.fullmatch(r'[A-Za-z]:[\\/].+', str(source)) or not source.is_file():
            raise ValueError('Укажите обычный файл на локальном диске.')
        with source.open('rb') as stream:
            return stream.read(MAX_IMAGE_BYTES + 1), candidate.name
    except OSError:
        raise ValueError('Локальный файл изображения недоступен.') from None


async def public_image(url, cancelled):
    from .agent_browser import public_url, PublicPageReader
    from .web_http import fetch_public
    url = public_url(url)
    if urlsplit(url).scheme != 'https':
        raise ValueError('Для публичных изображений требуется HTTPS.')
    deadline = time.monotonic() + 20
    reader = PublicPageReader(max_pages=1, max_depth=0)

    async def check_source(target):
        await reader._check_robots(target, cancelled, deadline)

    response = await fetch_public(url, cancel_event=cancelled, deadline=deadline,
                                  allowed_types=IMAGE_TYPES, before_request=check_source)
    content_type = response['content_type'].split(';', 1)[0].strip()
    from .geoint.images import _signature, _MIMES
    if content_type not in IMAGE_TYPES or _MIMES[_signature(response['body'])] != content_type:
        raise ValueError('Формат изображения не совпадает с типом, объявленным источником.')
    final_url = response['final_url']
    name = unquote(urlsplit(final_url).path.rsplit('/', 1)[-1]) or 'Публичное изображение'
    return response['body'], name, {'source_url': url, 'final_url': final_url}


def prepare_attachment(bridge, payload):
    """Import only. The revision-aware queue attaches the returned stable ID."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QFileDialog
    mode = payload.get('mode')
    allowed = {
        'picker': {'mode'}, 'path': {'mode', 'path'}, 'clipboard': {'mode'},
        'bytes': {'mode', 'data', 'name'}, 'url': {'mode', 'url'},
        'native_drop': {'mode', 'token'},
        'evidence': {'mode', 'canvas_id', 'investigation_id', 'entity_id'},
    }
    if not isinstance(mode, str) or mode not in allowed or set(payload) - allowed[mode]:
        raise ValueError('Неизвестный способ добавления изображения.')
    if getattr(bridge, '_canvas_import_job', None):
        raise ValueError('Дождитесь обработки предыдущего изображения.')
    path = payload.get('path')
    bitmap = None
    evidence = None
    if mode == 'native_drop':
        delivery = getattr(bridge,'_canvas_native_drop',None)
        if not delivery or delivery[0]!=payload.get('token') or time.monotonic()>delivery[2]:
            raise ValueError('Передача изображения истекла. Перетащите файл ещё раз.')
        bridge._canvas_native_drop=None
        path=delivery[1]
    elif mode == 'picker':
        path, _ = QFileDialog.getOpenFileName(bridge.host, 'Добавить изображение', '',
                                             'Изображения (*.png *.jpg *.jpeg *.webp)')
        if not path:
            return None
    elif mode == 'clipboard':
        mime = QApplication.clipboard().mimeData()
        paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()] if mime else []
        if paths:
            path = paths[0]
        elif mime and mime.hasImage():
            bitmap = QImage(QApplication.clipboard().image())
            if bitmap.isNull() or bitmap.width() * bitmap.height() > MAX_IMAGE_PIXELS:
                raise ValueError('Изображение из буфера пустое или превышает предел разрешения.')
        else:
            raise GeointError('canvas_clipboard_empty', 'В буфере нет изображения или ссылки на локальный файл.')
    elif mode == 'evidence':
        evidence = media_node(bridge, {key: value for key, value in payload.items() if key != 'mode'})
    store = bridge._images()
    reply = DeferredReply()

    def task():
        provenance = {}
        try:
            if bitmap is not None:
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if not bitmap.save(buffer, 'PNG'):
                    raise ValueError('Не удалось прочитать изображение из буфера.')
                data, name = bytes(buffer.data()), 'Снимок из буфера.png'
            elif mode == 'bytes':
                encoded = payload.get('data', '')
                if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
                    raise ValueError('Изображение превышает ограничение 20 МиБ.')
                data, name = base64.b64decode(encoded, validate=True), payload.get('name')
            elif mode == 'url':
                data, name, provenance = asyncio.run(public_image(payload.get('url'), job.cancelled))
            elif evidence:
                name, identifier, reference = evidence
                if identifier:
                    image = store.get(identifier)
                    return {**{key: image.get(key) for key in ATTACHMENT_FIELDS}, 'provenance': {}}, ''
                data, _, provenance = asyncio.run(public_image(reference.get('url'), job.cancelled))
                provenance['evidence_id'] = reference.get('evidence_id')
            else:
                data, name = local_image(path)
            image = store.import_bytes(data, name, job.cancelled)
            return {**{key: image.get(key) for key in ATTACHMENT_FIELDS}, 'provenance': provenance}, ''
        except (GeointError, ValueError, binascii.Error) as error:
            return None, str(error)[:240] if isinstance(error, GeointError) else 'Файл или публичный адрес изображения не прошёл проверку.'
        except Exception:
            return None, 'Источник изображения недоступен или отклонил загрузку.'

    job = UiJob(task, bridge)
    bridge._canvas_import_job = job

    def done(value, error):
        bridge._canvas_import_job = None
        result, message = value or (None, error)
        reply.resolve(result, {'code': 'canvas_image_import', 'error': message} if message else None)
        job.deleteLater()

    job.done.connect(done)
    job.start()
    return reply


def media_node(bridge,payload):
    if set(payload)-{'canvas_id','investigation_id','entity_id','attachment_id'}:raise ValueError('Передайте идентификатор объекта, а не путь или URL.')
    identifier=payload.get('entity_id')
    if payload.get('canvas_id'):
        doc=getattr(bridge._research_canvas,'document',None)
        if not doc or doc['id']!=payload['canvas_id']:raise ValueError('Откройте нужное расследование.')
        identifier=doc['view'].get('instances',{}).get(identifier,{}).get('entity_id',identifier)
        nodes=doc['entities']
    else:
        graph=bridge._graph_data
        if not payload.get('investigation_id') or graph.get('investigation_id')!=payload['investigation_id']:raise ValueError('Откройте нужный граф.')
        nodes=graph.get('entities',[])
    node=next((n for n in nodes if n['id']==identifier),None)
    if not node:raise ValueError('Изображение отсутствует в текущем расследовании.')
    attrs=deepcopy(node.get('attributes',{}))
    reference=attrs.get('media') or {}
    attachment=attrs.get('attachment_id')
    linked = linked_images(attrs)
    requested = payload.get('attachment_id')
    if requested:
        match = next((item for item in linked if item.get('id') == requested), None)
        if not match and attachment != requested:
            raise ValueError('Изображение не прикреплено к этому объекту.')
        if match:
            return match.get('name', node['label']), requested, match
    elif linked:
        return linked[0].get('name', node['label']), linked[0]['id'], linked[0]
    if not reference and not attachment:raise ValueError('У выбранного объекта нет исходного изображения.')
    return node.get('label','Изображение'),attachment,reference


def linked_images(attributes):
    values = attributes.get('image_attachments')
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)
            and isinstance(value.get('id'), str) and re.fullmatch(r'img_[a-f0-9]{64}', value['id'])]


def prepare_media(data,name='',reference=None):
    from PIL import Image,ImageOps,ExifTags
    with Image.open(io.BytesIO(data)) as original:
        if original.width*original.height>40_000_000:raise ValueError('Разрешение изображения превышает предел просмотра.')
        mime=Image.MIME.get(original.format,'application/octet-stream')
        exif={ExifTags.TAGS.get(key,str(key)):str(value)[:500] for key,value in original.getexif().items() if key in (270,271,272,274,305,306,33434,33437,34855,36867,37386)}
        image=ImageOps.exif_transpose(original)
        width,height=image.size
        image.thumbnail((1600,1600))
        image=image.convert('RGB')
        preview=io.BytesIO();image.save(preview,'JPEG',quality=86)
        if preview.tell()>1_250_000:
            preview=io.BytesIO();image.save(preview,'JPEG',quality=65)
        encoded=base64.b64encode(preview.getvalue()).decode('ascii')
    return {'preview':'data:image/jpeg;base64,'+encoded,'original_available':True,'width':width,'height':height,
        'mime':mime,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'exif':exif,
        'name':name,'original_reference':(reference or {}).get('source_url','')}


def request_media(bridge,action,payload):
    name,attachment,reference=media_node(bridge,payload)
    deferred=DeferredReply()
    store = bridge._images() if attachment else None
    def read():
        if action == 'canvas_media_thumbnail' and store:
            return {'preview': store.get(attachment)['preview']}, None
        if store:data=store.read_bytes(attachment)
        else:
            from .public_media import MediaStore
            data=MediaStore().read_original(reference)
        metadata=prepare_media(data,name,reference)
        if action != 'canvas_media_open':
            return metadata, None
        from PIL import Image, ImageOps
        from PySide6.QtGui import QImage
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA')
            pixels = QImage(image.tobytes(), image.width, image.height, image.width * 4,
                            QImage.Format.Format_RGBA8888).copy()
        return metadata, pixels
    jobs=getattr(bridge,'_canvas_media_jobs',set());bridge._canvas_media_jobs=jobs
    if len(jobs)>=4:raise ValueError('Дождитесь загрузки изображения.')
    def safe_read():
        try:return read()
        except (ValueError, OSError):return None
    job=UiJob(safe_read,bridge)
    jobs.add(job)
    def done(value,error):
        jobs.discard(job)
        if error or not value:
            deferred.resolve(error={'code':'canvas_media_unavailable','error':'Оригинал изображения недоступен или не прошёл проверку целостности.'})
        elif bridge._closed:
            deferred.resolve(error={'code':'canvas_media_closed','error':'Окно приложения закрыто.'})
        else:
            metadata,image=value
            if image is not None:
                from .media_viewer import OriginalImageViewer
                viewer=OriginalImageViewer(image,metadata,bridge.host)
                viewer.show()
            deferred.resolve(metadata)
        job.deleteLater()
    job.done.connect(done);job.start()
    return deferred
