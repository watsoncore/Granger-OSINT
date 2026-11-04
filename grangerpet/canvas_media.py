"""Original-byte viewing authorized by a server-owned graph node, without uploads."""
from copy import deepcopy
import base64
import hashlib
import io

from .async_reply import DeferredReply
from .ui_jobs import UiJob


def media_node(bridge,payload):
    if set(payload)-{'canvas_id','investigation_id','entity_id'}:raise ValueError('Передайте идентификатор объекта, а не путь или URL.')
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
    if not reference and not attachment:raise ValueError('У выбранного объекта нет исходного изображения.')
    return node.get('label','Изображение'),attachment,reference


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
    def read():
        if attachment:data=bridge._images().read_bytes(attachment)
        else:
            from .public_media import MediaStore
            data=MediaStore().read_original(reference)
        metadata=prepare_media(data,name,reference)
        return metadata,data if action=='canvas_media_open' else None
    job=UiJob(read,bridge)
    jobs=getattr(bridge,'_canvas_media_jobs',set());bridge._canvas_media_jobs=jobs
    if len(jobs)>=2:raise ValueError('Дождитесь загрузки изображения.')
    jobs.add(job)
    def done(value,error):
        jobs.discard(job)
        if error or not value:
            deferred.resolve(error={'code':'canvas_media_unavailable','error':'Оригинал изображения недоступен или не прошёл проверку целостности.'})
        elif bridge._closed:
            deferred.resolve(error={'code':'canvas_media_closed','error':'Окно приложения закрыто.'})
        else:
            metadata,data=value
            if data:
                from .media_viewer import OriginalImageViewer
                viewer=OriginalImageViewer(data,metadata,bridge.host)
                viewer.show()
            deferred.resolve(metadata)
        job.deleteLater()
    job.done.connect(done);job.start()
    return deferred
