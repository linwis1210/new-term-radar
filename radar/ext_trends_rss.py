"""Linwis free signal: Google Trends daily hot searches RSS (multi-geo), AI-filtered."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .ext_common import ai_related, http_get_text, term_row

GEOS = ["US", "GB", "IN", "JP", "SG", "DE", "BR", "AU", "CA"]
RSS = "https://trends.google.com/trending/rss?geo={geo}"
HT = {"ht": "https://trends.google.com/trending/rss"}
TRAFFIC_RE = re.compile(r"([\d,]+)\+?")


def _traffic(text: str) -> int:
    m = TRAFFIC_RE.search(text or "")
    if not m:
        return 0
    return int(m.group(1).replace(",", ""))


def fetch_trends_rss(cfg: dict | None = None) -> dict:
    """Merge daily Trends RSS across GEOS, dedupe, keep AI-tool-related titles."""
    geos = list((cfg or {}).get("linwis_ext", {}).get("trends_geos") or GEOS)
    merged: dict[str, dict] = {}
    errors = []
    for geo in geos:
        try:
            raw = http_get_text(RSS.format(geo=geo), timeout=25)
            root = ET.fromstring(raw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{geo}: {type(exc).__name__}")
            continue
        for item in root.findall("./channel/item"):
            title_el = item.find("title")
            title = " ".join((title_el.text or "").split()) if title_el is not None else ""
            if not title:
                continue
            traf_el = item.find("ht:approx_traffic", HT)
            traffic = _traffic(traf_el.text if traf_el is not None else "")
            key = title.lower()
            row = merged.setdefault(key, {"term": title, "traffic": 0, "geos": [], "examples": []})
            row["traffic"] = max(row["traffic"], traffic)
            if geo not in row["geos"]:
                row["geos"].append(geo)
            row["examples"].append(f"{geo}:{traffic}+")

    ai_rows = [r for r in merged.values() if ai_related(r["term"])]
    ai_rows.sort(key=lambda r: (-r["traffic"], -len(r["geos"])))
    terms = [
        term_row(
            r["term"],
            note=f"Trends RSS {r['traffic']}+ ({','.join(r['geos'][:4])})",
            examples=r["examples"][:6],
            recent=r["traffic"] or len(r["geos"]),
            geos=r["geos"],
            traffic=r["traffic"],
        )
        for r in ai_rows
    ]
    out = {"terms": terms[:30], "rows": ai_rows[:40], "geos": geos, "scanned": len(merged)}
    if errors:
        out["errors"] = errors
        if not merged:
            out["error"] = "; ".join(errors[:4])
    return out
