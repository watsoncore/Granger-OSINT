"""Reviewed SteamRecon MIT subset. Copyright (c) 2026 SteamRecon contributors.
See resources/third-party/SteamRecon-LICENSE.txt and steamrecon-provenance.json.
No upstream HTTP client, CLI, configuration or credential storage is included.
"""
from __future__ import annotations
import html
import re
import xml.etree.ElementTree as ET

class SteamPublicParser:
    def _profile(self, root: ET.Element, identity) -> dict:
        keys = [
            "steamID64", "steamID", "onlineState", "stateMessage", "privacyState",
            "visibilityState", "avatarIcon", "avatarMedium", "avatarFull", "vacBanned",
            "tradeBanState", "isLimitedAccount", "customURL", "memberSince", "steamRating",
            "hoursPlayed2Wk", "headline", "location", "realname", "summary",
        ]
        profile = {key: self._text(root.findtext(key)) for key in keys}
        profile["profileurl"] = identity.vanity_url or identity.profile_url
        profile["personaname"] = profile.get("steamID")
        profile["privacy"] = profile.get("privacyState") or profile.get("visibilityState")
        return profile

    def _games(self, root: ET.Element) -> list[dict]:
        games = []
        container = root.find("mostPlayedGames")
        if container is None:
            return games
        for game in container.findall("mostPlayedGame"):
            record = {child.tag: self._text(child.text) for child in list(game)}
            link = record.get("gameLink", "")
            match = re.search(r"/app/(\d+)", link)
            if match:
                record["appid"] = int(match.group(1))
            if record:
                games.append(record)
        return games

    def _groups(self, root: ET.Element) -> list[dict]:
        container = root.find("groups")
        if container is None:
            return []
        return [
            {child.tag: self._text(child.text) for child in list(group)}
            for group in container.findall("group")
        ]

    @staticmethod
    def _text(value: str | None) -> str:
        return html.unescape(value or "").strip()
