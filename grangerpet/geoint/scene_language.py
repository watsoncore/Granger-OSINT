"""Russian feature summary with the original vision caption retained verbatim.

This is a deterministic vocabulary summary, not a claimed full translation or
an independent pixel analysis. It never adds a place name or a camera position.
"""
from copy import deepcopy
import re

FEATURES=(
    (r'\b(?:city|town|urban)\b','городской вид'),
    (r'\b(?:mountains?|peaks?|ridge|alpine)\b','горы или хребет'),
    (r'\bvalley\b','долина'),(r'\b(?:snow|snowy|snow-covered)\b','снег'),
    (r'\b(?:building|buildings|architecture)\b','здания'),
    (r'\b(?:tower|towers)\b','башня'),(r'\bclock\b','часы'),
    (r'\b(?:church|cathedral)\b','церковь или собор'),(r'\bbridge\b','мост'),
    (r'\b(?:street|road|highway)\b','улица или дорога'),(r'\b(?:cars?|vehicles?)\b','транспорт'),
    (r'\b(?:people|person|pedestrians?)\b','люди'),(r'\b(?:trees?|forest|wooded)\b','деревья'),
    (r'\b(?:grass|grassy|meadow)\b','трава или луг'),(r'\b(?:river|stream)\b','река или ручей'),
    (r'\blake\b','озеро'),(r'\b(?:ocean|sea|beach)\b','море или побережье'),
    (r'\b(?:sign|signs|plaque|inscription)\b','табличка или надпись'),
    (r'\b(?:night|nighttime|night-time)\b','ночное освещение'),(r'\b(?:lights|illuminated|lit up)\b','искусственное освещение'),
    (r'\b(?:blue sky|clear sky)\b','ясное небо'),(r'\b(?:cloud|clouds|cloudy)\b','облака'),
)


def russian_description(value):
    if not isinstance(value,str) or not value.strip():return 'Локальная модель не предоставила описание сцены.'
    if re.search(r'[А-Яа-яЁё]',value):return value[:4000]
    features=[label for pattern,label in FEATURES if re.search(pattern,value,re.I)]
    return ('По описанию локальной модели: '+', '.join(features)+'. Возможны ошибки распознавания.' if features else
        'Локальная модель сформировала описание; для этой сцены русский словарь признаков недостаточен. Оригинал сохранён в доказательстве.')


def russian_scene(value):
    if not isinstance(value,dict):return {}
    output=deepcopy(value);original=value.get('description_original') or value.get('description','')
    output['description_original']=original
    output['description']=russian_description(original)
    output['description_presentation']='russian_feature_summary_not_verbatim_translation'
    return output
