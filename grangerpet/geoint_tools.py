"""Adapt local pixel/metadata tools to the existing evidence contract."""
from .config import data_directory
from .credentials import seal_bytes, open_bytes, protected_path
from .geoint import AttachmentStore, MappingClient, GeointError
from .agent_web import _envelope, _record


def attachment_store(root=None):
    return AttachmentStore(protected_path((root or data_directory())/'attachments'),seal=seal_bytes,open_sealed=open_bytes)


def mapping_client(settings):
    return MappingClient(nominatim_endpoint=getattr(settings,'geoint_nominatim_url',''),
                         overpass_endpoint=getattr(settings,'geoint_overpass_url',''))


def readiness(tool,settings,store=None):
    if tool.startswith('map_'): return mapping_client(settings).readiness(tool)
    if tool=='image_ocr':
        backend,_=(store or attachment_store())._ocr_paths()
        if backend is None: return {'available':False,'state':'not_installed','reason':'Не установлен локальный Tesseract.'}
    return {'available':True,'state':'ready_local','reason':'Локальная обработка выбранного изображения; пиксели внешним сервисам не отправляются.'}


def execute(tool,value,*,settings,store=None,maps=None,cancel_event=None,deadline=None):
    try:
        if tool.startswith('image_'):
            store=store or attachment_store()
            if tool=='image_metadata': data=store.analyze(value,cancel_event=cancel_event)
            elif tool=='image_compare': data=store.compare(value,cancel_event=cancel_event)
            else:
                import time
                timeout=max(.1,min(30,deadline-time.monotonic())) if deadline else 30
                data=store.ocr(value,cancel_event=cancel_event,timeout=timeout)
        else: data=(maps or mapping_client(settings)).execute(tool,value,cancel_event=cancel_event)
        if data.get('status') not in ('complete','completed','low_confidence'):
            return _envelope(tool,value,status=data.get('status','unavailable'),error_code=data.get('error_code'),limitations=data.get('limitations'))
        local=tool.startswith('image_')
        url='' if local else 'https://commons.wikimedia.org/' if tool=='map_wikimedia' else 'https://www.openstreetmap.org/'
        title={'image_metadata':'Метаданные и признаки изображения','image_ocr':'Распознанный текст','image_compare':'Локальные похожие изображения',
               'map_wikimedia':'Геотеги Wikimedia Commons','map_geocode':'Географические кандидаты','map_overpass':'Объекты OpenStreetMap'}[tool]
        # Details contain actual tool output, not a model-written image description.
        row={'id':tool+':'+value,'type':'image_analysis' if local else 'map', 'platform':'Local GEOINT' if local else 'Wikimedia Commons' if tool=='map_wikimedia' else 'OpenStreetMap',
            'title':title,'url':url,'description':data.get('text','')[:2000] or title,
            'details':{**data,'acquisition':'local_tool' if local else 'official_api'},'status':'metadata','sources':[tool]}
        return _envelope(tool,value,results=[row],status='partial' if data.get('status')=='low_confidence' else 'complete',limitations=data.get('limitations',[]))
    except GeointError as exc:
        status={'cancelled':'cancelled','timeout':'timeout','rate_limited':'rate_limited','forbidden':'blocked','endpoint_required':'unavailable'}.get(exc.code,'error')
        return _envelope(tool,value,status=status,error_code=exc.code,limitations=[str(exc)])
