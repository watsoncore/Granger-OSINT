# Adapted from michaelelizarov/linkedin-osint-toolkit (MIT); see resources/third-party/integrations19.
#!/usr/bin/env python3
"""
Role Classifier - Data-Driven Engine
=====================================

Classifies LinkedIn job titles into hierarchy levels and functional divisions
using rules loaded from classification_rules.json.

The JSON file holds ALL classification data (patterns, keywords, overrides).
This module is the engine only -- edit the JSON to tune classification.

Hierarchy Levels (ordered from most to least senior):
1. Executive   2. VP         3. Director   4. Head
5. Manager     6. Lead       7. Senior     8. Specialist
9. Mid-Level  10. Junior    11. Entry     12. Staff

Public API (unchanged):
    classify_title(title)       -> dict
    classify_role_level(title)  -> (level, weight)
    classify_division(title)    -> str
    get_hierarchy_order()       -> list
    HIERARCHY_LEVELS            -> dict
    DIVISION_KEYWORDS           -> dict
"""

import json
import os
import re
from typing import Tuple

# ---------------------------------------------------------------------------
# Load classification rules from JSON
# ---------------------------------------------------------------------------
from importlib.resources import files
_rules=json.loads(files(__package__).joinpath("classification_rules.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# Public module-level constants (backwards compatible)
# ---------------------------------------------------------------------------
HIERARCHY_LEVELS = _rules["hierarchy_levels"]
DIVISION_KEYWORDS = _rules["division_keywords"]

# Pre-compile patterns for performance
_NON_TITLE_RES = [re.compile(p, re.IGNORECASE) for p in _rules["non_title_patterns"]]
_COMPANY_NAME_RES = [re.compile(p, re.IGNORECASE) for p in _rules.get("company_name_patterns", [])]
_TITLE_OVERRIDES = {k.lower(): v for k, v in _rules["title_overrides"].items()}

# Pre-compile hierarchy patterns
_HIERARCHY_RULES = []
for rule in _rules["hierarchy_patterns"]:
    level = rule["level"]
    weight = HIERARCHY_LEVELS[level]

    if "patterns" in rule:
        compiled = [re.compile(p, re.IGNORECASE) for p in rule["patterns"]]
        _HIERARCHY_RULES.append({
            "level": level,
            "weight": weight,
            "compiled": compiled,
            "exclude": re.compile(rule["exclude"], re.IGNORECASE) if "exclude" in rule else None,
            "require": re.compile(rule["require"], re.IGNORECASE) if "require" in rule else None,
            "reclassify_to_specialist": re.compile(rule["reclassify_to_specialist"], re.IGNORECASE) if "reclassify_to_specialist" in rule else None,
            "skip_if_junior": rule.get("skip_if_junior", False),
            "multi": True,
        })
    elif "pattern" in rule:
        compiled = re.compile(rule["pattern"], re.IGNORECASE)
        _HIERARCHY_RULES.append({
            "level": level,
            "weight": weight,
            "compiled": compiled,
            "exclude": re.compile(rule["exclude"], re.IGNORECASE) if "exclude" in rule else None,
            "require": re.compile(rule["require"], re.IGNORECASE) if "require" in rule else None,
            "reclassify_to_specialist": re.compile(rule["reclassify_to_specialist"], re.IGNORECASE) if "reclassify_to_specialist" in rule else None,
            "skip_if_junior": rule.get("skip_if_junior", False),
            "multi": False,
        })


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------
def clean_title(title: str) -> str:
    """Clean a raw LinkedIn title for classification.

    Strips 'at Company' suffixes, parenthetical company refs, junk entries,
    and company-name-only entries.
    """
    if not title:
        return ""

    title_stripped = title.strip()
    title_lower = title_stripped.lower()

    # Filter junk entries
    for rx in _NON_TITLE_RES:
        if rx.search(title_lower):
            return ""

    # Filter company-name-only entries
    for rx in _COMPANY_NAME_RES:
        if rx.search(title_lower):
            return ""

    # Strip "at Company Name" suffix (case-insensitive)
    cleaned = re.sub(r'\s+at\s+\S.*$', '', title_stripped, flags=re.IGNORECASE)

    # Strip trailing parenthetical company names
    cleaned = re.sub(r'\s*\(former\s+known\s+.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\([^)]{15,}\)\s*$', '', cleaned)

    # Strip trailing "- COMPANY" patterns
    cleaned = re.sub(r'\s+-\s+[A-Z][A-Za-z\s.]+$', '', cleaned)

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Hierarchy classification
# ---------------------------------------------------------------------------
def classify_role_level(title: str) -> Tuple[str, int]:
    """Classify a job title into a hierarchy level.

    Checks title_overrides first, then applies regex patterns using
    a 'collect all matches, return highest weight' strategy.

    Returns (level_name, level_weight).
    """
    if not title:
        return ("Staff", HIERARCHY_LEVELS["Staff"])

    cleaned = clean_title(title)
    if not cleaned:
        return ("Staff", HIERARCHY_LEVELS["Staff"])

    # --- 1. Exact override lookup ---
    cleaned_lower = cleaned.lower()
    override = _TITLE_OVERRIDES.get(cleaned_lower)
    if override and "level" in override:
        lvl = override["level"]
        return (lvl, HIERARCHY_LEVELS.get(lvl, 5))

    # --- 2. Handle pipe/slash-separated compound titles ---
    for sep in ["|", "/"]:
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep) if p.strip()]
            if len(parts) > 1:
                best = ("Staff", HIERARCHY_LEVELS["Staff"])
                for part in parts:
                    lvl, w = classify_role_level(part)
                    if w > best[1]:
                        best = (lvl, w)
                if best[1] > HIERARCHY_LEVELS["Staff"]:
                    return best

    # --- 3. Pattern-based classification ---
    title_lower = cleaned.lower()
    matches = []
    has_junior_modifier = bool(
        re.search(r'\b(junior|jr\.?|associate|assistant|intern|student|trainee|cadet)\b', title_lower)
    )

    for rule in _HIERARCHY_RULES:
        # Skip mid-level roles if junior modifier present
        if rule["skip_if_junior"] and has_junior_modifier:
            continue

        # Check require constraint
        if rule.get("require") and not rule["require"].search(title_lower):
            continue

        if rule["multi"]:
            for rx in rule["compiled"]:
                if rx.search(title_lower):
                    # Check exclude
                    if rule["exclude"] and rule["exclude"].search(title_lower):
                        continue
                    # Check reclassify
                    if rule["reclassify_to_specialist"] and rule["reclassify_to_specialist"].search(title_lower):
                        matches.append(("Specialist", HIERARCHY_LEVELS["Specialist"]))
                    else:
                        matches.append((rule["level"], rule["weight"]))
                    break  # one match per rule group is enough
        else:
            rx = rule["compiled"]
            if rx.search(title_lower):
                if rule["exclude"] and rule["exclude"].search(title_lower):
                    continue
                if rule["reclassify_to_specialist"] and rule["reclassify_to_specialist"].search(title_lower):
                    matches.append(("Specialist", HIERARCHY_LEVELS["Specialist"]))
                else:
                    matches.append((rule["level"], rule["weight"]))

    # Special: "director" vs "directorate" disambiguation
    if any(m[0] == "Director" for m in matches):
        if "directorate" in title_lower:
            dir_pos = title_lower.find("director")
            dtorate_pos = title_lower.find("directorate")
            # If "directorate" appears at the same position, it's a company name
            if dir_pos == dtorate_pos:
                matches = [m for m in matches if m[0] != "Director"]

    # Special: "secretary" should NOT be company secretary (already specialist)
    # handled by the JSON patterns

    if matches:
        return max(matches, key=lambda x: x[1])

    # --- 4. Fallback: if title matches any division keyword, assume Mid-Level ---
    # Titles like "Cloud & Information Security" or "Marketing & Business
    # Development" are department-name-as-title entries where the person
    # didn't specify a role level.  Classifying as Mid-Level is a reasonable
    # default rather than lumping them into the Staff catch-all.
    title_for_div = cleaned.replace("|", " ").replace("/", " ").lower()
    for _div, keywords in DIVISION_KEYWORDS.items():
        for kw in keywords:
            kw_lower = kw.lower()
            if len(kw_lower) <= 3:
                if re.search(r'\b' + re.escape(kw_lower) + r'\b', title_for_div):
                    return ("Mid-Level", HIERARCHY_LEVELS["Mid-Level"])
            else:
                if kw_lower in title_for_div:
                    return ("Mid-Level", HIERARCHY_LEVELS["Mid-Level"])

    return ("Staff", HIERARCHY_LEVELS["Staff"])


# ---------------------------------------------------------------------------
# Division classification
# ---------------------------------------------------------------------------
def classify_division(title: str) -> str:
    """Classify a job title into a functional division.

    Checks title_overrides first, then scores division keywords.
    """
    if not title:
        return "General"

    cleaned = clean_title(title)
    if not cleaned:
        return "General"

    # --- 1. Exact override lookup ---
    cleaned_lower = cleaned.lower()
    override = _TITLE_OVERRIDES.get(cleaned_lower)
    if override and "division" in override:
        return override["division"]

    # --- 2. Keyword scoring ---
    # Merge pipe/slash separators for keyword matching
    title_lower = cleaned.replace("|", " ").replace("/", " ").lower()

    scores = {}
    for division, keywords in DIVISION_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            kw_lower = keyword.lower()
            if len(kw_lower) <= 3:
                if re.search(r'\b' + re.escape(kw_lower) + r'\b', title_lower):
                    score += len(keyword) + 5
            else:
                if kw_lower in title_lower:
                    score += len(keyword)
        if score > 0:
            scores[division] = score

    if scores:
        return max(scores, key=scores.get)

    return "General"


# ---------------------------------------------------------------------------
# Combined classification
# ---------------------------------------------------------------------------
def classify_title(title: str) -> dict:
    """Fully classify a job title.

    Returns dict with role_level, role_weight, division.
    """
    level, weight = classify_role_level(title)
    division = classify_division(title)
    return {"role_level": level, "role_weight": weight, "division": division}


def get_hierarchy_order() -> list:
    """Get hierarchy levels ordered from most senior to least."""
    return sorted(HIERARCHY_LEVELS.keys(), key=lambda x: HIERARCHY_LEVELS[x], reverse=True)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
