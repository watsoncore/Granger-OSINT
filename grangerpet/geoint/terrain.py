"""Coarse DEM geometry over explicit candidate points; never a camera solution."""
import math


def destination(lat,lon,bearing,distance_m):
    a,b,theta=map(math.radians,(lat,lon,bearing));d=distance_m/6371008.8
    x=math.asin(math.sin(a)*math.cos(d)+math.cos(a)*math.sin(d)*math.cos(theta))
    y=b+math.atan2(math.sin(theta)*math.sin(d)*math.cos(a),math.cos(d)-math.sin(a)*math.sin(x))
    return round(math.degrees(x),5),round((math.degrees(y)+180)%360-180,5)


def sample_points(lat,lon):
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (lat,lon)) or not -60<=lat<=60 or not -180<=lon<=180:raise ValueError('outside_SRTM_coverage_or_invalid_point')
    # 97 points fit the documented public API limit of 100 locations/request.
    points=[{'latitude':lat,'longitude':lon,'distance_m':0,'bearing_deg':None}]
    for index in range(32):
        for radius in (500,2000,6000):
            x,y=destination(lat,lon,index*11.25,radius)
            points.append({'latitude':x,'longitude':y,'distance_m':radius,'bearing_deg':index*11.25})
    return points


def dem_geometry(points,payload):
    if not isinstance(payload,dict) or payload.get('status')!='OK' or not isinstance(payload.get('results'),list):raise ValueError('invalid_dem_response')
    if len(payload['results'])!=len(points):raise ValueError('dem_point_count_mismatch')
    rows=[]
    for point,item in zip(points,payload['results']):
        if not isinstance(item,dict) or not isinstance(item.get('location'),dict):raise ValueError('invalid_dem_point')
        pos=item['location'];lat,lon=pos.get('lat'),pos.get('lng')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (lat,lon)):raise ValueError('invalid_dem_coordinate')
        if abs(lat-point['latitude'])>.00002 or abs(lon-point['longitude'])>.00002:raise ValueError('dem_coordinate_mismatch')
        elevation=item.get('elevation')
        if elevation is not None and (type(elevation) not in (int,float) or not math.isfinite(elevation) or not -500<=elevation<=9000):raise ValueError('invalid_dem_elevation')
        rows.append({**point,'elevation_m':elevation,'dataset':item.get('dataset')})
    base=rows[0]['elevation_m'];horizon=[]
    if base is not None:
        for bearing in range(32):
            samples=[row for row in rows[1:] if row['bearing_deg']==bearing*11.25 and row['elevation_m'] is not None]
            if samples:
                angles=[math.degrees(math.atan2(row['elevation_m']-base-1.7,row['distance_m'])) for row in samples]
                horizon.append({'bearing_deg':bearing*11.25,'sampled_max_angle_deg':round(max(angles),3),'valid_samples':len(samples)})
    valid=[row['elevation_m'] for row in rows if row['elevation_m'] is not None]
    return {'status':'complete' if len(valid)==len(rows) else 'partial','point_count':len(rows),'valid_points':len(valid),
        'center_elevation_m':base,'sampled_relief_m':round(max(valid)-min(valid),1) if valid else None,
        'points':rows,'horizon':horizon,'grid_resolution_m':90,'location_role':'model_prior_sample_point',
        'camera_position_verified':False,'sample_radius_m':6000,
        'limitations':['Грубая выборка SRTM90: 32 направления и 3 дальности; между точками могут быть пропущены хребты.',
            'Оценка горизонта не учитывает здания/растительность и не устанавливает положение камеры.',
            'Высота отсчитывается от геодезической системы DEM; наблюдатель 1.7 м — допущение, не измерение.']}
