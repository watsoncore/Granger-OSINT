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
import re

EVM = frozenset(('eth', 'ethereum', 'bsc', 'polygon', 'arbitrum', 'optimism', 'avalanche'))


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
        contract = row.get('asset_id') or row.get('token_contract') or semantics.get('token_contract') or row.get('contract')
        asset_key = network+'|'+(canonical_address(network, contract) if contract else asset)
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
            'contract': contract, 'amount': amount, 'timestamp': stamp, 'event_id': event,
            'tx_hash': row.get('tx_hash'), 'source': row.get('source'), 'source_url': row.get('url') or '',
            'evidence_id': row.get('evidence_id')})
    assets, peers, periods = {}, {}, Counter()
    directions = Counter(row['direction'] for row in transfers)
    for row in transfers:
        key = row['asset_key']
        group = assets.setdefault(key, {'chain': row['chain'], 'asset': row['asset'], 'contract': row['contract'],
            'asset_key': key, 'incoming': Decimal(0), 'outgoing': Decimal(0), 'known_amounts': 0,
            'unknown_amounts': 0, 'event_count': 0})
        group['event_count'] += 1
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
        if row['counterparty']:
            peer = peers.setdefault(row['chain']+'|'+row['counterparty'], {'chain': row['chain'], 'address': row['counterparty'],
                'event_count': 0, 'incoming': 0, 'outgoing': 0, 'asset_keys': set(), 'first_seen': None,
                'last_seen': None, 'evidence_ids': [], 'source_urls': []})
            peer['event_count'] += 1
            peer[row['direction']] += 1
            peer['asset_keys'].add(key)
            if row['timestamp']:
                peer['first_seen'] = min(peer['first_seen'] or row['timestamp'], row['timestamp'])
                peer['last_seen'] = max(peer['last_seen'] or row['timestamp'], row['timestamp'])
            for field in ('evidence_id', 'source_url'):
                values = peer['evidence_ids' if field == 'evidence_id' else 'source_urls']
                if row[field] and row[field] not in values:
                    values.append(row[field])
    largest = {}
    for key in assets:
        # Amounts of different assets are deliberately never compared or added.
        candidates = sorted((row for row in transfers if row['asset_key'] == key and row['amount'] is not None
                             and row['direction'] in ('incoming', 'outgoing')), key=lambda row: row['amount'], reverse=True)
        largest[key] = [{**row, 'amount': format(row['amount'], 'f')} for row in candidates[:10]]
    for group in assets.values():
        for field in ('incoming', 'outgoing'):
            group[field] = format(group[field], 'f') if group['known_amounts'] else None
    for peer in peers.values():
        peer['asset_keys'] = sorted(peer['asset_keys'])
    dates = sorted(row['timestamp'] for row in transfers if row['timestamp'])
    return {'schema_version': 1, 'target_address': target, 'canonical_target': canonical_address(chain, target),
        'coverage': 'observed_sample_only', 'input_observations': len(transactions), 'unique_events': len(transfers),
        'excluded': dict(excluded), 'directions': dict(directions), 'unique_counterparties': len(peers),
        'assets': list(assets.values()), 'counterparties': sorted(peers.values(), key=lambda row: (-row['event_count'], row['address'])),
        'largest_transfers_by_asset': largest, 'activity_by_day_utc': dict(sorted(periods.items())),
        'first_seen': dates[0] if dates else None, 'last_seen': dates[-1] if dates else None,
        'undated_events': sum(not row['timestamp'] for row in transfers),
        'limitations': ['Анализ охватывает полученную выборку, а не полную историю сети.',
            'Операции и сервисные метки не устанавливают личность или общего владельца.',
            'Суммы разных контрактов/активов не складываются; неизвестные суммы не считаются нулевыми.']}
