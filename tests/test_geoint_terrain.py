import io
import math
from urllib.parse import urlencode

import pytest
from PIL import Image,ImageDraw

from grangerpet.geoint.terrain import sample_points,dem_geometry
from grangerpet.geoint.open_geography import OpenGeography,DEM,OHM,SWISS
from grangerpet.geoint.scene_language import russian_scene
from grangerpet.geoint.skyline import extract,compare,fit_dem


def test_dem_uses_actual_returned_points_and_never_claims_a_camera_position():
    points=sample_points(43.15,77.05)
    data={'status':'OK','results':[{'location':{'lat':p['latitude'],'lng':p['longitude']},
        'elevation':1000+(.2*p['distance_m'] if p['bearing_deg']==0 else 0),'dataset':'srtm90m'} for p in points]}
    result=dem_geometry(points,data)
    assert len(points)==97 and result['valid_points']==97 and len(result['horizon'])==32
    assert result['horizon'][0]['sampled_max_angle_deg']>10
    assert result['location_role']=='model_prior_sample_point' and result['camera_position_verified'] is False
    data['results'][1]['elevation']=None
    assert dem_geometry(points,data)['valid_points']==96
    data['results'][2]['location']['lat']=1
    with pytest.raises(ValueError,match='mismatch'):dem_geometry(points,data)


@pytest.mark.parametrize('point',[(True,1),(90,0),(float('nan'),1),(1,181)])
def test_dem_rejects_invalid_or_outside_coverage_points(point):
    with pytest.raises(ValueError):sample_points(*point)


def test_source_batches_stay_within_unchanged_transport_url_limit():
    calls=[]
    def request(endpoint,params,*_):
        assert len(endpoint+'?'+urlencode(params))<2000
        pairs=[tuple(map(float,p.split(','))) for p in params['locations'].split('|')]
        calls.append(pairs)
        return {'status':'OK','results':[{'location':{'lat':a,'lng':b},'elevation':500,'dataset':'srtm90m'} for a,b in pairs]}, {'url':endpoint,'body_sha256':'a'*64}
    result=OpenGeography(request).terrain({'latitude':43.15,'longitude':77.05})
    assert len(calls)==2 and sum(map(len,calls))==97 and len(result['receipts'])==2


def test_historical_license_and_dates_are_source_fields_not_a_photo_date():
    def request(endpoint,params,*_):
        assert endpoint==OHM and 'around:2000' in params['data'] and 'out center 20' in params['data']
        return {'elements':[{'id':123,'type':'node','lat':41.9,'lon':12.5,'tags':{'name':'Fixture','start_date':'100','end_date':'200','license':'CC-BY-SA-4.0','source':'Published history'}}]}, {'url':OHM}
    result=OpenGeography(request).historical({'latitude':41.9,'longitude':12.5})
    assert result['features'][0]['license']=='CC-BY-SA-4.0' and result['features'][0]['end_date']=='200'
    assert 'photo_date' not in result and result['feature_count']==1


def test_regional_catalogue_is_scoped_and_does_not_download_restricted_assets():
    calls=[]
    def request(endpoint,params,*_):
        calls.append(endpoint)
        return ({'id':'ch.swisstopo.swissalti3d','license':'proprietary','summaries':{'gsd':[.5,2]}} if endpoint==SWISS else {'features':[{'id':'fixture','bbox':[7.8,46.6,7.9,46.7],'properties':{'datetime':'2024-01-01'}}]}),{'url':endpoint}
    source=OpenGeography(request)
    assert source.regional({'latitude':43.15,'longitude':77.05})['status']=='not_applicable' and not calls
    result=source.regional({'latitude':46.68,'longitude':7.86})
    assert result['collection_license']=='proprietary' and result['assets_downloaded'] is False and len(calls)==2


def mountain(invert=False):
    image=Image.new('RGB',(256,160),(150,190,230));draw=ImageDraw.Draw(image)
    points=[(x,round(65+(1 if invert else -1)*(18*math.sin(x/29)+8*math.sin(x/12)))) for x in range(256)]
    draw.polygon(points+[(255,160),(0,160)],fill=(54,68,55));buffer=io.BytesIO();image.save(buffer,format='PNG');return buffer.getvalue()


def test_skyline_is_reviewable_actual_pixel_trace_with_qualified_shape_comparison():
    first=extract(mountain());second=extract(mountain(True));same=compare(first,first);different=compare(first,second)
    assert first['status']=='complete' and len(first['points'])>=24
    assert same['standardized_shape_rmse']==0 and different['standardized_shape_rmse']>.5
    assert same['original_points']==first['points'] and same['location_verified'] is False
    terrain={'horizon':[{'bearing_deg':i*11.25,'sampled_max_angle_deg':math.sin(i/4)*12} for i in range(32)]}
    result=fit_dem(first,terrain)
    assert result['searched_windows']==96 and result['camera_position_verified'] is False
    assert result['use']=='weak_candidate_screening_only'


def test_flat_or_night_image_does_not_fabricate_a_skyline():
    for color in ((0,0,0),(150,190,230)):
        buffer=io.BytesIO();Image.new('RGB',(128,96),color).save(buffer,format='PNG')
        assert extract(buffer.getvalue())['status']=='unavailable'


def test_russian_summary_preserves_original_without_inventing_place_names():
    original={'description':'A city is lit up at night. There are many buildings and a clock tower.'}
    result=russian_scene(original)
    assert result['description_original']==original['description'] and 'городской вид' in result['description'] and 'башня' in result['description']
    assert 'Москва' not in result['description'] and 'not_verbatim_translation' in result['description_presentation']
    assert russian_scene(result)==result
