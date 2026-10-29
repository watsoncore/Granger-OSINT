"""Bounded scalar ShadowFinder computation, without plotting or network.

Shadow length comparison is adapted from Bellingcat ShadowFinder (MIT).
Sun position is a scalar port of suncalc-py 0.1.x (MIT, upstream SunCalc
BSD-2-Clause); full notices are in resources/third-party/integrations19.
It intentionally returns an ambiguous band, not an image geolocation verdict.
"""
from __future__ import annotations
from datetime import datetime, timezone
import math
import time

class LocalToolError(ValueError):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)

def check(cancel_event=None,deadline=None):
    if cancel_event is not None and cancel_event.is_set():
        raise LocalToolError('cancelled','Локальное вычисление отменено.')
    if deadline is not None and time.monotonic()>=deadline:
        raise LocalToolError('timeout','Истекло время локального вычисления.')

def number(value,name,minimum,maximum):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise LocalToolError('invalid_arguments',f'Некорректное числовое поле {name}.')
    return float(value)

def utc_datetime(value):
    if not isinstance(value,str) or len(value)>40:
        raise LocalToolError('invalid_arguments','Нужно точное время ISO8601 сZ или смещением UTC.')
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None or result.utcoffset() is None or not 1900<=result.year<=2100:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        raise LocalToolError('invalid_arguments','Нужны год1900–2100 и явно указанная временная зона. Неизвестное местное время не угадывается.') from None

def sun_position(date_time, latitude, longitude):
    """Geometric altitude radians and north-clockwise azimuth degrees.

    Matches upstream suncalc-py get_position(date,lon,lat) without atmospheric
    refraction, matching the library called by ShadowFinder 0.7.1.
    """
    dt=utc_datetime(date_time) if isinstance(date_time,str) else date_time
    if not isinstance(dt,datetime) or dt.tzinfo is None:
        raise LocalToolError('invalid_arguments','Нужно время сUTCtimezone.')
    lat=number(latitude,'latitude',-90,90);lon=number(longitude,'longitude',-180,180)
    rad=math.pi/180
    days=dt.timestamp()/86400-.5+2440588-2451545
    anomaly=rad*(357.5291+.98560028*days)
    center=rad*(1.9148*math.sin(anomaly)+.02*math.sin(2*anomaly)+.0003*math.sin(3*anomaly))
    ecliptic=anomaly+center+rad*102.9372+math.pi
    obliquity=rad*23.4397
    declination=math.asin(math.sin(ecliptic)*math.sin(obliquity))
    ascension=math.atan2(math.sin(ecliptic)*math.cos(obliquity),math.cos(ecliptic))
    hour_angle=rad*(280.16+360.9856235*days)+rad*lon-ascension
    phi=rad*lat
    altitude=math.asin(max(-1,min(1,math.sin(phi)*math.sin(declination)+math.cos(phi)*math.cos(declination)*math.cos(hour_angle))))
    azimuth=math.atan2(math.sin(hour_angle),math.cos(hour_angle)*math.sin(phi)-math.tan(declination)*math.cos(phi))
    return {'altitude_radians':altitude,'sun_altitude_deg':math.degrees(altitude),'azimuth_north_clockwise_deg':(math.degrees(azimuth)+180)%360}

def _scenario(args):
    if not isinstance(args,dict):raise LocalToolError('invalid_arguments','Параметры должны быть объектом.')
    allowed={'datetime_utc','object_height','shadow_length','sun_altitude_deg','tolerance_fraction','grid_step_deg','bounds','max_cells','candidates'}
    if set(args)-allowed:raise LocalToolError('invalid_arguments','Есть неизвестные параметры локального расчёта.')
    dt=utc_datetime(args.get('datetime_utc'))
    angle=args.get('sun_altitude_deg');height=args.get('object_height');length=args.get('shadow_length')
    if angle is not None:
        if height is not None or length is not None:raise LocalToolError('invalid_arguments','Укажите угол ИЛИ высоту и длину тени.')
        angle=number(angle,'sun_altitude_deg',.1,89.9);mode='altitude_angle'
    else:
        height=number(height,'object_height',.0001,1000000);length=number(length,'shadow_length',.0001,1000000)
        angle=math.degrees(math.atan2(height,length));mode='shadow_length'
    tolerance=number(args.get('tolerance_fraction',.1),'tolerance_fraction',.001,.5)
    return dt,angle,height,length,mode,tolerance

def _evaluate(dt,latitude,longitude,angle,height,length,mode,tolerance):
    pos=sun_position(dt,latitude,longitude);altitude=pos['altitude_radians']
    predicted=None if altitude<=0 else height/math.tan(altitude) if height is not None else None
    relative=None if altitude<=0 else (predicted-length)/length if mode=='shadow_length' else (pos['sun_altitude_deg']-angle)/angle
    # Compatibility is an explicit normalized residual, never a probability.
    return {**{key:value for key,value in pos.items() if key!='altitude_radians'},'predicted_shadow_length':predicted,
        'relative_residual':relative,'matches_tolerance':relative is not None and abs(relative)<=tolerance,
        'compatibility_score':0 if relative is None else max(0,1-abs(relative)/tolerance)}

def shadow_regions(args,*,cancel_event=None,deadline=None):
    check(cancel_event,deadline);started=time.monotonic()
    dt,angle,height,length,mode,tolerance=_scenario(args)
    step=number(args.get('grid_step_deg',2),'grid_step_deg',.5,10)
    bounds=args.get('bounds',[-180,-60,180,85])
    if not isinstance(bounds,(list,tuple)) or len(bounds)!=4:raise LocalToolError('invalid_arguments','bounds=[west,south,east,north].')
    west,south,east,north=[number(value,'bounds',-180 if i%2==0 else -90,180 if i%2==0 else 90) for i,value in enumerate(bounds)]
    if west>=east or south>=north:raise LocalToolError('invalid_arguments','bounds должен иметь положительную площадь, без перехода через180°.')
    max_cells=args.get('max_cells',500)
    if type(max_cells) is not int or not 1<=max_cells<=2000:raise LocalToolError('invalid_arguments','max_cells должен быть1–2000.')
    cols,rows=math.ceil((east-west)/step),math.ceil((north-south)/step)
    if rows*cols>210000:raise LocalToolError('invalid_arguments','Слишком мелкая сетка. Увеличьте grid_step_deg или ограничьте bounds.')
    features=[];matches=0
    for row in range(rows):
        check(cancel_event,deadline);bottom=south+row*step;top=min(north,bottom+step);lat=(bottom+top)/2
        for col in range(cols):
            if col%64==0:check(cancel_event,deadline)
            left=west+col*step;right=min(east,left+step);lon=(left+right)/2
            data=_evaluate(dt,lat,lon,angle,height,length,mode,tolerance)
            if data['matches_tolerance']:
                matches+=1
                if len(features)<max_cells:
                    features.append({'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[left,bottom],[right,bottom],[right,top],[left,top],[left,bottom]]]},
                        'properties':{'center_latitude':lat,'center_longitude':lon,**data}})
    candidates=args.get('candidates',[])
    if not isinstance(candidates,list) or len(candidates)>100:raise LocalToolError('invalid_arguments','Не более100 кандидатов.')
    scores=[]
    for candidate in candidates:
        check(cancel_event,deadline)
        if not isinstance(candidate,dict) or set(candidate)-{'latitude','longitude','label'}:raise LocalToolError('invalid_arguments','Кандидат должен содержать latitude/longitude/label.')
        lat=number(candidate.get('latitude'),'latitude',-90,90);lon=number(candidate.get('longitude'),'longitude',-180,180)
        label=candidate.get('label','')
        if not isinstance(label,str) or len(label)>150:raise LocalToolError('invalid_arguments','Слишком длинная подпись кандидата.')
        scores.append({'latitude':lat,'longitude':lon,'label':label,**_evaluate(dt,lat,lon,angle,height,length,mode,tolerance)})
    return {'tool':'shadow_regions','status':'complete','execution_mode':'LOCAL_PYTHON','method':'ShadowFinder relative residual + scalar SunCalc solar position',
        'datetime_utc':dt.isoformat().replace('+00:00','Z'),'observed_sun_altitude_deg':angle,'object_height':height,'shadow_length':length,'comparison_mode':mode,
        'tolerance_fraction':tolerance,'grid_step_deg':step,'bounds':list(bounds),'cells_evaluated':rows*cols,'matching_cells_total':matches,'matching_cells_returned':len(features),
        'truncated':matches>len(features),'regions':{'type':'FeatureCollection','features':features},'candidate_scores':scores,
        'score_semantics':'Normalized geometric compatibility, not location probability. Cell center evaluation, not an exact boundary.',
        'duration_ms':round((time.monotonic()-started)*1000,2),
        'warnings':['Дата и точноеUTCвремя должны быть известны; неизвестные параметры не выводятся из фотографии.',
         'Одно отношение высоты и тени даёт множество возможных мест. Совпадение не подтверждает геолокацию.',
         'Модель предполагает вертикальный объект и ровную поверхность; не учитывает рельеф, наклон, атмосферную рефракцию и ошибку измерения времени.',
         'Ячейки — оценка в центре с указанным шагом, не точные границы. ВремяUTCобязательно, локальные timezonegridнеиспользуются.']}
