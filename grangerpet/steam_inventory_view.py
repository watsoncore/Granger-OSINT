"""Lossless item projection and explicitly partial public Market valuation."""
from collections import Counter
from decimal import Decimal,InvalidOperation
from copy import deepcopy


def inventories(records,*,include_items=True):
    from .agent_evidence import current_observation
    groups={}
    for raw in records:
        if not isinstance(raw,dict):continue
        row=current_observation(raw);data=row.get('details',{})
        if not isinstance(data,dict) or row.get('type') not in ('steam_inventory','steam_item'):continue
        steamid=data.get('steamid64');appid=data.get('appid');context=data.get('contextid')
        if not isinstance(steamid,str) or type(appid) is not int or not isinstance(context,str):continue
        key=(steamid,appid,context)
        view=groups.setdefault(key,{'steamid64':steamid,'appid':appid,'contextid':context,
            'canonical_url':data.get('canonical_url'),'items':{},'page_batches':[],'source_failures':[]})
        if row.get('type')=='steam_inventory':
            coverage=data.get('coverage')
            if isinstance(coverage,dict) and coverage not in view['page_batches']:view['page_batches'].append(deepcopy(coverage))
            failures=data.get('source_failures')
            if isinstance(failures,list):view['source_failures'].extend(deepcopy([value for value in failures if isinstance(value,dict)]))
        elif isinstance(data.get('assetid'),str):
            view['items'][data['assetid']]={**deepcopy(data),'evidence_id':row.get('evidence_id'),'source_url':row.get('url')}
    result=[]
    for view in groups.values():
        items=list(view['items'].values());batches=view.pop('page_batches');totals={row['reported_total'] for row in batches if type(row.get('reported_total')) is int}
        reported=next(iter(totals)) if len(totals)==1 else None
        starts=any(not row.get('starts_at_cursor') for row in batches)
        exhausted=bool(batches and batches[-1].get('stop_reason')=='exhausted')
        subtotal=Decimal(0);priced=0;units=0;quote_times=[]
        for item in items:
            try:quantity=int(item.get('amount','1'))
            except (ValueError,TypeError):quantity=1
            units+=quantity
            price=item.get('price');price=price if isinstance(price,dict) else {}
            if price.get('currency')!='USD' or not isinstance(price.get('amount_decimal'),str):continue
            try:amount=Decimal(price['amount_decimal'])
            except InvalidOperation:continue
            if not amount.is_finite() or amount<0:continue
            subtotal+=amount*quantity;priced+=1
            if price.get('observed_at'):quote_times.append(price['observed_at'])
        view.update(observed_assets=len(items),observed_units=units,reported_total=reported,
            coverage_status='complete' if starts and exhausted and reported==len(items) and len(totals)==1 else 'partial',
            coverage_reason='server_exhausted_before_reported_count' if exhausted and reported is not None and reported!=len(items) else
                'reported_total_changed' if len(totals)>1 else 'cursor_exhausted' if exhausted else 'pagination_incomplete',
            next_cursor=batches[-1].get('next_cursor') if batches else None,pages=[page for batch in batches for page in batch.get('pages',[])],
            categories=dict(Counter(item.get('category') or 'Не классифицировано' for item in items)),
            valuation={'currency':'USD','priced_assets':priced,'unpriced_assets':len(items)-priced,
                'observed_subtotal_decimal':str(subtotal) if priced else None,
                'quote_first_observed_at':min(quote_times) if quote_times else None,'quote_last_observed_at':max(quote_times) if quote_times else None,
                'coverage':'partial' if priced<len(items) else 'observed_items_only',
                'method':'Сумма известных lowest Market quotes × количество; не полная стоимость инвентаря, не оценка редких float/pattern/наклеек.'})
        view['items']=items if include_items else []
        result.append(view)
    return result


def model_summaries(records):
    result=[]
    for view in inventories(records):
        items=view.pop('items')
        view['sample_items']=[{key:item.get(key) for key in ('assetid','name','category','rarity','exterior','float_value','pattern_template','evidence_id')}
                              for item in items[:8]]
        view['pages_count']=len(view.pop('pages'))
        result.append(view)
    return result
