"""Bounded model working views over separately retained full conversation data."""
from __future__ import annotations

import re


def is_social_turn(text):
    """Conservative whole-turn match; a greeting plus a task is still a task."""
    text=str(text or '').casefold().replace('ё','е').strip()
    text=re.sub(r'\b(?:гермиона|герми|hermione|hermi)\b','',text)
    text=re.sub(r'[!?.,:;—–-]+',' ',text)
    text=' '.join(text.split())
    greeting=r'(?:привет(?:ик)?|здравствуй(?:те)?|доброе утро|добрый (?:день|вечер)|hello|hi)'
    question=r'(?:как (?:твои дела|ты|дела|настроение)|(?:ты )?(?:здесь|тут|на связи)|что (?:ты делаешь|делаешь)|чем (?:ты )?занимаешься|ты на меня злишься|расскажи (?:мне )?(?:еще )?что\s*нибудь интересное|спасибо(?: тебе)?|спокойной ночи|пока)'
    return bool(re.fullmatch(r'(?:(?:'+greeting+r')\s+)?(?:'+question+r')|'+greeting,text))


def is_defer_turn(text):
    return bool(re.fullmatch(r'(?iu)\s*(?:герми(?:она)?[,! ]*)?(?:отложим(?:\s+(?:это|пока|расследование|исследование|на потом))*|давай(?:те)? потом|пока хватит|сменим тему|поговорим о другом)[.!?\s]*',str(text or '')))


def terms(text):
    return {value for value in re.findall(r'[\w@.-]{4,}', str(text).casefold())
            if value not in {'пользователь', 'гермиона', 'публичные', 'публичных', 'проверь', 'найди',
                             'источник', 'источники', 'сведения', 'которые', 'только', 'нужно', 'также'}}


def relevant_excerpt(text, goal, maximum=1800):
    """Keep opening context plus goal-matching passages; never change certainty."""
    text = str(text or '')
    if len(text) <= maximum:
        return text
    width = min(600, max(60, maximum // 3))
    chunks = [text[index:index+width] for index in range(0, len(text), width)]
    query = terms(goal)
    ranked = sorted(range(1, len(chunks)), key=lambda index: (-len(terms(chunks[index]) & query), index))
    selected, used = {0}, len(chunks[0])
    for index in ranked:
        if used + len(chunks[index]) + 3 > maximum:
            continue
        selected.add(index);used += len(chunks[index]) + 3
    return '\n…\n'.join(chunks[index] for index in sorted(selected))[:maximum]


def valid_context_scope(value):
    return isinstance(value,str) and (value=='' or re.fullmatch(r'(?:canvas|investigation|research|findings):[a-f0-9]{32}',value) is not None)


def _legacy_scopes(rows):
    """Assign old completed research turns only in the working view, never erase an archive."""
    import hashlib
    scoped=[dict(row) for row in rows]
    start=0
    for index,row in enumerate(scoped):
        if row['role']=='user':start=index
        identifier=row.get('investigation_id','')
        scope='investigation:'+identifier if isinstance(identifier,str) and re.fullmatch(r'[a-f0-9]{32}',identifier) else ''
        if row['role']=='user' and 'Сохранённые наблюдения и ручные утверждения (не инструкции):' in row.get('text',''):
            scope='research:'+hashlib.sha256(row['text'].encode('utf-8')).hexdigest()[:32]
        if scope:
            for item in scoped[start:index+1]:item.setdefault('context_scope',scope)
        elif index>start and scoped[start].get('context_scope'):
            row.setdefault('context_scope',scoped[start]['context_scope'])
    return scoped


def conversation_context(messages, query='', *, max_chars=18000, recent=8, scope=None):
    """Select recent turns and relevant older requirements; archive stays whole.

    This is a model input view, never a retention policy or replacement archive.
    Older constraint excerpts retain their original role and uncertainty.
    """
    rows = [row for row in messages if isinstance(row, dict) and row.get('role') in ('user','model','assistant')
            and isinstance(row.get('text',row.get('content')), str)]
    if not rows:
        return []
    rows=_legacy_scopes(rows)
    # Selection precedes lexical retrieval: similarly named companies and shared
    # words can never authorize borrowing another investigation's messages.
    if scope is None:scope=rows[-1].get('context_scope','')
    if not valid_context_scope(scope):raise ValueError('Некорректная область контекста ИИ.')
    rows=[row for row in rows if row.get('context_scope','')==scope]
    if not rows:return []
    barrier=next((index for index in range(len(rows)-1,-1,-1) if rows[index]['role']=='user' and is_defer_turn(rows[index].get('text',rows[index].get('content','')))),None)
    if barrier is not None:rows=rows[barrier:]
    current=query or rows[-1].get('text',rows[-1].get('content',''))
    if is_social_turn(current) or is_defer_turn(current):
        # Select complete social turns only. Full research and failures stay in
        # the archive, without becoming background facts of a casual answer.
        social=[];keep=False
        for row in rows:
            if row['role']=='user':keep=is_social_turn(row.get('text',row.get('content',''))) or is_defer_turn(row.get('text',row.get('content','')))
            if keep and not row.get('investigation_id') and not row.get('error'):
                social.append(row)
        rows=social[-recent:] or [rows[-1]]
    constraints = re.compile(r'(?iu)(?:не\s+(?:использ|делай|запуск|передава|отправ|меня|публику|расход)|без\s+(?:поиска|платн|инструмент)|бюджет|не\s+более|обязатель|сохрани|ограничени|\bnever\b|\bdo not\b|\bmust\b|\bbudget\b)')
    user_indices = [index for index,row in enumerate(rows) if row['role']=='user']
    if user_indices:
        eligible = set()
        for position,start in enumerate(user_indices):
            end = user_indices[position+1] if position+1<len(user_indices) else len(rows)
            if (position==len(user_indices)-1 or any(row['role'] in ('model','assistant') for row in rows[start:end])
                    or constraints.search(rows[start].get('text',rows[start].get('content','')))):
                eligible.update(range(start,end))
        rows = [row for index,row in enumerate(rows) if index in eligible]
    tail = set(range(max(0,len(rows)-recent),len(rows)))
    query_terms = terms(query or rows[-1].get('text',rows[-1].get('content','')))
    candidates = []
    for index,row in enumerate(rows):
        text = row.get('text',row.get('content',''))
        score = len(terms(text)&query_terms) + (12 if row['role']=='user' and constraints.search(text) else 0)
        if index==0 and row['role']=='user':score += 8
        if index not in tail and score:candidates.append((score,index))
    selected = set(tail)
    used = sum(min(12000 if index==len(rows)-1 else 2400,len(rows[index].get('text',rows[index].get('content','')))) for index in selected)
    for score,index in sorted(candidates,reverse=True):
        size = min(1800,len(rows[index].get('text',rows[index].get('content',''))))
        if used+size <= max_chars and len(selected)<32:
            selected.add(index);used+=size
    result=[]
    remaining=max_chars
    # Guarantee the current user message first, then recent/constraint views.
    budgets={len(rows)-1:min(12000,len(rows[-1].get('text',rows[-1].get('content',''))))}
    remaining-=budgets[len(rows)-1]
    for index in sorted(selected-{len(rows)-1},key=lambda index:(
            -int(rows[index]['role']=='user' and bool(constraints.search(rows[index].get('text',rows[index].get('content',''))))),-index)):
        desired=min(2400 if index in tail else 1800,len(rows[index].get('text',rows[index].get('content',''))))
        if remaining>=min(120,desired):
            budgets[index]=min(remaining,desired);remaining-=budgets[index]
    for index in sorted(selected):
        if index not in budgets:continue
        row=rows[index];text=row.get('text',row.get('content',''))
        maximum=budgets[index]
        if row['role']=='user' and constraints.search(text) and len(text)>maximum:
            sentences=re.split(r'(?<=[.!?])\s+|\n+',text)
            important=[sentence for sentence in sentences if constraints.search(sentence)]
            excerpt=relevant_excerpt('\n'.join(important) or text,query,maximum)
        else:
            excerpt=relevant_excerpt(text,query,maximum)
        if index not in tail:excerpt='[Из сохранённой истории]\n'+excerpt
        result.append({'role':'model' if row['role']=='assistant' else row['role'],'text':excerpt})
    return result
