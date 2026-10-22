"""Linwis free signal: Steam search for AI-related new/hot apps (filter pure games)."""
from __future__ import annotations

import json
import re

from .ext_common import http_get_text, steam_ai_toolish, term_row

# Specials/new+AI flavoured search; public store endpoint, no key.
SEARCH = (
    "https://store.steampowered.com/search/results/"
    "?query=&start=0&count=40&dynamic_data=&sort_by=Released_DESC"
    "&snr=1_7_7_151_150&filter=popularnew&infinite=1&term=AI"
)
APP_RE = re.compile(
    r'href="(https://store\.steampowered\.com/app/(\d+)/[^"?]+)'
    r'[^>]*>.*?<span class="title">([^<]+)</span>',
    re.I | re.S,
)
# Simpler fallback: app links + titles from results_html.
HREF_RE = re.compile(
    r'href="(https://store\.steampowered\.com/app/\d+/[^"?]+).*?data-ds-appid="(\d+)".*?'
    r'class="title">\s*([^<]+)\s*<',
    re.I | re.S,
)
ALT_RE = re.compile(
    r'data-ds-appid="(\d+)"[^>]*>[\s\S]*?class="title">\s*([^<]+)\s*<',
    re.I,
)


def _parse_results_html(html: str) -> list[dict]:
    rows = []
    seen = set()
    for m in ALT_RE.finditer(html or ""):
        appid, title = m.group(1), " ".join(m.group(2).split())
        if appid in seen:
            continue
        seen.add(appid)
        rows.append({
            "appid": appid,
            "title": title,
            "url": f"https://store.steampowered.com/app/{appid}/",
        })
    return rows


def fetch_steam(cfg: dict | None = None) -> dict:
    """Return AI-tool-ish Steam apps; skip pure traditional games."""
    del cfg
    try:
        raw = http_get_text(SEARCH, timeout=40)
        try:
            payload = json.loads(raw)
            html = payload.get("results_html") or ""
        except json.JSONDecodeError:
            html = raw
        apps = _parse_results_html(html)
    except Exception as exc:  # noqa: BLE001
        return {"terms": [], "rows": [], "error": f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"}

    kept = [a for a in apps if steam_ai_toolish(a["title"])]
    terms, seen = [], set()
    for a in kept:
        term = a["title"].lower()
        if term in seen:
            continue
        seen.add(term)
        terms.append(term_row(
            term,
            note="Steam AI search",
            examples=[f"{a['title']} {a['url']}"],
            recent=1,
            url=a["url"],
            appid=a["appid"],
        ))
    return {"terms": terms[:25], "rows": kept[:40], "scanned": len(apps)}
