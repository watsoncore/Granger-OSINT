"""User-facing typed inputs; format validation never asserts a real registration."""
import re
from .engine.router import _url

JURISDICTIONS={
    'KZ':{'label':'Казахстан','identifiers':{'name':'Название','bin':'БИН','lei':'LEI','website':'Официальный сайт'}},
    'RU':{'label':'Россия','identifiers':{'name':'Название','inn':'ИНН юридического лица','ogrn':'ОГРН','lei':'LEI','website':'Официальный сайт'}},
    'GB':{'label':'Великобритания','identifiers':{'name':'Название','company_number':'Номер компании','lei':'LEI','website':'Официальный сайт'}},
    'US':{'label':'США','identifiers':{'name':'Название','cik':'CIK','registration_number':'Регистрационный номер','lei':'LEI','website':'Официальный сайт'}},
    'OTHER':{'label':'Другая / не указана','identifiers':{'name':'Название','registration_number':'Регистрационный номер','lei':'LEI','website':'Официальный сайт'}},
}
PATTERNS={'bin':r'\d{12}','inn':r'\d{10}','ogrn':r'\d{13}',
          'lei':r'[A-Z0-9]{18}\d{2}','company_number':r'[A-Z0-9]{8}','cik':r'\d{1,10}',
          'registration_number':r'[^\x00-\x1f]{1,80}'}


def organization(values):
    if not isinstance(values,dict):raise ValueError('Заполните сведения о компании.')
    country=values.get('jurisdiction','OTHER')
    if country not in JURISDICTIONS:raise ValueError('Выберите юрисдикцию компании.')
    method=values.get('identifier_type','name')
    if method not in JURISDICTIONS[country]['identifiers']:raise ValueError('Этот идентификатор не относится к выбранной юрисдикции.')
    value=values.get('identifier','')
    if not isinstance(value,str):raise ValueError('Введите название или регистрационный идентификатор.')
    value=value.strip()
    if not value or len(value)>300 or any(ord(char)<32 for char in value):raise ValueError('Введите название или регистрационный идентификатор.')
    if method in PATTERNS:
        value=value.upper()
        if not re.fullmatch(PATTERNS[method],value):raise ValueError('Проверьте формат поля «'+JURISDICTIONS[country]['identifiers'][method]+'».')
    if method=='website':value=_url(value)[2]
    legal_name=values.get('legal_name','')
    if not isinstance(legal_name,str) or len(legal_name)>300:raise ValueError('Название компании: до 300 символов.')
    return {'jurisdiction':country,'identifier_type':method,'identifier':value,
            'legal_name':legal_name.strip() or (value if method=='name' else ''),
            'value':value,'registration_verified':False,
            **({'url':value} if method=='website' else {}),
            **({'registration_number':value} if method not in ('name','website') else {})}


def organization_catalog():
    return [{'id':key,**value} for key,value in JURISDICTIONS.items()]
