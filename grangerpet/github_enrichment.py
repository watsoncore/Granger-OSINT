"""Bounded public GitHub enrichment using the shared HTTP/cache/rate contracts."""
from copy import deepcopy
import time

from . import public_sources


def execute(username, *, limit=5, cancel_event=None, deadline=None, client_factory=None,
            resolver=None, agent_model=''):
    end=min(deadline,time.monotonic()+30) if deadline is not None else time.monotonic()+30
    options={'cancel_event':cancel_event,'deadline':end,'client_factory':client_factory,
             'resolver':resolver,'agent_model':agent_model}
    if type(limit) is not int or not 1<=limit<=20:
        return public_sources.execute('github_profile',username,limit=limit,**options)
    result=public_sources.execute('github_profile',username,limit=1,**options)
    if result['status'] not in ('complete','partial') or not result['results']:
        return result
    result=deepcopy(result)
    attempts=[]

    def collect(source, target, count):
        outcome=public_sources.execute(source,target,limit=count,**options)
        attempts.append({'source':source,'status':outcome['status'],
                         'count':len(outcome['results']),'error_code':outcome.get('error_code')})
        result['results'].extend(outcome['results'])
        if outcome['status'] not in ('complete','empty'):
            result['status']='partial'
            result['limitations'].append(source+': '+str(outcome.get('error_code') or outcome['status']))
        return outcome

    count=min(5,max(1,limit))
    repositories=collect('github_user_repositories',username,count)
    collect('github_organizations',username,min(10,max(1,limit)))
    for repository in repositories['results'][:2]:
        name=repository.get('details',{}).get('full_name')
        if not isinstance(name,str):continue
        if cancel_event and cancel_event.is_set() or time.monotonic()>=end:
            result['status']='partial'
            result['limitations'].append('Расширение остановлено. Уже полученные сведения доступны для добавления.')
            break
        collect('github_languages',name,1)
        collect('github_releases',name,3)
    result['source_attempts']=[{'source':'github_profile','status':'complete','count':1},*attempts]
    result['limitations'].append(
        'Публичная выборка: до пяти репозиториев, десяти организаций и языки/релизы первых двух репозиториев. '
        'Отсутствие записи не доказывает отсутствия других проектов или скрытого членства.')
    return result
