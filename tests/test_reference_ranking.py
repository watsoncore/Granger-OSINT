"""Ranking fixture regression: a nearby sign must not beat a scene view."""
from grangerpet.geoint.reference_ranking import rank_references
from grangerpet.geoint.research import ResearchSources


def test_scene_relevance_dominates_distance_and_does_not_confirm_location():
    values=[{'title':'Kremlin memorial plaque inscription','source_url':'https://example.org/sign','distance_m':1},
            {'title':'Kremlin clock tower and cathedral architecture','source_url':'https://example.org/tower','distance_m':900}]
    ranked=rank_references(values,'A clock tower and a cathedral building with a street.')
    assert ranked[0]['source_url'].endswith('/tower')
    assert ranked[1]['selection']['score']<0
    assert not ranked[0]['selection']['geolocation_verified']
    assert not ranked[0]['selection']['score_calibrated']
    assert 'selection' not in values[0]


def test_repeated_texture_matches_are_not_unique_landmark_confirmation():
    ranked=rank_references([{'source_url':'https://example.org/facade','title':'A building',
        'comparison':{'spatial_coverage':[.01,.02],'match_count':100,'support_kind':'localized_or_insufficient_features'}}],'A building')
    assert any('повторяться' in text for text in ranked[0]['selection']['basis'])


def test_commons_combines_semantic_search_with_nearby_photos():
    class Maps:
        commons_endpoint='https://commons.wikimedia.org/w/api.php'
        def __init__(self):self.calls=[]
        def execute(self,*args):return {'media':[{'page_id':1,'distance_m':1}]}
        def _request(self,endpoint,params,cancel):
            self.calls.append(params)
            if params.get('list')=='search':return {'query':{'search':[{'pageid':2}]}},False
            return {'query':{'pages':{str(i):{'pageid':i,'title':title,'imageinfo':[{'mime':'image/jpeg','url':'https://example.org/'+str(i)+'.jpg','descriptionurl':'https://example.org/'+str(i)}]} for i,title in [(1,'A memorial plaque'),(2,'A clock tower')]}}},False
    maps=Maps();sources=ResearchSources(maps=maps)
    result=sources.commons({'latitude':55.,'longitude':37.,'observed_scene':'A clock tower'},[{'query':'Kremlin clock tower'}],2,None)
    assert len(maps.calls)==2 and maps.calls[1]['pageids']=='1|2'
    assert result[0]['page_id']==2 and result[1]['page_id']==1


def test_wikidata_place_contract_rejects_non_earth_missing_and_remote_coordinates():
    from grangerpet.geoint.wikidata import lookup
    class Maps:
        def _request(self,endpoint,params,cancel):
            if params['action']=='wbsearchentities':return {'search':[{'id':'Q1'},{'id':'Q2'},{'id':'Q3'}]},False
            return {'entities':{key:{'labels':{'en':{'value':key}},'claims':{'P625':[{'mainsnak':{'datavalue':{'value':point}}}]}} for key,point in [
                ('Q1',{'latitude':55.75,'longitude':37.62,'globe':'http://www.wikidata.org/entity/Q2'}),
                ('Q2',{'latitude':55.75,'longitude':37.62,'globe':'http://www.wikidata.org/entity/Q111'}),
                ('Q3',{'latitude':0,'longitude':0,'globe':'http://www.wikidata.org/entity/Q2'})]}},False
    rows=lookup({'query':'Kremlin','latitude':55.75,'longitude':37.62},Maps())
    assert len(rows)==1 and rows[0]['entity_id']=='Q1'
    assert rows[0]['data_license']=='CC0-1.0' and not rows[0]['reference_location_verified']
