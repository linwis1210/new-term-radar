"""Linwis free signal: Hacker News / Show HN via the public Firebase API."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ext_common import ai_related, http_get_text, term_row

FIREBASE = "https://hacker-news.firebaseio.com/v0"
TOP_N = 40
SHOW_N = 30
MIN_SCORE = 5
SHOW_RE = re.compile(r"^show\s+hn\s*:\s*", re.I)


def _item(item_id: int) -> dict | None:
    try:
        raw = http_get_text(f"{FIREBASE}/item/{item_id}.json", timeout=20)
        return json.loads(raw) if raw and raw != "null" else None
    except Exception:  # noqa: BLE001
        return None


def _ids(kind: str, limit: int) -> list[int]:
    data = json.loads(http_get_text(f"{FIREBASE}/{kind}.json", timeout=20))
    return list(data or [])[:limit]


def _title_term(title: str) -> str:
    t = SHOW_RE.sub("", title or "").strip()
    # Prefer the product-ish head before a dash/colon.
    for sep in (" – ", " — ", " - ", ": "):
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    return " ".join(t.split())[:80]


def fetch_hn(cfg: dict | None = None) -> dict:
    """Return {terms, rows, error?} of AI-tool-related HN / Show HN stories."""
    del cfg  # reserved for future knobs
    try:
        top_ids = _ids("topstories", TOP_N)
        show_ids = _ids("showstories", SHOW_N)
    except Exception as exc:  # noqa: BLE001
        return {"terms": [], "rows": [], "error": f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"}

    wanted = [(i, "top") for i in top_ids] + [(i, "show") for i in show_ids]
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(_item, i): kind for i, kind in wanted}
        for fut in as_completed(futs):
            kind = futs[fut]
            it = fut.result()
            if not it or it.get("type") not in ("story", None):
                continue
            title = it.get("title") or ""
            score = int(it.get("score") or 0)
            if score < MIN_SCORE:
                continue
            blob = f"{title} {it.get('url') or ''} {it.get('text') or ''}"
            if not ai_related(blob) and not SHOW_RE.match(title):
                continue
            if SHOW_RE.match(title) and not ai_related(blob):
                # Keep Show HN only when AI-related.
                continue
            if not ai_related(blob):
                continue
            items.append({
                "id": it.get("id"),
                "title": title,
                "score": score,
                "url": it.get("url") or f"https://news.ycombinator.com/item?id={it.get('id')}",
                "kind": "show" if SHOW_RE.match(title) or kind == "show" else "top",
                "descendants": int(it.get("descendants") or 0),
            })

    items.sort(key=lambda r: -r["score"])
    terms, seen = [], set()
    for it in items:
        term = _title_term(it["title"]).lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term_row(
            term,
            note=f"HN {it['kind']}: {it['score']} pts",
            examples=[f"{it['title']} ({it['score']}) {it['url']}"],
            recent=it["score"],
            url=it["url"],
            hn_id=it["id"],
        ))
    return {"terms": terms[:25], "rows": items[:40], "fetched": len(wanted)}
