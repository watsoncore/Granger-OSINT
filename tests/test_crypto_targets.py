"""Offline contracts, not live provider-availability tests."""
import base64
import binascii
import hashlib
import json

import pytest

from grangerpet.crypto_targets import (
    CHAINS, CHAIN_OPTIONS, EVM_CHAINS, canonical_crypto_address,
    capability_matrix, node_gansar_capability, resolve_crypto_target,
    validate_gansar_arguments,
)
from grangerpet.engine.blockchain_contracts import CHAINS as WORKER_CHAINS
from grangerpet.engine.blockchain_analytics import analyze_transactions, canonical_address


BTC = '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'
TRON = 'TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj'
EVM = '0xAbCdEf0123456789aBcDEF0123456789abCdef01'
SOLANA = '11111111111111111111111111111111'
TON_RAW = '0:' + '12' * 32


def base58check(version, body=b'\x12' * 20):
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    payload = bytes([version]) + body
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    number = int.from_bytes(data, 'big')
    encoded = ''
    while number:
        number, digit = divmod(number, 58)
        encoded = alphabet[digit] + encoded
    return '1' * (len(data) - len(data.lstrip(b'\0'))) + encoded


def ton_friendly(tag=0x11):
    payload = bytes([tag, 0]) + bytes.fromhex('12' * 32)
    return base64.urlsafe_b64encode(payload + binascii.crc_hqx(payload, 0).to_bytes(2, 'big')).decode()


@pytest.mark.parametrize('chain,address', [('btc', BTC), ('doge', base58check(0x1e)),
    ('doge', base58check(0x16)), ('tron', TRON), ('solana', SOLANA), ('ton', TON_RAW),
    ('ton', ton_friendly()), *[(chain, EVM) for chain in EVM_CHAINS]])
def test_all_actual_network_formats_resolve_without_vendor_imports(chain, address):
    result = resolve_crypto_target(address, chain)
    assert result['valid'] and not result['requires_network']
    assert result['chain'] == chain and result['identity_key'].startswith(chain + '|')
    assert result['canonical_address'] == canonical_crypto_address(chain, address)
    assert 'profile' in result['supported_operations']


def test_capability_matrix_matches_exact_installed_worker_chains_and_is_json_safe():
    assert CHAINS == WORKER_CHAINS
    assert len(CHAIN_OPTIONS) == 11
    assert json.loads(json.dumps(capability_matrix(), ensure_ascii=False)) == capability_matrix()
    assert [row['id'] for row in capability_matrix() if row['nft_inventory']] == ['ton']
    assert 'base' not in CHAINS  # Basenames identity context is not a financial adapter.


def test_same_hex_address_requires_network_and_has_distinct_chain_scoped_identity():
    auto = resolve_crypto_target(EVM)
    assert auto['valid'] and auto['requires_network'] and auto['candidates'] == list(EVM_CHAINS)
    assert auto['identity_key'] == '' and auto['supported_operations'] == []
    with pytest.raises(ValueError, match='Выберите сеть'):
        validate_gansar_arguments({'address': EVM})
    identities = {resolve_crypto_target(EVM, chain)['identity_key'] for chain in EVM_CHAINS}
    assert len(identities) == 6
    assert resolve_crypto_target(EVM.lower(), 'ethereum')['identity_key'] == resolve_crypto_target(EVM, 'eth')['identity_key']


@pytest.mark.parametrize('value', ['50.7.89.130', '8.8.8.8', 'person@example.org', 'Hermione',
    'a' * 64, '0x' + 'ab' * 32, '0x1234', 'https://etherscan.io/tx/0x' + 'a' * 64,
    BTC[:-1] + 'b', TRON[:-1] + 'k', 'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kg3g4ty'])
def test_non_addresses_transaction_hashes_and_bad_checksums_are_rejected(value):
    assert not resolve_crypto_target(value)['valid']
    with pytest.raises(ValueError):
        validate_gansar_arguments({'address': value})


def test_network_mismatch_unknown_chain_and_testnet_are_not_silently_changed():
    assert resolve_crypto_target(BTC, 'ton')['error_code'] == 'network_mismatch'
    assert resolve_crypto_target(EVM, 'base')['error_code'] == 'unsupported_network'
    assert not resolve_crypto_target(base58check(0x6f), 'btc')['valid']
    testnet = resolve_crypto_target(ton_friendly(0x91), 'ton')
    assert not testnet['valid'] and testnet['test_only'] and testnet['error_code'] == 'testnet_not_supported'


def test_ton_aliases_match_stable_existing_graph_identity_and_preserve_representations():
    bounce = resolve_crypto_target(ton_friendly(), 'ton')
    nonbounce = resolve_crypto_target(ton_friendly(0x51), 'ton')
    raw = resolve_crypto_target(TON_RAW)
    assert bounce['identity_key'] == nonbounce['identity_key'] == raw['identity_key'] == 'ton|' + TON_RAW
    assert bounce['representation'] == 'friendly' and raw['representation'] == 'raw'


def test_address_validation_does_not_collapse_case_sensitive_base58():
    assert canonical_crypto_address('tron', TRON) == TRON
    assert canonical_crypto_address('tron', TRON.lower()) is None
    # BIP-173 reference vector, 20-byte witness-v0 program.
    address = 'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4'
    assert canonical_crypto_address('btc', address.upper()) == address
    assert canonical_crypto_address('btc', 'bC' + address[2:]) is None


def test_operations_reflect_real_entry_points_and_normalization_does_not_mutate_input():
    args = {'address': EVM, 'chain': 'bnb', 'operation': 'transactions', 'mode': 'quick'}
    normalized = validate_gansar_arguments(args)
    assert args['chain'] == 'bnb' and args['address'] == EVM
    assert normalized == {**args, 'chain': 'bsc', 'address': EVM.lower()}
    with pytest.raises(ValueError, match='только для TON'):
        validate_gansar_arguments({**args, 'operation': 'nft'})
    with pytest.raises(ValueError):
        validate_gansar_arguments({'address': BTC, 'operation': 'contracts'})
    assert validate_gansar_arguments({'address': TRON, 'operation': 'contracts'})['chain'] == 'tron'


def test_deferred_names_and_nft_references_do_not_claim_verified_wallet_identity():
    ens = resolve_crypto_target('Example.eth')
    assert ens['valid'] and ens['chain'] == 'eth' and ens['representation'] == 'ens'
    assert ens['canonical_address'] == 'example.eth' and ens['identity_key'] == 'eth|ens_name:example.eth'
    dns = validate_gansar_arguments({'address': 'Example.ton', 'operation': 'profile'})
    assert dns['chain'] == 'ton' and dns['address'] == 'example.ton'
    gift = validate_gansar_arguments({'address': 'https://t.me/nft/LolPop-123', 'operation': 'profile'})
    assert gift['chain'] == 'ton' and gift['operation'] == 'nft'
    assert not resolve_crypto_target('https://t.me/nft/no-contract')['valid']
    assert not resolve_crypto_target('https://t.me:8443/nft/LolPop-1')['valid']


def test_node_compatibility_uses_machine_attributes_and_does_not_fall_back_to_label():
    ip = {'type': 'ip', 'label': EVM, 'attributes': {'address': EVM, 'chain': 'eth'}}
    assert not node_gansar_capability(ip)['compatible']
    assert not node_gansar_capability({'type': 'blockchain_address', 'label': BTC, 'attributes': {}})['compatible']
    wallet = {'type': 'blockchain_address', 'label': 'My wallet', 'attributes': {'address': EVM, 'chain': 'bsc'}}
    result = node_gansar_capability(wallet)
    assert result['compatible'] and result['machine_value'] == EVM and result['chain'] == 'bsc'
    assert not node_gansar_capability(wallet, 'eth')['compatible']
    assert node_gansar_capability(wallet, 'eth')['error_code'] == 'network_mismatch'
    ambiguous = {**wallet, 'attributes': {'address': EVM, 'chain': 'evm'}}
    assert node_gansar_capability(ambiguous, 'eth')['identity_key'] == 'eth|' + EVM.lower()
    asset = {'type': 'asset', 'attributes': {'asset_id': TON_RAW, 'target_address': TRON, 'chain': 'ton'}}
    assert node_gansar_capability(asset)['machine_value'] == TON_RAW
    assert not node_gansar_capability({'type': 'asset', 'attributes': {'target_address': TRON}})['compatible']
    collection = {'type': 'asset', 'attributes': {'asset_type': 'nft_collection', 'collection': TON_RAW, 'chain': 'ton'}}
    assert node_gansar_capability(collection)['compatible']


def test_bitcoin_witness_case_is_one_wallet_in_existing_analytics_and_graph():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.engine.blockchain_rows import normalize_dossier
    from grangerpet.evidence_graph import build
    address = 'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4'
    report = {'target_address': address, 'detected_chains': ['btc'], 'transactions': [
        {'chain': 'btc', 'tx_hash': 'one', 'event_id': 'one:0', 'asset': 'BTC',
         'from_address': address.upper(), 'to_address': BTC, 'amount_decimal': '0.1'},
        {'chain': 'btc', 'tx_hash': 'two', 'event_id': 'two:0', 'asset': 'BTC',
         'from_address': address, 'to_address': BTC, 'amount_decimal': '0.2'}]}
    assert canonical_address('btc', address.upper()) == address
    assert canonical_address('btc', 'BC1not-an-address') == 'BC1not-an-address'
    result = analyze_transactions(report['transactions'], address, 'btc')
    assert result['assets'][0]['outgoing'] == '0.3'
    assert result['unique_counterparties'] == 1
    records = [normalize_evidence(row, 'blockchain_gansar', address) for row in normalize_dossier(report)]
    graph = build(records, full=True, limit=5000, goal=address)
    wallets = [node for node in graph['entities'] if node['type'] == 'blockchain_address']
    assert len(wallets) == 2
    aggregate = next(edge['aggregate'] for edge in graph['relations'] if edge['relation_type'] == 'transfers')
    assert aggregate['amount'] == '0.3' and aggregate['count'] == 2


@pytest.mark.parametrize('chain,address', [('ton', ton_friendly()), ('btc', BTC), ('tron', TRON),
    ('solana', SOLANA), *[(chain, EVM) for chain in EVM_CHAINS]])
def test_input_identity_key_matches_existing_imported_wallet_node_id(chain, address):
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.engine.blockchain_rows import normalize_dossier
    from grangerpet.evidence_graph import _id, build
    resolution = resolve_crypto_target(address, chain)
    report = {'target_address': address, 'detected_chains': [chain], 'balances': [
        {'chain': chain, 'address': address, 'asset': 'OBSERVED', 'amount_decimal': '1'}]}
    records = [normalize_evidence(row, 'blockchain_gansar', address) for row in normalize_dossier(report)]
    graph = build(records, full=True, limit=5000)
    expected = _id('blockchain_address', resolution['identity_key'])
    assert any(node['id'] == expected for node in graph['entities'])


@pytest.mark.parametrize('networks', [('eth',), ('bsc',), ('eth', 'bsc')])
def test_ambiguous_hex_goal_selects_only_observed_network_scopes(networks):
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.engine.blockchain_rows import normalize_dossier
    from grangerpet.evidence_graph import _id, build
    report = {'target_address': EVM, 'detected_chains': list(networks), 'balances': [
        {'chain': chain, 'address': EVM, 'asset': 'NATIVE', 'amount_decimal': '1'} for chain in networks]}
    records = [normalize_evidence(row, 'blockchain_gansar', EVM) for row in normalize_dossier(report)]
    graph = build(records, full=True, limit=5000, goal=EVM)
    wallets = [node for node in graph['entities'] if node['type'] == 'blockchain_address']
    expected = {_id('blockchain_address', chain + '|' + EVM.lower()) for chain in networks}
    assert {node['id'] for node in wallets} == expected
    if len(networks) == 1:
        assert any(node['id'] in expected and node['attributes'].get('is_root') for node in wallets)
    else:
        scopes = [edge['to_id'] for edge in graph['relations'] if edge['relation_type'] == 'investigates']
        assert set(scopes) == expected


def test_unobserved_ambiguous_hex_goal_is_research_scope_instead_of_a_fictitious_wallet():
    from grangerpet.evidence_graph import build
    graph = build([], full=True, limit=5000, goal=EVM)
    assert not any(node['type'] == 'blockchain_address' for node in graph['entities'])
    root = next(node for node in graph['entities'] if node['attributes'].get('is_root'))
    assert root['attributes']['network_selection_required']


def test_shared_graph_aggregates_same_hex_and_token_contract_separately_per_network():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.engine.blockchain_rows import normalize_dossier
    from grangerpet.evidence_graph import build
    peer = '0x' + '12' * 20
    contract = '0x' + '34' * 20
    transactions = [{'chain': chain, 'tx_hash': 'same-hash-fixture', 'event_id': 'same-event-fixture',
        'asset': 'USD', 'token_contract': contract, 'from_address': EVM,
        'to_address': peer, 'amount_decimal': amount} for chain, amount in [('eth', '1.1'), ('bsc', '2.2')]]
    report = {'target_address': EVM, 'detected_chains': ['eth', 'bsc'], 'transactions': transactions}
    records = [normalize_evidence(row, 'blockchain_gansar', EVM) for row in normalize_dossier(report)]
    graph = build(records, full=True, limit=5000, goal=EVM)
    aggregates = [edge['aggregate'] for edge in graph['relations'] if edge['relation_type'] == 'transfers']
    assert len(aggregates) == 2
    assert {item['asset_key']: item['amount'] for item in aggregates} == {
        'eth|' + contract: '1.1', 'bsc|' + contract: '2.2'}
    assert len({node['id'] for node in graph['entities'] if node['type'] == 'transaction'}) == 2
