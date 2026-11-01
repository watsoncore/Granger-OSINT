"""Explainable reference selection. These scores are not location probabilities."""
from copy import deepcopy
import math
import re

CLASSES={
    'tower':r'\b(?:tower|bell|clock|башн\w*|колокольн\w*|часов\w*)\b',
    'architecture':r'\b(?:building|architecture|cathedral|church|castle|kremlin|facade|palace|собор\w*|церк\w*|кремл\w*|здани\w*|дворец\w*|фасад\w*)\b',
    'street':r'\b(?:street|road|avenue|square|улиц\w*|дорог\w*|площад\w*)\b',
    'mountain':r'\b(?:mountain|alpine|peak|ridge|гор[аы]|горн\w*|вершин\w*)\b',
    'water':r'\b(?:river|lake|sea|ocean|harbour|waterfront|рек[аи]|озер\w*|мор[ея]|набережн\w*)\b',
    'detail':r'\b(?:plaque|sign|inscription|memorial|tablet|таблич\w*|надпис\w*|мемориальн\w*|вывеск\w*)\b',
}


def scene_text(records):
    return ' '.join(str((row.get('details') or {}).get('description') or '') for row in records
        if (row.get('details') or {}).get('tool') in ('image_understand','visual_geoint','image_ocr'))[:6000]


def rank_reference(reference,scene,candidate=None):
    reference=deepcopy(reference);candidate=candidate or {}
    text=' '.join(str(reference.get(key) or '') for key in ('title','description'))
    observed={key for key,pattern in CLASSES.items() if re.search(pattern,scene,re.I)}
    shown={key for key,pattern in CLASSES.items() if re.search(pattern,text,re.I)}
    shared=observed&shown;score=3.*len(shared-{'detail'});reasons=[]
    if shared:reasons.append('Общий тип сцены: '+', '.join(sorted(shared)))
    if 'detail' in shown and 'detail' not in observed:
        score-=5.;reasons.append('Крупная табличка/надпись вместо исходного вида: штраф за другой объект')
    principal=observed-{'detail'};candidate_principal=shown-{'detail'}
    if principal and candidate_principal and not principal&candidate_principal:
        score-=2.;reasons.append('Типы сцены расходятся')
    region_words=set(re.findall(r'[\w-]{5,}',str(candidate.get('region','')).casefold()))
    named_overlap=region_words&set(re.findall(r'[\w-]{5,}',text.casefold()))
    if named_overlap:score+=min(.6,.15*len(named_overlap));reasons.append('Совпало название области гипотезы; это не подтверждение')
    distance=reference.get('distance_m',reference.get('distance_to_candidate_m'))
    if type(distance) in (int,float) and math.isfinite(distance) and distance>=0:
        score+=.1/(1+distance/1000)
        reasons.append('Расстояние используется только как слабый дополнительный признак')
    comparison=reference.get('comparison') or {}
    coverage=comparison.get('spatial_coverage') or []
    if len(coverage)==2 and all(type(x) in (int,float) and math.isfinite(x) for x in coverage):
        geometry=comparison.get('geometry') or {}
        if comparison.get('support_kind')=='distributed_feature_matches_not_location_proof':
            score+=2*min(coverage);reasons.append('Локальные совпадения распределены по двум кадрам')
        elif comparison.get('match_count',0):
            score-=.5;reasons.append('Совпадения локализованы; окна/текстуры могут повторяться')
    reference['selection']={'score':round(score,4),'score_calibrated':False,'geolocation_verified':False,
        'basis':reasons or ['Недостаточно семантических признаков; нужна проверка пикселей'],
        'observed_scene_types':sorted(observed),'reference_scene_types':sorted(shown),
        'interpretation':'Приоритет просмотра, не вероятность географического совпадения.'}
    return reference


def rank_references(references,scene,candidate=None):
    unique={}
    for row in references:
        key=row.get('source_url') or row.get('image_url')
        if key and key not in unique:unique[key]=rank_reference(row,scene,candidate)
    return sorted(unique.values(),key=lambda row:-row['selection']['score'])
