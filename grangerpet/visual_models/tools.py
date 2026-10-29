"""Typed, attachment-scoped adapters for the optional offline visual child."""
from __future__ import annotations

IMAGE={'type':'string','minLength':68,'maxLength':68}
_BASE={'attachment_id':IMAGE,'top_k':{'type':'integer','minimum':1,'maximum':10},
       'samples':{'type':'integer','minimum':8,'maximum':256},'seed':{'type':'integer','minimum':0,'maximum':2**31-1}}
INPUT_SCHEMAS={name:{'type':'object','properties':dict(_BASE),'required':['attachment_id'],'additionalProperties':False}
               for name in ('geoclip_predict','waypoint_predict')}
INPUT_SCHEMAS['waypoint_match']={'type':'object','properties':{'attachment_id':IMAGE,'reference_id':IMAGE},
    'required':['attachment_id','reference_id'],'additionalProperties':False}


def readiness():
    from .manager import get_manager
    state=get_manager().status()
    return {'available':state['available'],'state':'ready_local' if state['available'] else 'installed_unverified' if state['installed'] else 'not_installed',
        'reason':'Отдельный offline CPU-runtime проверен; снимки остаются локально. Координаты модели — гипотезы.' if state['available'] else
        'Файлы установлены; выполните проверку CPU-runtime в настройках инструментов.' if state['installed'] else
        'Нужен отдельный CPU-runtime GeoCLIP/Waypoint (~3,38 ГБ загрузки). Установка доступна в настройках инструментов только с вашим согласием.'}


def execute(tool,args,*,store,cancel_event,deadline):
    from .manager import get_manager
    from ..geoint import GeointError
    try:
        image=store.read_bytes(args['attachment_id'],cancel_event)
        manager=get_manager()
        if tool=='waypoint_match':
            reference=store.read_bytes(args['reference_id'],cancel_event)
            result=manager.match(image,reference,cancel_event=cancel_event,deadline=deadline)
        else:
            result=manager.infer('geoclip' if tool=='geoclip_predict' else 'waypoint',image,
                top_k=args.get('top_k',5),samples=args.get('samples',32),seed=args.get('seed',0),cancel_event=cancel_event,deadline=deadline)
    except GeointError as error:
        return {'status':'cancelled' if error.code=='cancelled' else 'error','error_code':error.code,'results':[],'limitations':[str(error)]}
    status=result.get('status')
    if status!='completed':
        return {'status':status if status in ('cancelled','timeout','error') else 'unavailable',
            'error_code':result.get('error_code','visual_worker_failed'),'results':[],
            'limitations':['Локальная модель не завершила вычисление. Результат не подтверждён.']}
    component='GeoCLIP' if tool=='geoclip_predict' else 'Waypoint'
    limitations=list(result.get('warnings',[]))+['Предсказания модели и доли сэмплов не являются вероятностью правильного места. Нужна независимая проверка по признакам и источникам.']
    details={**result,'tool':'geoclip' if tool=='geoclip_predict' else 'waypoint' if tool=='waypoint_predict' else 'waypoint_match','attachment_id':args['attachment_id'],'execution_mode':'LOCAL_MODEL','acquisition':'local_tool',
        'capability':tool,'source_record':True,'limitations':limitations}
    details['preview']=store.small_preview(args['attachment_id'],cancel_event)
    if 'reference_id' in args:details['reference_id']=args['reference_id']
    return {'status':'complete','results':[{'id':tool+':'+args['attachment_id']+':'+str(args.get('seed',0)),
        'type':'image_analysis','platform':component,'title':component+' · '+('сопоставление изображений' if tool=='waypoint_match' else 'географические гипотезы'),
        'url':'','description':'Результат локального CPU-inference по выбранному изображению.','status':'hypothesis',
        'details':details,'sources':[tool]}],'limitations':limitations}
