"""Linwis free signal: Product Hunt recent launches via the public Atom feed."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .ext_common import ai_related, http_get_text, term_row

FEED = "https://www.producthunt.com/feed"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _text(el) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def fetch_ph(cfg: dict | None = None) -> dict:
    """Return {terms, rows, error?} for AI-related Product Hunt entries."""
    del cfg
    try:
        raw = http_get_text(FEED, timeout=30)
        root = ET.fromstring(raw)
    except Exception as exc:  # noqa: BLE001
        return {"terms": [], "rows": [], "error": f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"}

    rows = []
    for entry in root.findall("a:entry", ATOM):
        title = _text(entry.find("a:title", ATOM))
        summary = _text(entry.find("a:summary", ATOM)) or _text(entry.find("a:content", ATOM))
        link_el = entry.find("a:link", ATOM)
        href = (link_el.get("href") if link_el is not None else "") or ""
        published = _text(entry.find("a:published", ATOM))
        blob = f"{title} {summary}"
        if not ai_related(blob):
            continue
        # Product name is usually before an em-dash / hyphen tagline.
        name = title
        for sep in (" — ", " – ", " - "):
            if sep in title:
                name = title.split(sep, 1)[0].strip()
                break
        rows.append({
            "name": name,
            "title": title,
            "summary": summary[:240],
            "url": href,
            "published": published,
        })

    terms, seen = [], set()
    for r in rows:
        term = " ".join(r["name"].split()).lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term_row(
            term,
            note="Product Hunt",
            examples=[f"{r['title']}: {r['summary'][:120]} {r['url']}"],
            recent=1,
            url=r["url"],
        ))
    return {"terms": terms[:25], "rows": rows[:40]}
