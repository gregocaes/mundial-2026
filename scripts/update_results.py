#!/usr/bin/env python3
"""
Mundial 2026 — scrape Wikipedia for match results and update data.json.

Strategy
--------
- For each Group A-L, fetch the wikitext of the dedicated article
  (2026 FIFA World Cup Group X).
- Find every {{Football box}} (or similar) template inside.
- Extract team1, team2, score, scorers.
- Map team names → 3-letter codes used in our data.json.
- Write into data.json["liveResults"] keyed by "<group>-<sortedPair>".
- For knockouts, parse the main "2026 FIFA World Cup knockout stage"
  article (key prefix "KO-<sortedPair>").

The JS in index.html merges liveResults with localStorage on load, so
scores appear without any manual entry. Synthetic dates/matchdays stay
(they will be replaced in a later iteration).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "mundial-2026-tracker/1.0 (https://github.com/; auto-update)"
TIMEOUT = 30

# Map Wikipedia names → our 3-letter codes
TEAM_NAME_TO_CODE: dict[str, str] = {
    # Pot 1
    "Mexico":         "MEX", "México":         "MEX",
    "Canada":         "CAN", "Canadá":         "CAN",
    "United States":  "USA",
    "Argentina":      "ARG",
    "Brazil":         "BRA", "Brasil":         "BRA",
    "Spain":          "ESP", "España":         "ESP",
    "France":         "FRA", "Francia":        "FRA",
    "England":        "ENG", "Inglaterra":     "ENG",
    "Portugal":       "POR",
    "Germany":        "GER", "Alemania":       "GER",
    "Netherlands":    "NED", "Países Bajos":   "NED",
    "Belgium":        "BEL", "Bélgica":        "BEL",
    # Pot 2
    "Croatia":        "CRO", "Croacia":        "CRO",
    "Uruguay":        "URU",
    "Morocco":        "MAR", "Marruecos":      "MAR",
    "Japan":          "JPN", "Japón":          "JPN",
    "South Korea":    "KOR", "Korea Republic": "KOR",
    "Egypt":          "EGY", "Egipto":         "EGY",
    "Colombia":       "COL",
    "Ecuador":        "ECU",
    "Senegal":        "SEN",
    "Iran":           "IRN", "IR Iran":        "IRN",
    "Switzerland":    "SUI", "Suiza":          "SUI",
    "Australia":      "AUS",
    # Pot 3
    "Tunisia":        "TUN", "Túnez":          "TUN",
    "Ivory Coast":    "CIV", "Côte d'Ivoire":  "CIV",
    "Austria":        "AUT",
    "Turkey":         "TUR", "Türkiye":        "TUR", "Turquía": "TUR",
    "Algeria":        "ALG", "Argelia":        "ALG",
    "Norway":         "NOR", "Noruega":        "NOR",
    "South Africa":   "RSA", "Sudáfrica":      "RSA",
    "Scotland":       "SCO", "Escocia":        "SCO",
    "Paraguay":       "PAR",
    "Ghana":          "GHA",
    "Panama":         "PAN", "Panamá":         "PAN",
    "Czech Republic": "CZE", "Chequia":        "CZE", "Czechia": "CZE",
    # Pot 4
    "Uzbekistan":     "UZB",
    "Saudi Arabia":   "KSA", "Arabia Saudí":   "KSA",
    "Qatar":          "QAT", "Catar":          "QAT",
    "New Zealand":    "NZL", "Nueva Zelanda":  "NZL",
    "Bosnia and Herzegovina": "BIH",
    "Jordan":         "JOR", "Jordania":       "JOR",
    "Iraq":           "IRQ", "Irak":           "IRQ",
    "Haiti":          "HAI", "Haití":          "HAI",
    "Sweden":         "SWE", "Suecia":         "SWE",
    "Curaçao":        "CUW", "Curacao":        "CUW",
    "Cape Verde":     "CPV", "Cabo Verde":     "CPV",
    "DR Congo":       "COD", "Democratic Republic of the Congo": "COD",
}

VALID_CODES = set(TEAM_NAME_TO_CODE.values())

GROUPS = list("ABCDEFGHIJKL")


# ---------- Wikipedia API ----------

def fetch_wikitext(page_title: str) -> Optional[str]:
    """Return the raw wikitext of a Wikipedia article, or None if not found."""
    try:
        r = requests.get(
            WIKI_API,
            params={
                "action": "parse",
                "page": page_title,
                "prop": "wikitext",
                "format": "json",
                "formatversion": 2,
                "redirects": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        return data.get("parse", {}).get("wikitext")
    except Exception as e:
        print(f"  ! fetch error for {page_title}: {e}", file=sys.stderr)
        return None


# ---------- Template parsing ----------

FOOTBALL_BOX_NAMES = {
    "football box", "footballbox", "football box collapsible",
    "footballboxcollapsible", "football box-final",
    "#invoke:football box",  # modern Lua-module-based invocation
}


def find_football_boxes(wikitext: str) -> list[str]:
    """Extract every {{Football box ...}} template block (including nested braces)."""
    boxes: list[str] = []
    i = 0
    n = len(wikitext)
    while i < n - 1:
        if wikitext[i:i + 2] != "{{":
            i += 1
            continue
        # Read template name until pipe, newline, or closing braces
        j = i + 2
        while j < n and wikitext[j] not in "|\n}":
            j += 1
        name = wikitext[i + 2:j].strip().lower()
        if name not in FOOTBALL_BOX_NAMES:
            i += 2
            continue
        # Find matching }} with brace-depth tracking
        depth = 1
        k = j
        while k < n - 1 and depth > 0:
            two = wikitext[k:k + 2]
            if two == "{{":
                depth += 1
                k += 2
            elif two == "}}":
                depth -= 1
                k += 2
                if depth == 0:
                    boxes.append(wikitext[i:k])
                    break
            else:
                k += 1
        i = k if depth == 0 else i + 2
    return boxes


def parse_template_fields(template: str) -> dict[str, str]:
    """
    Parse a template into a dict of named fields.
    Handles nested templates and links within values.
    """
    # Strip outer {{ and }}
    inner = template[2:-2]
    fields: dict[str, str] = {}
    # Split into parts at top-level pipes only
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        nxt = inner[i + 1] if i + 1 < len(inner) else ""
        if ch == "{" and nxt == "{":
            depth += 1
            buf.append(ch); buf.append(nxt); i += 2; continue
        if ch == "}" and nxt == "}":
            depth -= 1
            buf.append(ch); buf.append(nxt); i += 2; continue
        if ch == "[" and nxt == "[":
            depth += 1
            buf.append(ch); buf.append(nxt); i += 2; continue
        if ch == "]" and nxt == "]":
            depth -= 1
            buf.append(ch); buf.append(nxt); i += 2; continue
        if ch == "|" and depth == 0:
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(ch); i += 1
    parts.append("".join(buf))

    # First part is the template name (ignored)
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            fields[key.strip()] = value.strip()
    return fields


# ---------- Field interpreters ----------

def strip_wiki_markup(text: str) -> str:
    """Quick-and-dirty cleanup of wikitext to plain string."""
    if not text:
        return ""
    # [[Foo|Bar]] → Bar ; [[Foo]] → Foo
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", text)
    # {{flagicon|XXX}} or {{fb|XXX}} → XXX
    text = re.sub(r"\{\{[a-zA-Z\s]*\|([^}|]+)(?:\|[^}]*)?\}\}", r"\1", text)
    # Strip remaining templates and HTML tags
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def name_to_code(raw: str) -> Optional[str]:
    """Resolve a raw team string from Wikipedia into a 3-letter code."""
    if not raw:
        return None
    # Direct 3-letter code embedded?
    m = re.search(r"\b([A-Z]{3})\b", raw)
    if m and m.group(1) in VALID_CODES:
        return m.group(1)
    cleaned = strip_wiki_markup(raw)
    # Exact match
    if cleaned in TEAM_NAME_TO_CODE:
        return TEAM_NAME_TO_CODE[cleaned]
    # Substring match (longest first to avoid 'Korea' matching prematurely)
    for name in sorted(TEAM_NAME_TO_CODE.keys(), key=len, reverse=True):
        if name.lower() in cleaned.lower():
            return TEAM_NAME_TO_CODE[name]
    return None


SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[–\-]\s*(\d{1,2})(?!\d)")


def parse_score(raw: str) -> Optional[tuple[int, int]]:
    """
    Parse a score from the raw 'score' field. The score may be the
    final value of a {{score link}} template (e.g. '0–2'), or a raw
    'M–N' string. Returns None for placeholders like 'Match 1' (no
    digit-dash-digit pattern) and for canceled/walkover entries.
    """
    if not raw:
        return None
    # Pull the rightmost positional arg of {{score link|...|0–2}} if present
    candidates: list[str] = [raw]
    for m in re.finditer(r"\{\{[^{}]*\}\}", raw):
        tpl = m.group(0)
        parts = tpl.strip("{}").split("|")
        if parts:
            candidates.append(parts[-1])
    # Search every candidate for a digit-dash-digit pattern
    for c in candidates:
        m = SCORE_RE.search(c)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


GOAL_RE = re.compile(
    r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\][^{[]*?\{\{goal\|(\d+)",
    re.IGNORECASE,
)


def parse_goals(raw: str, team_code: str) -> list[dict]:
    """Extract a list of scorer dicts from a goals1/goals2 field."""
    if not raw:
        return []
    goals: list[dict] = []
    for m in GOAL_RE.finditer(raw):
        player = m.group(1).strip()
        minute = int(m.group(2))
        goals.append({"player": player, "team": team_code, "minute": minute})
    # Fallback: simpler pattern "Player NN'"
    if not goals:
        simple = re.findall(r"([\w\sÀ-ÿ'\-\.]+?)\s+(\d{1,3})['′]", strip_wiki_markup(raw))
        for player, minute in simple:
            p = player.strip()
            if p and len(p) > 1:
                goals.append({"player": p, "team": team_code, "minute": int(minute)})
    return goals


# ---------- Main extraction ----------

def extract_matches_from_page(wikitext: str, stage: str, group: Optional[str] = None) -> list[dict]:
    """Pull every Football box from a wikitext page and convert it to our format."""
    matches: list[dict] = []
    for box in find_football_boxes(wikitext):
        fields = parse_template_fields(box)
        team1 = name_to_code(fields.get("team1", "") or fields.get("home", ""))
        team2 = name_to_code(fields.get("team2", "") or fields.get("away", ""))
        if not team1 or not team2:
            continue
        score = parse_score(fields.get("score", ""))
        match = {
            "stage": stage,
            "group": group,
            "home": team1,
            "away": team2,
        }
        if score is not None:
            match["homeGoals"], match["awayGoals"] = score
            match["played"] = True
            match["scorers"] = (
                parse_goals(fields.get("goals1", ""), team1)
                + parse_goals(fields.get("goals2", ""), team2)
            )
        else:
            match["played"] = False
        matches.append(match)
    return matches


def main() -> int:
    data_path = Path("data.json")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    live: dict[str, dict] = {}

    # Group stage
    for letter in GROUPS:
        title = f"2026 FIFA World Cup Group {letter}"
        wt = fetch_wikitext(title)
        if wt is None:
            print(f"Group {letter}: page not found, skipping", file=sys.stderr)
            continue
        matches = extract_matches_from_page(wt, "group", letter)
        played = sum(1 for m in matches if m.get("played"))
        print(f"Group {letter}: {len(matches)} matches, {played} played")
        for m in matches:
            if not m.get("played"):
                continue
            a, b = sorted([m["home"], m["away"]])
            key = f"{letter}-{a}-{b}"
            live[key] = {
                "home": m["home"], "away": m["away"],
                "homeGoals": m["homeGoals"], "awayGoals": m["awayGoals"],
                "scorers": m.get("scorers", []),
            }

    # Knockout stage (one consolidated article)
    ko_title = "2026 FIFA World Cup knockout stage"
    wt = fetch_wikitext(ko_title)
    if wt is not None:
        matches = extract_matches_from_page(wt, "knockout")
        played = sum(1 for m in matches if m.get("played"))
        print(f"Knockout: {len(matches)} matches, {played} played")
        for m in matches:
            if not m.get("played"):
                continue
            a, b = sorted([m["home"], m["away"]])
            key = f"KO-{a}-{b}"
            live[key] = {
                "home": m["home"], "away": m["away"],
                "homeGoals": m["homeGoals"], "awayGoals": m["awayGoals"],
                "scorers": m.get("scorers", []),
            }
    else:
        print("Knockout page not found yet (normal until late June)")

    # Write back
    data["liveResults"] = live
    data["tournament"]["lastAutoUpdate"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nTotal live results written: {len(live)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
