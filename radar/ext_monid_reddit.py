"""Linwis Monid signal: Reddit hot posts via monid anyapi /reddit.subreddit_posts."""
from __future__ import annotations

from pathlib import Path

from .ext_common import ai_related, monid_cost_usd, monid_run, monid_which, term_row

DEFAULT_SUBS = [
    "SideProject", "artificial", "LocalLLaMA", "singularity", "StableDiffusion",
    "aivideo", "MachineLearning", "ChatGPT", "OpenAI", "technology", "InternetIsBeautiful",
]


def fetch_monid_reddit(cfg: dict | None = None, state: Path | None = None) -> dict:
    """Fetch hot posts from configured subreddits. Skip gracefully without monid."""
    if not monid_which():
        return {"terms": [], "rows": [], "skipped": True, "error": "monid CLI not found"}

    lx = (cfg or {}).get("linwis_ext") or {}
    subs = list(lx.get("reddit_subs") or DEFAULT_SUBS)
    limit = int(lx.get("reddit_limit") or 15)
    wait = int(lx.get("monid_wait") or 30)
    out_dir = None
    if state is not None:
        out_dir = Path(state) / "linwis_monid" / "reddit"
        out_dir.mkdir(parents=True, exist_ok=True)

    rows, terms_map, errors = [], {}, []
    cost = 0.0
    for sub in subs:
        body = {"subreddit": sub, "sort": "hot", "limit": limit, "route": "badger"}
        path = (out_dir / f"{sub}.json") if out_dir else None
        try:
            run = monid_run("/reddit.subreddit_posts", body, wait=wait, out_path=path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sub}: {type(exc).__name__}: {' '.join(str(exc).split())[:100]}")
            continue
        cost += monid_cost_usd(run)
        if run.get("status") and run.get("status") != "COMPLETED":
            errors.append(f"{sub}: status={run.get('status')}")
            continue
        posts = ((run.get("output") or {}).get("data") or {}).get("posts") or []
        for p in posts:
            title = " ".join(str(p.get("title") or "").split())
            text = " ".join(str(p.get("selftext") or "").split())[:400]
            blob = f"{title} {text}"
            if not ai_related(blob):
                continue
            url = "https://www.reddit.com" + (p.get("permalink") or "")
            row = {
                "subreddit": sub,
                "title": title,
                "score": int(p.get("score") or 0),
                "comments": int(p.get("numComments") or p.get("num_comments") or 0),
                "url": url,
                "id": p.get("id") or "",
            }
            rows.append(row)
            # Term: first meaningful chunk of title.
            term = title.lower()
            for sep in (" — ", " – ", " - ", ": ", " | "):
                if sep in term:
                    term = term.split(sep, 1)[0].strip()
                    break
            term = " ".join(term.split())[:80]
            if not term:
                continue
            g = terms_map.setdefault(term, term_row(
                term, note=f"r/{sub}", examples=[], recent=0, urls=[]))
            g["recent"] = max(g["recent"], row["score"])
            g["examples"].append(f"r/{sub} ({row['score']}): {title[:100]}")
            g["urls"].append(url)
            g["note"] = f"Reddit r/{sub} score={row['score']}"

    terms = sorted(terms_map.values(), key=lambda r: -r["recent"])[:40]
    out = {"terms": terms, "rows": rows[:80], "cost_usd": round(cost, 6),
           "subs": subs, "cost_micros": int(round(cost * 1e6))}
    if errors:
        out["errors"] = errors
        if not rows and not terms:
            out["error"] = "; ".join(errors[:3])
    return out
