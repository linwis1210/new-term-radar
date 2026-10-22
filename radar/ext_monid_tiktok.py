"""Linwis Monid signal: TikTok trending hashtags + US feed; AI-tool filter. No Instagram."""
from __future__ import annotations

from pathlib import Path

from .ext_common import ai_related, monid_cost_usd, monid_run, monid_which, term_row

DEFAULT_REGIONS = ["US", "SG", "GB"]
DEFAULT_INDUSTRIES = ["tech_electronics", "games", "education"]


def fetch_monid_tiktok(cfg: dict | None = None, state: Path | None = None) -> dict:
    if not monid_which():
        return {"terms": [], "rows": [], "skipped": True, "error": "monid CLI not found"}

    lx = (cfg or {}).get("linwis_ext") or {}
    regions = list(lx.get("tiktok_regions") or DEFAULT_REGIONS)
    industries = list(lx.get("tiktok_industries") or DEFAULT_INDUSTRIES)
    period = int(lx.get("tiktok_period") or 7)
    limit = int(lx.get("tiktok_hashtag_limit") or 3)
    wait = int(lx.get("monid_wait") or 30)
    out_dir = None
    if state is not None:
        out_dir = Path(state) / "linwis_monid" / "tiktok"
        out_dir.mkdir(parents=True, exist_ok=True)

    rows, errors = [], []
    cost = 0.0

    # Hashtags: region × industry (limit kept small for cost).
    for region in regions:
        for industry in industries:
            body = {
                "region": region,
                "industry": industry,
                "period": period,
                "limit": limit,
            }
            # AnyAPI field names vary; also try country/countryCode aliases in one call shape.
            # Primary shape used in prior linwis runs:
            body = {
                "country": region,
                "industry": industry,
                "period": period,
                "limit": limit,
            }
            label = f"{region}-{industry}"
            path = (out_dir / f"hashtags_{label}.json") if out_dir else None
            try:
                run = monid_run("/tiktok.trending_hashtags", body, wait=wait, out_path=path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"hashtags {label}: {type(exc).__name__}")
                continue
            cost += monid_cost_usd(run)
            data = (run.get("output") or {}).get("data") or {}
            items = data.get("items") or data.get("hashtags") or data.get("list") or []
            if isinstance(data, list):
                items = data
            for it in items:
                if not isinstance(it, dict):
                    continue
                tag = str(it.get("hashtag") or it.get("name") or it.get("title") or "").lstrip("#")
                if not tag:
                    continue
                blob = f"{tag} {it.get('industry') or ''} {industry}"
                rows.append({
                    "kind": "hashtag",
                    "tag": tag,
                    "region": region,
                    "industry": industry,
                    "rank": it.get("rank"),
                    "posts": it.get("posts"),
                    "ai": ai_related(blob),
                })

    # Feed: US only.
    path = (out_dir / "feed_US.json") if out_dir else None
    try:
        run = monid_run("/tiktok.trending_feed", {"country": "US", "limit": 10}, wait=wait, out_path=path)
        cost += monid_cost_usd(run)
        data = (run.get("output") or {}).get("data") or {}
        items = data.get("items") or data.get("videos") or data.get("list") or []
        if isinstance(data, list):
            items = data
        for it in items:
            if not isinstance(it, dict):
                continue
            desc = " ".join(str(it.get("desc") or it.get("title") or it.get("description") or "").split())
            tags = it.get("hashtags") or it.get("challenges") or []
            tag_txt = " ".join(
                (t.get("title") if isinstance(t, dict) else str(t)) for t in (tags or [])
            )
            blob = f"{desc} {tag_txt}"
            rows.append({
                "kind": "feed",
                "desc": desc[:200],
                "tags": tag_txt,
                "region": "US",
                "ai": ai_related(blob),
                "url": it.get("share_url") or it.get("url") or "",
            })
    except Exception as exc:  # noqa: BLE001
        errors.append(f"feed US: {type(exc).__name__}")

    ai_rows = [r for r in rows if r.get("ai")]
    terms_map = {}
    for r in ai_rows:
        if r["kind"] == "hashtag":
            term = r["tag"].lower()
            note = f"TikTok #{r['tag']} {r['region']}/{r['industry']}"
            ex = [note]
        else:
            term = (r.get("desc") or r.get("tags") or "")[:60].lower()
            note = "TikTok feed US"
            ex = [r.get("desc") or ""]
        if not term:
            continue
        g = terms_map.setdefault(term, term_row(term, note=note, examples=[], recent=1))
        g["examples"].extend(ex)
        g["note"] = note

    out = {
        "terms": list(terms_map.values())[:30],
        "rows": ai_rows[:60],
        "scanned": len(rows),
        "cost_usd": round(cost, 6),
        "cost_micros": int(round(cost * 1e6)),
    }
    if errors:
        out["errors"] = errors
        if not ai_rows and not terms_map:
            # Still success with empty AI filter — only error if nothing fetched.
            if not rows:
                out["error"] = "; ".join(errors[:3])
    return out
