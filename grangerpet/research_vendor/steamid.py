"""Reviewed SteamRecon MIT subset. Copyright (c) 2026 SteamRecon contributors.
See resources/third-party/SteamRecon-LICENSE.txt and steamrecon-provenance.json.
No upstream HTTP client, CLI, configuration or credential storage is included.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse




STEAM64_BASE = 76561197960265728


class SteamIDError(ValueError):
    pass


@dataclass(frozen=True)
class SteamIdentity:
    steamid64: str
    account_id: int
    steam2: str
    steam3: str
    steam_hex: str
    profile_url: str
    vanity_url: str = ""

    def to_dict(self) -> dict[str, str | int]:
        return {
            "steamid64": self.steamid64,
            "account_id": self.account_id,
            "steam2": self.steam2,
            "steam3": self.steam3,
            "steam_hex": self.steam_hex,
            "profile_url": self.profile_url,
            "vanity_url": self.vanity_url,
        }


def from_account_id(account_id: int, vanity_url: str = "") -> SteamIdentity:
    if account_id < 0 or account_id > 0xFFFFFFFF:
        raise SteamIDError("Invalid account ID")
    steamid64 = STEAM64_BASE + account_id
    auth_server = account_id & 1
    auth_id = account_id >> 1
    return SteamIdentity(
        steamid64=str(steamid64),
        account_id=account_id,
        steam2=f"STEAM_0:{auth_server}:{auth_id}",
        steam3=f"[U:1:{account_id}]",
        steam_hex=f"steam:{steamid64:x}",
        profile_url=f"https://steamcommunity.com/profiles/{steamid64}",
        vanity_url=vanity_url,
    )


def parse_local(value: str) -> SteamIdentity | None:
    raw = value.strip()
    steam2 = re.fullmatch(r"STEAM_[0-5]:([01]):(\d+)", raw, re.IGNORECASE)
    if steam2:
        return from_account_id(int(steam2.group(2)) * 2 + int(steam2.group(1)))
    steam3 = re.fullmatch(r"\[?U:1:(\d+)\]?", raw, re.IGNORECASE)
    if steam3:
        return from_account_id(int(steam3.group(1)))
    hex_id = re.fullmatch(r"(?:steam:)?([0-9a-f]{15,16})", raw, re.IGNORECASE)
    if hex_id and any(char.isalpha() for char in hex_id.group(1)):
        steam64 = int(hex_id.group(1), 16)
        if steam64 >= STEAM64_BASE:
            return from_account_id(steam64 - STEAM64_BASE)
    profile_match = re.search(r"steamcommunity\.com/profiles/(\d{17})", raw, re.IGNORECASE)
    if profile_match:
        steam64 = int(profile_match.group(1))
        return from_account_id(steam64 - STEAM64_BASE)
    if re.fullmatch(r"\d{17}", raw):
        steam64 = int(raw)
        if steam64 >= STEAM64_BASE:
            return from_account_id(steam64 - STEAM64_BASE)
    if re.fullmatch(r"\d{1,10}", raw):
        return from_account_id(int(raw))
    return None


def extract_vanity(value: str) -> str:
    raw = value.strip()
    if "steamcommunity.com" in raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        match = re.search(r"/id/([^/?#]+)", parsed.path)
        return match.group(1) if match else ""
    if re.fullmatch(r"[A-Za-z0-9_-]{2,64}", raw):
        return raw
    return ""


def resolve(value: str, client: HttpClient) -> SteamIdentity:
    local = parse_local(value)
    if local:
        return local
    vanity = extract_vanity(value)
    if not vanity:
        raise SteamIDError("Unsupported Steam identifier")
    url = f"https://steamcommunity.com/id/{vanity}/?xml=1"
    response = client.get(url)
    match = re.search(r"<steamID64>(\d{17})</steamID64>", response.text)
    if not match:
        raise SteamIDError("Steam profile was not resolved")
    steam64 = int(match.group(1))
    return from_account_id(steam64 - STEAM64_BASE, f"https://steamcommunity.com/id/{vanity}")
