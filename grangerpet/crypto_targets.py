"""Lightweight Gansar input contracts; no Qt, vendor imports or network requests.

An address format is not evidence that an account exists or that a person owns
it. Network identity is explicit, particularly for the six supported EVM chains.
The collection and financial aggregation remain in the existing Gansar worker
and evidence graph, respectively.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlsplit

from .engine.blockchain_analytics import _bitcoin_witness
from .validators.ton_address import parse_ton_address


EVM_CHAINS = ('eth', 'bsc', 'polygon', 'arbitrum', 'optimism', 'avalanche')
CHAIN_OPTIONS = (
    {'id': 'btc', 'label': 'Bitcoin', 'chain_id': None},
    {'id': 'doge', 'label': 'Dogecoin', 'chain_id': None},
    {'id': 'eth', 'label': 'Ethereum', 'chain_id': 1},
    {'id': 'bsc', 'label': 'BNB Smart Chain', 'chain_id': 56},
    {'id': 'polygon', 'label': 'Polygon', 'chain_id': 137},
    {'id': 'arbitrum', 'label': 'Arbitrum One', 'chain_id': 42161},
    {'id': 'optimism', 'label': 'Optimism', 'chain_id': 10},
    {'id': 'avalanche', 'label': 'Avalanche C-Chain', 'chain_id': 43114},
    {'id': 'tron', 'label': 'Tron', 'chain_id': None},
    {'id': 'ton', 'label': 'TON', 'chain_id': None},
    {'id': 'solana', 'label': 'Solana', 'chain_id': None},
)
CHAINS = tuple(item['id'] for item in CHAIN_OPTIONS)
OPERATIONS = ('profile', 'balances', 'assets', 'transactions', 'nft', 'identity',
              'contracts', 'labels', 'attribution', 'trace', 'cached')
_ALIASES = {'ethereum': 'eth', 'bitcoin': 'btc', 'dogecoin': 'doge',
            'binance': 'bsc', 'bnb': 'bsc', 'avax': 'avalanche', 'matic': 'polygon',
            'sol': 'solana', 'evm': 'auto', '': 'auto'}
_BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_COMMON = ('profile', 'balances', 'assets', 'transactions', 'labels',
           'attribution', 'trace', 'cached')
_COVERAGE = {
    'btc': ('Blockstream, mempool.space; BlockCypher fallback',
            'Native BTC/UTXO address history; no token/NFT inventory',
            'Public provider quotas; returned bounded sample is not complete chain history.'),
    'doge': ('Blockchair; BlockCypher fallback; optional SoChain/OKLink',
             'Native DOGE/UTXO address history; no token/NFT inventory',
             'SoChain/OKLink require keys; Dogechain is a page link; Core RPC has no assumed address index; Bitquery/GetBlock are unavailable skeletons.'),
    'eth': ('Ethereum RPC, Etherscan V2, Blockscout, Blockchair, Ethplorer, explorer HTML',
            'Native state; indexed/token transfer observations where returned; ENS/public identity context',
            'Etherscan needs a key; public/HTML endpoints may fail; transfer observations are not full NFT inventory.'),
    'bsc': ('BSC RPC, BscScan, BscIntel, explorer HTML',
            'Native state; bounded BEP20/NFT transfer and contract observations',
            'BscScan needs a key; public log/enrichment coverage is bounded; no full NFT inventory.'),
    'polygon': ('Polygon RPC, explorer HTML, Etherscan V2',
                'Native balance/nonce/code; indexed history only from responding explorer/API',
                'RPC state does not enumerate history; Etherscan needs a key; no full NFT inventory.'),
    'arbitrum': ('Arbitrum RPC, Arbiscan HTML, Etherscan V2',
                 'Native balance/nonce/code; indexed history only from responding explorer/API',
                 'RPC state does not enumerate history; Etherscan needs a key; no full NFT inventory.'),
    'optimism': ('Optimism RPC, Blockscout, explorer HTML, Etherscan V2',
                 'Native state and indexed history/transfer observations',
                 'Public indexer availability/quotas vary; Etherscan needs a key; no full NFT inventory.'),
    'avalanche': ('Avalanche C-Chain RPC, Etherscan V2',
                  'Native balance/nonce/code; optional indexed API observations',
                  'RPC state does not enumerate history; Etherscan needs a key; no full NFT inventory.'),
    'tron': ('TronScan, TronGrid, public contract observations',
             'TRX, TRC20, resources, decoded transfers and contract metadata',
             'Public rate limits and optional provider keys; no full NFT inventory.'),
    'ton': ('TonAPI, Tonviewer; Toncenter/V3 and bounded public fallbacks; TON NFT service',
            'TON/Jetton, history, NFT wallet/item/collection, exact DNS/collectibles, on-chain getter checks',
            'Public provider gates/429; indexer ownership is separate from getter verification; mainnet only.'),
    'solana': ('Solana RPC; Solscan explorer context',
               'SOL/account state, signatures/decoded transactions, SPL token accounts and NFT observations',
               'Public RPC quotas/pruning; unavailable Solscan is not a successful data substitute; no dedicated full NFT inventory.'),
}


def normalize_chain(chain):
    value = str(chain or '').strip().lower()
    return _ALIASES.get(value, value)


def _base58_bytes(value):
    if not value or len(value) > 100:
        return None
    number = 0
    for character in value:
        digit = _BASE58.find(character)
        if digit < 0:
            return None
        number = number * 58 + digit
    padding = len(value) - len(value.lstrip('1'))
    return b'\0' * padding + number.to_bytes((number.bit_length() + 7) // 8, 'big')


def _base58check(value, versions):
    decoded = _base58_bytes(value)
    if decoded is None or len(decoded) != 25 or decoded[0] not in versions:
        return False
    checksum = hashlib.sha256(hashlib.sha256(decoded[:21]).digest()).digest()[:4]
    return decoded[21:] == checksum


def canonical_crypto_address(chain, value):
    """Return a valid network-scoped representation, otherwise None."""
    chain = normalize_chain(chain)
    if not isinstance(value, str) or len(value) > 200:
        return None
    value = value.strip()
    if chain in EVM_CHAINS:
        return value.lower() if re.fullmatch(r'0x[0-9a-fA-F]{40}', value) else None
    if chain == 'ton':
        parsed = parse_ton_address(value)
        return parsed['raw'] if parsed else None
    if chain == 'btc':
        if _bitcoin_witness(value):
            return value.lower()
        return value if _base58check(value, (0, 5)) else None
    if chain == 'doge':
        return value if _base58check(value, (0x1e, 0x16)) else None
    if chain == 'tron':
        return value if value.startswith('T') and _base58check(value, (0x41,)) else None
    if chain == 'solana':
        decoded = _base58_bytes(value)
        return value if decoded is not None and len(decoded) == 32 else None
    return None


def _operations(chain, kind='address'):
    if kind in ('ton_name', 'nft_reference'):
        return ['profile', 'nft', 'cached']
    operations = list(_COMMON)
    if chain in EVM_CHAINS:
        operations += ['identity', 'contracts']
    elif chain == 'tron':
        operations.append('contracts')
    elif chain == 'ton':
        operations.append('nft')
    return [operation for operation in OPERATIONS if operation in operations]


def _nft_reference(value):
    """Recognize exact formats handled by the isolated TON NFT entry point.

    This is syntactic routing only: a username/gift page does not establish an
    NFT contract, owner or even an on-chain export. Generic names are excluded.
    """
    if re.fullmatch(r'@[A-Za-z0-9_]{1,64}|[A-Za-z0-9_]{1,64}\.t\.me', value, re.I):
        return value.lower()
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*-\d+', value):
        return value
    candidate = value if '://' in value else 'https://' + value
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or '').lower().removeprefix('www.')
        if (parsed.scheme not in ('http', 'https') or parsed.username or parsed.password
                or parsed.port not in (None, 80, 443)):
            return None
    except ValueError:
        return None
    if host not in ('t.me', 'fragment.com', 'getgems.io', 'tonviewer.com', 'tonscan.org', 'gram.org'):
        return None
    parts = [unquote(part) for part in parsed.path.split('/') if part]
    if host == 't.me':
        if len(parts) == 1 and re.fullmatch(r'[A-Za-z0-9_]{1,64}', parts[0]):
            return 'https://t.me/' + parts[0]
        if len(parts) == 2 and parts[0].lower() == 'nft' and re.fullmatch(r'[A-Za-z][A-Za-z0-9]*-\d+', parts[1]):
            return 'https://t.me/nft/' + parts[1]
        return None
    if host == 'fragment.com' and len(parts) == 2 and parts[0].lower() == 'username':
        return 'https://fragment.com/username/' + parts[1] if re.fullmatch(r'[A-Za-z0-9_]{1,64}', parts[1]) else None
    addresses = [part for part in parts if canonical_crypto_address('ton', part)]
    if host == 'gram.org' and not (len(parts) == 2 and parts[0].lower() == 'address' and len(addresses) == 1):
        return None
    if len(addresses) == 1 or host == 'getgems.io' and len(addresses) == 2:
        if any((parse_ton_address(address) or {}).get('test_only') for address in addresses):
            return None
        return 'https://' + host + parsed.path
    return None


def resolve_crypto_target(value, chain='auto'):
    """Return JSON-safe resolution for a machine value; never inspect a label."""
    selected = normalize_chain(chain)
    text = value.strip() if isinstance(value, str) else ''
    result = {'valid': False, 'input': text, 'target_kind': 'unsupported',
              'candidates': [], 'chain': '', 'chain_id': None,
              'canonical_address': '', 'identity_key': '', 'representation': '',
              'test_only': False, 'requires_network': False,
              'supported_operations': [], 'operation_reasons': {},
              'error_code': '', 'reason': ''}
    if selected not in ('auto', *CHAINS):
        result.update(error_code='unsupported_network', reason='Эта сеть отсутствует в установленном Gansar.')
        return result
    if not text or len(text) > 200:
        result.update(error_code='invalid_crypto_target', reason='Укажите поддерживаемый адрес или точный идентификатор NFT, до 200 символов.')
        return result
    candidates = []
    canonical = ''
    kind = 'address'
    if re.fullmatch(r'0x[0-9a-fA-F]{40}', text):
        candidates = list(EVM_CHAINS)
    else:
        # The selected chain may legitimately share a Base58 representation.
        candidates = [item for item in ('btc', 'doge', 'tron', 'ton') if canonical_crypto_address(item, text)]
        if not candidates and canonical_crypto_address('solana', text):
            candidates.append('solana')
    if not candidates:
        if re.fullmatch(r'[a-z0-9_-]+(?:\.[a-z0-9_-]+)*\.ton', text, re.I):
            candidates, kind, canonical = ['ton'], 'ton_name', text.lower()
        elif re.fullmatch(r'(?:[^\s./@]+\.)+eth', text, re.I):
            candidates, kind, canonical = ['eth'], 'ens_name', text.lower()
        elif _nft_reference(text):
            candidates, kind, canonical = ['ton'], 'nft_reference', _nft_reference(text)
    result['candidates'] = candidates
    if not candidates:
        result.update(error_code='invalid_crypto_target', reason='Значение не является поддерживаемым адресом с корректным форматом/checksum. IP, имя пользователя и hash транзакции нельзя подставлять как адрес кошелька.')
        return result
    if selected != 'auto' and selected not in candidates:
        result.update(error_code='network_mismatch', reason='Адрес или идентификатор не соответствует выбранной сети.')
        return result
    resolved = selected if selected != 'auto' else candidates[0] if len(candidates) == 1 else 'evm'
    result.update(valid=True, target_kind='name' if kind in ('ton_name', 'ens_name') else kind,
                  chain=resolved, requires_network=resolved == 'evm')
    if resolved == 'evm':
        result.update(canonical_address=text.lower(), representation='hex',
                      error_code='network_required', reason='Выберите сеть: формат 0x не определяет, в какой EVM-сети требуется исследование.')
        return result
    ton = parse_ton_address(text) if resolved == 'ton' and kind == 'address' else None
    canonical = canonical or canonical_crypto_address(resolved, text)
    operations = _operations(resolved, kind)
    representation = ('ens' if kind == 'ens_name' else 'ton_dns' if kind == 'ton_name'
                      else 'public_nft_reference' if kind == 'nft_reference'
                      else ton['format'] if ton else 'hex' if resolved in EVM_CHAINS
                      else 'bech32' if resolved == 'btc' and text.lower().startswith('bc1') else 'base58')
    result.update(canonical_address=canonical, representation=representation,
                  identity_key=resolved + '|' + (canonical if kind == 'address' else kind + ':' + canonical),
                  chain_id=next(item['chain_id'] for item in CHAIN_OPTIONS if item['id'] == resolved),
                  supported_operations=operations,
                  operation_reasons={operation: ('Полная NFT-инвентаризация реализована только для TON.' if operation == 'nft'
                       else 'ENS/Lens/Basenames/EAS доступны для EVM-адресов; это публичные записи, не доказательство личности.' if operation == 'identity'
                       else 'Установленный адаптер не реализует эту операцию для данного типа цели/сети.')
                       for operation in OPERATIONS if operation not in operations})
    if ton and ton['test_only']:
        result.update(valid=False, test_only=True, supported_operations=[], error_code='testnet_not_supported',
                      reason='Установленный Gansar настроен на mainnet; TON test-only адрес не выполняется.')
    return result


def validate_gansar_arguments(arguments):
    """Validate semantics before spawning the worker; return a copied mapping."""
    if not isinstance(arguments, dict):
        raise ValueError('Аргументы Gansar должны быть объектом.')
    normalized = dict(arguments)
    resolution = resolve_crypto_target(normalized.get('address'), normalized.get('chain', 'auto'))
    if not resolution['valid'] or resolution['requires_network']:
        raise ValueError(resolution['reason'])
    operation = normalized.get('operation', 'profile')
    if operation not in resolution['supported_operations']:
        raise ValueError(resolution['operation_reasons'].get(operation, 'Неизвестная операция Gansar.'))
    normalized['chain'] = resolution['chain']
    normalized['address'] = resolution['canonical_address']
    normalized['operation'] = operation
    # Named NFT references require the actual NFT service entry point. Unlike
    # .ton, public asset links do not automatically select it in the worker.
    if resolution['target_kind'] == 'nft_reference' and operation == 'profile':
        normalized['operation'] = 'nft'
    return normalized


def node_gansar_capability(node, chain='auto'):
    """Formal node→tool compatibility, using typed attributes only.

    Do not fall back to display labels or unrelated target_address: an asset's
    owner and the NFT contract are different entities.
    """
    node = node if isinstance(node, dict) else {}
    attrs = node.get('attributes') if isinstance(node.get('attributes'), dict) else {}
    kind = node.get('type')
    if kind == 'blockchain_address':
        value = attrs.get('address') or attrs.get('value')
    elif kind in ('nft', 'nft_asset', 'token_asset', 'asset', 'collection', 'token'):
        value = attrs.get('contract') or attrs.get('asset_id') or attrs.get('address')
        if not value and attrs.get('asset_type') == 'nft_collection':
            value = attrs.get('collection')
    elif kind in ('contract', 'infrastructure_asset') and (kind == 'contract' or attrs.get('asset_type') == 'blockchain_contract'):
        value = attrs.get('address') or attrs.get('contract')
    else:
        value = None
    stored_chain=normalize_chain(attrs.get('chain') or attrs.get('network') or attrs.get('platform'))
    selected = chain if normalize_chain(chain) != 'auto' else stored_chain
    if normalize_chain(selected) not in ('auto', *CHAINS):
        selected = 'auto'
    resolution = resolve_crypto_target(value, selected)
    if stored_chain in CHAINS and normalize_chain(chain) not in ('auto',stored_chain):
        resolution.update(valid=False,supported_operations=[],error_code='network_mismatch',
            reason='Сеть инструмента отличается от сети выбранной сущности. Создайте отдельный объект для другой сети.')
    elif value is None:
        resolution.update(valid=False, error_code='incompatible_node_type',
                          reason='Gansar принимает адрес кошелька/контракта или проверяемый NFT-идентификатор. Выбранный тип узла несовместим.')
    return {**resolution, 'compatible': bool(resolution['valid']), 'node_type': kind or '',
            'machine_value': value or ''}


def capability_matrix():
    """Serializable installed capabilities, not a promise of live availability."""
    return [{**item, 'supported_operations': _operations(item['id']),
             'address_validation': 'format' if item['id'] in EVM_CHAINS else 'base58_32_bytes' if item['id'] == 'solana' else 'checksum',
             'nft_inventory': item['id'] == 'ton', 'live_availability': 'provider_dependent',
             'providers': _COVERAGE[item['id']][0], 'data_coverage': _COVERAGE[item['id']][1],
             'limitations': _COVERAGE[item['id']][2]}
            for item in CHAIN_OPTIONS]
