"""Validate TON addr_std strings without importing or redistributing vendor code.

Independently written from the public TON address-format specification:
https://docs.ton.org/foundations/addresses/formats
https://github.com/ton-blockchain/TEPs/blob/master/text/0002-address.md

This validates representation only. It does not claim an account exists, reveal
its owner, resolve TON DNS, or send any network request. CRC is the Python
stdlib's CRC16-CCITT/XMODEM (initial value zero), not copied vendor source.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import re


def parse_ton_address(value):
    """Return a normalized addr_std descriptor, or None for an invalid string.

    Both URL-safe and standard Base64 are accepted, as required by TON docs.
    Raw addresses carry no bounce or testnet flag; friendly flags are retained
    so the existing mainnet-only router can reject testnet input explicitly.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    raw = re.fullmatch(r"(-?\d{1,10}):([0-9a-fA-F]{64})", value)
    if raw:
        workchain = int(raw.group(1))
        # TEP-2 defines signed-32 workchain IDs for the raw form. The
        # user-friendly addr_std wrapper below carries a signed-8 ID instead.
        if not -(2**31) <= workchain < 2**31:
            return None
        account = raw.group(2).lower()
        return {"raw": f"{workchain}:{account}", "workchain": workchain,
                "account_id": account, "test_only": False, "bounceable": None,
                "format": "raw"}
    if not re.fullmatch(r"[A-Za-z0-9_+/\-]{48}", value):
        return None
    try:
        decoded = base64.b64decode(value.translate(str.maketrans('-_', '+/')), validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(decoded) != 36:
        return None
    payload, supplied_checksum = decoded[:34], decoded[34:]
    expected_checksum = binascii.crc_hqx(payload, 0).to_bytes(2, 'big')
    if not hmac.compare_digest(supplied_checksum, expected_checksum):
        return None
    tag = payload[0]
    base_tag = tag & 0x7f
    if base_tag not in (0x11, 0x51):
        return None
    workchain = int.from_bytes(payload[1:2], 'big', signed=True)
    account = payload[2:].hex()
    return {"raw": f"{workchain}:{account}", "workchain": workchain,
            "account_id": account, "test_only": bool(tag & 0x80),
            "bounceable": base_tag == 0x11, "format": "friendly"}
