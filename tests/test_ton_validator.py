"""Public TON/TEP-2 known vectors, independent of optional Gansar sources."""
import ast
import base64
import binascii
from pathlib import Path

import pytest

from grangerpet.engine.router import detect_query, validate_ton
from grangerpet.validators.ton_address import parse_ton_address


RAW = '0:ca6e321c7cce9ecedf0a8ca2492ec8592494aa5fb5ce0387dff96ef6af982a3e'
ROOT_DNS = '-1:e56754f83426f69b09267bd876ac97c44821345b7e266bd956a7bfbfb98df35c'


@pytest.mark.parametrize('address,bounce,test_only', [
    ('EQDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPrHF', True, False),
    ('UQDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPuwA', False, False),
    ('kQDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPgpP', True, True),
    ('0QDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPleK', False, True),
])
def test_official_ton_documentation_vectors(address, bounce, test_only):
    parsed = parse_ton_address(address)
    assert parsed['raw'] == RAW
    assert parsed['bounceable'] is bounce and parsed['test_only'] is test_only
    assert parsed['workchain'] == 0 and parsed['format'] == 'friendly'
    standard = address.replace('-', '+').replace('_', '/')
    assert parse_ton_address(standard) == parsed


@pytest.mark.parametrize('address,bounce', [
    ('Ef_lZ1T4NCb2mwkme9h2rJfESCE0W34ma9lWp7-_uY3zXDvq', True),
    ('Uf_lZ1T4NCb2mwkme9h2rJfESCE0W34ma9lWp7-_uY3zXGYv', False),
])
def test_official_tep2_masterchain_vectors(address, bounce):
    parsed = parse_ton_address(address)
    assert parsed['raw'] == ROOT_DNS and parsed['workchain'] == -1
    assert parsed['bounceable'] is bounce and not parsed['test_only']


def test_raw_is_case_normalized_and_flags_are_not_invented():
    parsed = parse_ton_address('  -1:' + 'aB' * 32 + '  ')
    assert parsed['raw'] == '-1:' + 'ab' * 32
    assert parsed['bounceable'] is None and not parsed['test_only'] and parsed['format'] == 'raw'


@pytest.mark.parametrize('value', [None, '', 123, '0:'+'g'*64, '0:'+'0'*63, '2147483648:'+'0'*64,
                                  '-2147483649:'+'0'*64, '0:'+'0'*65, 'EQ'+'A'*46,
                                  'EQDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPrHA'])
def test_malformed_or_corrupt_input_is_rejected(value):
    assert parse_ton_address(value) is None


@pytest.mark.parametrize('workchain', [-2147483648, -129, 128, 2147483647])
def test_raw_workchain_retains_tep2_signed32_range(workchain):
    address = f'{workchain}:' + 'ab' * 32
    assert parse_ton_address(address)['raw'] == address


def test_wrong_tag_with_correct_checksum_is_not_a_contract_address():
    data = bytes([0x3e, 0]) + bytes(32)
    encoded = base64.urlsafe_b64encode(data + binascii.crc_hqx(data, 0).to_bytes(2, 'big')).decode()
    assert parse_ton_address(encoded) is None


def test_router_works_without_a_vendor_checkout_and_retains_testnet_rejection(tmp_path):
    missing = {'source_root': str(tmp_path / 'no-optional-tools')}
    public = 'EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c'
    assert validate_ton(public, missing)['raw'] == '0:'+'0'*64
    result = detect_query(public, options=missing)
    assert result.valid and result.chain == 'ton' and result.text == '0:'+'0'*64
    testnet = detect_query('kQDKbjIcfM6ezt8KjKJJLshZJJSqX7XOA4ff-W72r5gqPgpP', options=missing)
    assert not testnet.valid and 'testnet' in testnet.error


def test_build_spec_has_no_dependency_on_unlicensed_optional_validator():
    root = Path(__file__).resolve().parents[1]
    spec = (root/'GrangerPet.spec').read_text(encoding='utf-8-sig')
    ast.parse(spec)
    assert 'Gansar-main' not in spec and 'ton_normalize.py' not in spec
    assert (root/'grangerpet/validators/ton_address.py').is_file()
