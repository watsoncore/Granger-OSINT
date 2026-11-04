"""Public, finite inputs for the installed Maigret engine (no Qt/vendor imports)."""
from __future__ import annotations

MODES = ("quick", "standard", "full", "custom")
_NAMES = {"type": "array", "maxItems": 100, "uniqueItems": True,
          "items": {"type": "string", "minLength": 1, "maxLength": 160}}
INPUT_SCHEMA = {
    "type": "object", "properties": {
        "username": {"type": "string", "minLength": 1, "maxLength": 64},
        "mode": {"type": "string", "enum": list(MODES)},
        "site_count": {"type": "integer", "minimum": 0},
        "sites": _NAMES, "tags": _NAMES, "exclude_tags": _NAMES,
        "per_site_timeout": {"type": "number", "minimum": 1, "maximum": 60},
        "concurrency": {"type": "integer", "minimum": 1, "maximum": 32},
        "parse_metadata": {"type": "boolean"},
        "include_mirrors": {"type": "boolean"},
        "time_budget": {"type": "number", "minimum": 5, "maximum": 3600},
    }, "required": ["username"], "additionalProperties": False,
}


def normalize_options(arguments, *, legacy_limit=10, legacy_timeout=25):
    """Validate again in the isolated worker; a site count is never a result cap.

    Full/Standard selection does not accept a hidden top-N. Custom count=0 is
    all matching database entries. Lists bound input size, not database coverage.
    """
    arguments = dict(arguments or {})
    if set(arguments) - set(INPUT_SCHEMA["properties"]):
        raise ValueError("Unknown Maigret option")
    mode = arguments.get("mode", "quick")
    if mode not in MODES:
        raise ValueError("Unknown Maigret mode")
    out = {"mode": mode}
    for key in ("sites", "tags", "exclude_tags"):
        values = arguments.get(key, [])
        if (not isinstance(values, list) or len(values) > 100 or
                any(not isinstance(v, str) or not 1 <= len(v) <= 160 or
                    any(ord(c) < 32 for c in v) for v in values)):
            raise ValueError("Invalid Maigret filter")
        out[key] = list(dict.fromkeys(values))
    if mode != "custom" and any(out[key] for key in ("sites", "tags", "exclude_tags")):
        raise ValueError("Site filters require Custom mode")
    count = arguments.get("site_count", max(1, min(50, int(legacy_limit))) if mode == "quick" else 0)
    if type(count) is not int or count < 0:
        raise ValueError("Invalid Maigret site count")
    if (mode in ("standard", "full") and count) or (mode == "quick" and not 1 <= count <= 50):
        raise ValueError("Site count requires Custom mode (Quick permits 1–50 ranked sites)")
    out["site_count"] = count
    defaults = {"per_site_timeout": 7 if mode == "quick" else 30,
                "concurrency": 3 if mode == "quick" else 12,
                "time_budget": max(5, min(3600, float(legacy_timeout))) if mode == "quick" else 300 if mode == "standard" else 1800}
    import math
    for key, low, high in (("per_site_timeout", 1, 60), ("concurrency", 1, 32), ("time_budget", 5, 3600)):
        value = arguments.get(key, defaults[key])
        if (type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high
                or key == "concurrency" and type(value) is not int):
            raise ValueError("Invalid Maigret execution bound")
        out[key] = value
    parse = arguments.get("parse_metadata", True)
    if type(parse) is not bool:
        raise ValueError("Invalid Maigret metadata option")
    out["parse_metadata"] = parse
    mirrors = arguments.get("include_mirrors", True)
    if type(mirrors) is not bool or mode != "custom" and mirrors is False:
        raise ValueError("Exact site selection requires Custom mode")
    out["include_mirrors"] = mirrors
    return out
