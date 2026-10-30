"""Deterministic analytics over observed Gansar transfers, never a collector.

Amounts are Decimal, scoped by chain AND asset contract. Coverage is the input
sample, not all chain history. Duplicate provider observations are not payments.
This module also runs in the isolated vendor interpreter without Qt.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import base64
import binascii
import hashlib
import re

EVM = frozenset(('eth', 'ethereum', 'bsc', 'polygon', 'arbitrum', 'optimism', 'avalanche'))
NATIVE = {'ton':'TON','btc':'BTC','bitcoin':'BTC','eth':'ETH','ethereum':'ETH','bsc':'BNB',
    'polygon':'POL','arbitrum':'ETH','optimism':'ETH','avalanche':'AVAX','tron':'TRX',
    'trx':'TRX','solana':'SOL','sol':'SOL','dogecoin':'DOGE','doge':'DOGE'}


def canonical_address(chain, address):
    value = str(address or '').strip()
    if chain.lower() == 'ton':
        if match := re.fullmatch(r'(-?\d{1,10}):([0-9a-fA-F]{64})', value):
            workchain = int(match[1])
            if -(2**31) <= workchain < 2**31:
                return str(workchain)+':'+match[2].lower()
        try:
            raw = base64.b64decode(value.translate(str.maketrans('-_', '+/')), validate=True)
            if (len(raw) == 36 and raw[0] & 0x7f in (0x11, 0x51)
                    and raw[34:] == binascii.crc_hqx(raw[:34], 0).to_bytes(2, 'big')):
                # Test-only addresses retain their domain; never merge mainnet.
                return ('test:' if raw[0] & 0x80 else '')+str(int.from_bytes(raw[1:2], 'big', signed=True))+':'+raw[2:34].hex()
        except (ValueError, binascii.Error):
            pass
    return value.lower() if chain.lower() in EVM else value


def decimal_amount(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 and (not number or -60 <= number.adjusted() <= 60) else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def asset_identity(row,chain='',scope=''):
    """A ticker is not a contract. Unidentified token amounts stay separate."""
    network=str(row.get('chain') or chain).lower()
    semantics=row.get('event_semantics') or row.get('raw') or {}
    if not isinstance(semantics,dict):semantics={}
    asset=str(row.get('asset') or 'unknown')
    contract=row.get('asset_id') or row.get('token_contract') or semantics.get('token_contract') or row.get('contract')
    if not contract and network=='ton' and asset.upper().startswith(('JETTON:','NFT:')):
        possible=canonical_address('ton',asset.split(':',1)[1])
        if re.fullmatch(r'(?:test:)?-?\d+:[a-f0-9]{64}',possible):contract=possible
    if isinstance(contract,str) and contract.strip():
        return network+'|'+canonical_address(network,contract),contract,'contract_reported'
    if asset.upper()==NATIVE.get(network):return network+'|'+asset.upper(),None,'native_asset'
    if asset=='unknown' and decimal_amount(row.get('amount_decimal',row.get('amount'))) is None:
        return network+'|unknown',None,'asset_unknown'
    reference=row.get('event_id') or row.get('tx_hash') or row.get('evidence_id') or row.get('id') or scope
    fingerprint=hashlib.sha256(str(reference).encode()).hexdigest()[:16]
    return network+'|unidentified|'+asset+'|'+fingerprint,None,'contract_unknown_not_aggregated'


def _date(value):
    try:
        if type(value) in (int, float):
            value = datetime.fromtimestamp(value / 1000 if value > 1e12 else value, timezone.utc)
        elif isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            return None
        if value.tzinfo is None:
            return None  # Do not invent a source timezone.
        return value.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def analyze_transactions(transactions, target, chain=''):
    seen, transfers, excluded = set(), [], Counter()
    for row in transactions:
        if not isinstance(row, dict):
            excluded['invalid'] += 1
            continue
        network = str(row.get('chain') or chain).lower()
        first = canonical_address(network, row.get('from_address'))
        second = canonical_address(network, row.get('to_address'))
        owner = canonical_address(network, target)
        semantics = row.get('event_semantics') or row.get('raw') or {}
        if not isinstance(semantics, dict):
            semantics = {}
        asset = str(row.get('asset') or 'unknown')
        asset_key,contract,identity_status=asset_identity(row,network,scope=len(transfers))
        amount = decimal_amount(row.get('amount_decimal', row.get('amount')))
        stamp = _date(row.get('timestamp'))
        event = row.get('event_id') or semantics.get('event_id')
        # An action index distinguishes token actions sharing one tx hash.
        reference = event or (str(row.get('tx_hash'))+'|'+str(semantics.get('action_index', '')) if row.get('tx_hash') else row.get('evidence_id') or row.get('id'))
        key = (network, str(reference), first, second, asset_key, amount)
        if reference and key in seen:
            excluded['duplicate_observations'] += 1
            continue
        if reference:
            seen.add(key)
        failed = row.get('success') is False or row.get('status') in ('failed', 'reverted', 'aborted')
        if failed:
            excluded['failed_events'] += 1
            continue
        direction = ('self' if first == second == owner else 'outgoing' if first == owner and second
                     else 'incoming' if second == owner and first else 'unresolved')
        counterparty = second if direction == 'outgoing' else first if direction == 'incoming' else ''
        transfers.append({'chain': network, 'from_address': first, 'to_address': second,
            'original_from_address': row.get('from_address'), 'original_to_address': row.get('to_address'),
            'direction': direction, 'counterparty': counterparty, 'asset': asset, 'asset_key': asset_key,
            'contract': contract, 'asset_identity_status':identity_status,'amount': amount, 'timestamp': stamp, 'event_id': event,
            'tx_hash': row.get('tx_hash'), 'source': row.get('source'), 'source_url': row.get('url') or '',
            'evidence_id': row.get('evidence_id')})
    assets, peers, periods,repeat_groups,hours = {}, {}, Counter(),{},Counter()
    directions = Counter(row['direction'] for row in transfers)
    for row in transfers:
        key = row['asset_key']
        group = assets.setdefault(key, {'chain': row['chain'], 'asset': row['asset'], 'contract': row['contract'],
            'asset_key': key,'identity_status':row['asset_identity_status'], 'incoming': Decimal(0), 'outgoing': Decimal(0), 'known_amounts': 0,
            'amount_coverage':{direction:{'known_events':0,'unknown_events':0} for direction in ('incoming','outgoing','self','unresolved')},
            'unknown_amounts': 0, 'event_count': 0})
        group['event_count'] += 1
        group['amount_coverage'][row['direction']]['unknown_events' if row['amount'] is None else 'known_events']+=1
        if row['amount'] is None:
            group['unknown_amounts'] += 1
        else:
            group['known_amounts'] += 1
            if row['direction'] in ('incoming', 'outgoing'):
                with localcontext() as context:
                    context.prec = 160
                    group[row['direction']] += row['amount']
        if row['timestamp']:
            periods[row['timestamp'][:10]] += 1
            hours[row['timestamp'][:13]+':00:00+00:00']+=1
        if row['counterparty']:
            peer = peers.setdefault(row['chain']+'|'+row['counterparty'], {'chain': row['chain'], 'address': row['counterparty'],
                'event_count': 0, 'incoming': 0, 'outgoing': 0, 'asset_keys': set(), 'first_seen': None,
                'last_seen': None, 'evidence_ids': [], 'source_urls': [],'volumes_by_asset':{}})
            peer['event_count'] += 1
            peer[row['direction']] += 1
            peer['asset_keys'].add(key)
            volume=peer['volumes_by_asset'].setdefault(key,{'asset':row['asset'],'contract':row['contract'],
                'incoming':Decimal(0),'outgoing':Decimal(0),'unknown_amounts':0,'known_incoming':0,'known_outgoing':0,
                'incoming_events':0,'outgoing_events':0})
            volume[row['direction']+'_events']+=1
            if row['amount'] is None:volume['unknown_amounts']+=1
            else:
                with localcontext() as context:
                    context.prec=160;volume[row['direction']]+=row['amount']
                volume['known_'+row['direction']]+=1
            if row['timestamp']:
                peer['first_seen'] = min(peer['first_seen'] or row['timestamp'], row['timestamp'])
                peer['last_seen'] = max(peer['last_seen'] or row['timestamp'], row['timestamp'])
            for field in ('evidence_id', 'source_url'):
                values = peer['evidence_ids' if field == 'evidence_id' else 'source_urls']
                if row[field] and row[field] not in values:
                    values.append(row[field])
            if row['amount'] is not None:
                repeat_groups.setdefault((row['chain'],row['counterparty'],row['direction'],key,row['amount']),[]).append(row)
    largest = {}
    for key in assets:
        # Amounts of different assets are deliberately never compared or added.
        candidates = sorted((row for row in transfers if row['asset_key'] == key and row['amount'] is not None
                             and row['direction'] in ('incoming', 'outgoing')), key=lambda row: row['amount'], reverse=True)
        largest[key] = [{**row, 'amount': format(row['amount'], 'f')} for row in candidates[:10]]
    for group in assets.values():
        for field in ('incoming', 'outgoing'):
            coverage=group['amount_coverage'][field]
            group[field] = format(group[field], 'f') if coverage['known_events'] or group['known_amounts'] and not coverage['unknown_events'] else None
        group['volumes_partial']=any(item['unknown_events'] for direction,item in group['amount_coverage'].items() if direction in ('incoming','outgoing'))
    for peer in peers.values():
        peer['asset_keys'] = sorted(peer['asset_keys'])
        for volume in peer['volumes_by_asset'].values():
            for direction in ('incoming','outgoing'):
                volume[direction]=format(volume[direction],'f') if volume['known_'+direction] or not volume[direction+'_events'] else None
    patterns=[]
    for (network,peer,direction,key,amount),events in repeat_groups.items():
        if len(events)<3:continue
        times=sorted(row['timestamp'] for row in events if row['timestamp'])
        intervals=sorted((datetime.fromisoformat(second)-datetime.fromisoformat(first)).total_seconds() for first,second in zip(times,times[1:]))
        middle=len(intervals)//2
        median=(intervals[middle] if len(intervals)%2 else (intervals[middle-1]+intervals[middle])/2) if intervals else None
        patterns.append({'kind':'repeated_exact_amount','criteria':'at_least_3_distinct_events_same_peer_direction_asset_and_exact_amount',
            'chain':network,'counterparty':peer,'direction':direction,'asset_key':key,'amount':format(amount,'f'),
            'count':len(events),'first_seen':times[0] if times else None,'last_seen':times[-1] if times else None,
            'median_interval_seconds':median,'dated_events':len(times),'evidence_ids':[row['evidence_id'] for row in events if row['evidence_id']],
            'interpretation':'Повторяется наблюдаемая сумма; экономическая причина и намерения не установлены.'})
    dates = sorted(row['timestamp'] for row in transfers if row['timestamp'])
    return {'schema_version': 1, 'target_address': target, 'canonical_target': canonical_address(chain, target),
        'coverage': 'observed_sample_only', 'input_observations': len(transactions), 'unique_events': len(transfers),
        'excluded': dict(excluded), 'directions': dict(directions), 'unique_counterparties': len(peers),
        'assets': list(assets.values()), 'counterparties': sorted(peers.values(), key=lambda row: (-row['event_count'], row['address'])),
        'largest_transfers_by_asset': largest, 'activity_by_day_utc': dict(sorted(periods.items())),
        'first_seen': dates[0] if dates else None, 'last_seen': dates[-1] if dates else None,
        'activity_by_hour_utc':dict(sorted(hours.items())),
        'repeated_patterns':sorted(patterns,key=lambda row:-row['count']),
        'repeated_patterns_total':len(patterns),
        'undated_events': sum(not row['timestamp'] for row in transfers),
        'limitations': ['Анализ охватывает полученную выборку, а не полную историю сети.',
            'Операции и сервисные метки не устанавливают личность или общего владельца.',
            'Суммы разных контрактов/активов не складываются; неизвестные суммы не считаются нулевыми.']}
