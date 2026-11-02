"""Conservative sky/foreground trace and shape diagnostics from actual pixels.

Not semantic segmentation. Clouds, snow, trees, haze and buildings may confuse
this heuristic. Outputs are reviewable overlays, not verified mountain matches.
"""
import io
import math
import statistics


def extract(raw):
    from PIL import Image,ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        if source.width*source.height>16_000_000:raise ValueError('skyline_pixel_limit')
        image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((128,96))
    width,height=image.size;pixels=image.load();points=[]
    def sky(rgb):
        r,g,b=rgb
        return (b>=max(100,r*.96) and b>=g*.91 and max(rgb)>125) or (min(rgb)>160 and max(rgb)-min(rgb)<40)
    for x in range(width):
        if not sky(pixels[x,0]):continue
        first=None
        for y in range(1,height-2):
            if not sky(pixels[x,y]) and not sky(pixels[x,y+1]):first=y;break
        if first is not None and .07*height<first<.9*height:points.append([round(x/max(1,width-1),4),round(first/height,4)])
    coverage=len(points)/max(1,width)
    values=[p[1] for p in points]
    if coverage<.65 or len(points)<24 or statistics.pstdev(values)<.012:
        return {'status':'unavailable','reason':'no_reliable_nonflat_sky_foreground_trace','column_coverage':round(coverage,3),
            'location_verified':False,'algorithm':'top_connected_color_boundary_v1'}
    return {'status':'complete','points':points,'column_coverage':round(coverage,3),'algorithm':'top_connected_color_boundary_v1',
        'coordinate_space':'normalized_oriented_image','location_verified':False,
        'limitations':['Эвристическая граница неба; облака, деревья, здания и снег могут дать ложный контур. Нужен визуальный просмотр.']}


def _interpolate(points,x):
    if x<points[0][0] or x>points[-1][0]:return None
    for index in range(1,len(points)):
        if points[index][0]>=x:
            a,b=points[index-1],points[index];fraction=(x-a[0])/(b[0]-a[0] or 1)
            return a[1]+fraction*(b[1]-a[1])
    return points[-1][1]


def _normal(values):
    mean=statistics.mean(values);sd=statistics.pstdev(values)
    return [(v-mean)/sd for v in values] if sd>.0001 else None


def compare(a,b):
    if a.get('status')!='complete' or b.get('status')!='complete':return {'status':'unavailable','location_verified':False}
    errors=[]
    for shift in (-.1,-.05,0,.05,.1):
        pairs=[(_interpolate(a['points'],i/47),_interpolate(b['points'],i/47+shift)) for i in range(48)]
        pairs=[pair for pair in pairs if None not in pair]
        if len(pairs)<32:continue
        x,y=_normal([v[0] for v in pairs]),_normal([v[1] for v in pairs])
        if x is None or y is None:continue
        errors.append((math.sqrt(sum((p-q)**2 for p,q in zip(x,y))/len(x)),shift,len(x)))
    if not errors:return {'status':'unavailable','location_verified':False}
    error,shift,count=min(errors)
    return {'status':'complete','standardized_shape_rmse':round(error,4),'horizontal_shift_fraction':shift,'sample_count':count,
        'original_points':a['points'],'reference_points':b['points'],'location_verified':False,
        'interpretation':'Сходство эвристических контуров, не вероятность совпадения. Нет подтверждённого масштаба, направления и точки камеры.'}


def fit_dem(trace,terrain):
    if trace.get('status')!='complete':return {'status':'unavailable','reason':'no_pixel_trace','camera_position_verified':False}
    horizon=terrain.get('horizon',[])
    if len(horizon)!=32:return {'status':'unavailable','reason':'incomplete_dem_horizon','camera_position_verified':False}
    observed=[_interpolate(trace['points'],i/47) for i in range(48)]
    valid=[(index,value) for index,value in enumerate(observed) if value is not None]
    if len(valid)<32:return {'status':'unavailable','camera_position_verified':False}
    # Compare relative shape after removing unknown pitch/vertical scale. This
    # deliberately cannot recover an absolute camera bearing/FOV or altitude.
    observed_norm=_normal([-value for _,value in valid]);fits=[]
    for fov in (45,67.5,90):
        for start in range(32):
            expected=[]
            for index,_ in valid:
                position=start+index/47*fov/11.25;left=int(position)%32;fraction=position-int(position)
                expected.append(horizon[left]['sampled_max_angle_deg']*(1-fraction)+horizon[(left+1)%32]['sampled_max_angle_deg']*fraction)
            expected_norm=_normal(expected)
            if observed_norm is None or expected_norm is None:continue
            error=math.sqrt(sum((x-y)**2 for x,y in zip(observed_norm,expected_norm))/len(valid))
            fits.append((error,start*11.25+fov/2,fov))
    if not fits:return {'status':'unavailable','reason':'flat_dem_or_image_shape','camera_position_verified':False}
    error,bearing,fov=min(fits)
    return {'status':'complete','standardized_shape_rmse':round(error,4),'searched_windows':len(fits),
        'best_window_center_bearing_deg':bearing%360,'assumed_horizontal_fov_deg':fov,'camera_position_verified':False,
        'use':'weak_candidate_screening_only','not_calibrated_probability':True,
        'limitations':['Лучшее из 96 окон при неизвестном ракурсе; случайное сходство возможно.',
            'Это не измеренное направление камеры. DEM-профиль построен вокруг модельного prior, не проверенной точки съёмки.']}
