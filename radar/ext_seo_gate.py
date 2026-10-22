"""Linwis SEO four-gate: new+rising, AI-tool, SERP empty-ish, long-tail + RDAP .com check.

First version: no AIsa. SERP uses a light public fetch or marks serp: unchecked.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import UA
from .ext_common import AI_NEG, ai_related, http_get

RDAP = "https://rdap.verisign.com/com/v1/domain/{domain}"
# DuckDuckGo HTML is a light public SERP stand-in (no key).
DDG = "https://html.duckduckgo.com/html/?q={q}"

BOLD_RE = re.compile(r"\*\*([^*]{2,60})\*\*")
LIST_RE = re.compile(r"去重[：:]\s*(.+)")
WORD_OK = re.compile(r"^[a-z0-9][a-z0-9 ._+-]{1,48}$", re.I)

LONG_TAIL_TEMPLATES = [
    "{t} ai",
    "{t} tool",
    "{t} api",
    "what is {t}",
    "{t} tutorial",
    "{t} vs",
    "best {t}",
    "{t} open source",
    "how to use {t}",
    "{t} review",
]


def prior_terms(radar_dir: Path | None = None) -> set[str]:
    """Terms already reported in /workspace/radar/*.md (bold names + 去重 lists)."""
    root = Path(radar_dir) if radar_dir else Path("/workspace/radar")
    found: set[str] = set()
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in BOLD_RE.finditer(text):
            found.add(m.group(1).strip().lower())
        for m in LIST_RE.finditer(text):
            for part in re.split(r"[,/|、]", m.group(1)):
                part = part.strip().lower()
                if part:
                    found.add(part)
    return found


def gate1_new_rising(term: str, evidence: dict) -> tuple[bool, str]:
    """真新词且在涨 — heuristic from multi-source / score / traffic."""
    t = term.strip().lower()
    if not t or not WORD_OK.match(t):
        return False, "词形不适合建站"
    if len(t) < 3:
        return False, "过短"
    sources = evidence.get("sources") or []
    score = int(evidence.get("score") or evidence.get("recent") or 0)
    if len(sources) >= 2 or score >= 50 or evidence.get("traffic", 0) >= 200:
        return True, f"多源或热度够（sources={len(sources)}, score={score}）"
    if evidence.get("force_new"):
        return True, "标记为新冒头"
    if len(sources) == 1 and score >= 10:
        return True, f"单源但有热度（{sources[0]}, score={score}）"
    return False, "热度/新意不足"


def gate2_ai_tool(term: str, evidence: dict) -> tuple[bool, str]:
    blob = " ".join([term, evidence.get("blob") or "", " ".join(evidence.get("examples") or [])])
    if AI_NEG.search(blob) and not ai_related(blob):
        return False, "八卦/体育/政治向"
    if ai_related(blob) or evidence.get("ai"):
        return True, "AI 工具相关"
    return False, "看不出 AI 工具属性"


def serp_check(term: str, fetch=None) -> dict:
    """Light SERP check. Returns {status, note, rivals}.

    status: empty | crowded | unchecked | error
    """
    fetch = fetch or _ddg_fetch
    try:
        html = fetch(term)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unchecked", "note": f"serp: unchecked ({type(exc).__name__})", "rivals": []}
    if html is None:
        return {"status": "unchecked", "note": "serp: unchecked", "rivals": []}
    low = html.lower()
    # Crowded if official docs / big properties dominate.
    rivals = []
    for needle, label in (
        ("wikipedia.org", "wikipedia"),
        ("github.com", "github"),
        ("producthunt.com", "producthunt"),
        ("apps.apple.com", "appstore"),
        ("play.google.com", "play"),
    ):
        if needle in low:
            rivals.append(label)
    # Count result-ish links.
    links = len(re.findall(r"uddg=|result__a|class=\"result", low))
    if links == 0 and "duckduckgo" not in low:
        return {"status": "unchecked", "note": "serp: unchecked (no parse)", "rivals": rivals}
    if len(rivals) >= 3 or links > 20:
        return {"status": "crowded", "note": f"前排较满（{', '.join(rivals) or 'many'}）", "rivals": rivals}
    return {"status": "empty", "note": f"前排相对空（rivals={', '.join(rivals) or 'none'}）", "rivals": rivals}


def _ddg_fetch(term: str) -> str:
    url = DDG.format(q=urllib.parse.quote_plus(term))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read().decode("utf-8", errors="replace")


def long_tails(term: str, n: int = 8) -> list[str]:
    t = term.strip().lower()
    out = []
    for tmpl in LONG_TAIL_TEMPLATES:
        phrase = tmpl.format(t=t)
        if phrase not in out:
            out.append(phrase)
        if len(out) >= n:
            break
    return out


def domain_candidates(term: str, n: int = 3) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "", term.lower())
    if not base:
        return []
    cands = [f"{base}.com", f"{base}ai.com", f"get{base}.com", f"{base}app.com", f"try{base}.com"]
    return list(dict.fromkeys(cands))[: max(2, n)]


def rdap_available(domain: str, fetch=None) -> dict:
    """RDAP for .com: 404 → available, 200 → taken."""
    fetch = fetch or _rdap_fetch
    try:
        status, body = fetch(domain)
    except Exception as exc:  # noqa: BLE001
        return {"domain": domain, "status": "error", "note": f"{type(exc).__name__}"}
    if status == 404:
        return {"domain": domain, "status": "available", "note": "RDAP 404 可注册"}
    if status == 200:
        return {"domain": domain, "status": "taken", "note": "已注册"}
    return {"domain": domain, "status": "unknown", "note": f"HTTP {status}"}


def _rdap_fetch(domain: str) -> tuple[int, bytes]:
    url = RDAP.format(domain=domain.lower())
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rdap+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b""


def merge_candidates(blocks: dict[str, dict]) -> list[dict]:
    """Merge terms from extension signal blocks into evidence rows."""
    out: dict[str, dict] = {}
    for src, block in blocks.items():
        if src == "seo_gate" or not isinstance(block, dict):
            continue
        for r in block.get("terms") or []:
            term = (r.get("term") or "").strip().lower()
            if not term:
                continue
            row = out.setdefault(term, {
                "term": term, "sources": [], "examples": [], "score": 0,
                "traffic": 0, "blob": "", "ai": False,
            })
            if src not in row["sources"]:
                row["sources"].append(src)
            row["examples"] += list(r.get("examples") or [])[:2]
            row["score"] = max(row["score"], int(r.get("recent") or 0))
            row["traffic"] = max(row["traffic"], int(r.get("traffic") or 0))
            row["blob"] += " " + " ".join(r.get("examples") or [])
            row["ai"] = row["ai"] or ai_related(term + " " + row["blob"])
    return sorted(out.values(), key=lambda r: (-len(r["sources"]), -r["score"]))


def run_seo_gate(cfg: dict, blocks: dict[str, dict], *,
                 radar_dir: Path | None = None,
                 serp_fetch=None, rdap_fetch=None,
                 check_serp: bool = True, check_rdap: bool = True) -> dict:
    """Apply four gates; return candidates + excluded. Pure-logic friendly via fetch hooks."""
    lx = (cfg or {}).get("linwis_ext") or {}
    if lx.get("seo_gate") is False:
        return {"skipped": True, "candidates": [], "excluded": []}

    prior = prior_terms(radar_dir or lx.get("radar_dir") or "/workspace/radar")
    merged = merge_candidates(blocks)
    candidates, excluded = [], []

    for ev in merged:
        term = ev["term"]
        reasons = []
        if term in prior or any(term in p or p in term for p in prior if len(p) >= 3):
            excluded.append({"term": term, "reason": "已在 /workspace/radar 报告中出现", "sources": ev["sources"]})
            continue

        ok1, why1 = gate1_new_rising(term, ev)
        ok2, why2 = gate2_ai_tool(term, ev)
        reasons += [f"①{why1}", f"②{why2}"]
        if not (ok1 and ok2):
            excluded.append({"term": term, "reason": "; ".join(reasons), "sources": ev["sources"]})
            continue

        if check_serp and lx.get("serp_check", True):
            serp = serp_check(term, fetch=serp_fetch)
        else:
            serp = {"status": "unchecked", "note": "serp: unchecked", "rivals": []}
        reasons.append(f"③{serp['note']}")
        if serp["status"] == "crowded":
            excluded.append({"term": term, "reason": "; ".join(reasons), "sources": ev["sources"], "serp": serp})
            continue

        tails = long_tails(term, n=int(lx.get("long_tail_n") or 8))
        domains = []
        if check_rdap and lx.get("rdap_check", True):
            for d in domain_candidates(term, n=int(lx.get("rdap_n") or 3)):
                domains.append(rdap_available(d, fetch=rdap_fetch))
        else:
            domains = [{"domain": d, "status": "unchecked", "note": "rdap skipped"} for d in domain_candidates(term)]

        # Gate 4: need at least some long tails; domain availability is informational.
        if len(tails) < 5:
            excluded.append({"term": term, "reason": "; ".join(reasons + ["④长尾不足"]), "sources": ev["sources"]})
            continue
        reasons.append(f"④长尾{len(tails)} + RDAP {sum(1 for d in domains if d['status']=='available')}/{len(domains)} 可注册")

        near = [p for p in prior if p and (p in term or term in p)][:5]
        candidates.append({
            "term": term,
            "sources": ev["sources"],
            "reason": "; ".join(reasons),
            "long_tails": tails,
            "domains": domains,
            "near": near,
            "examples": ev["examples"][:3],
            "serp": serp,
        })

    return {
        "candidates": candidates[:20],
        "excluded": excluded[:40],
        "prior": len(prior),
        "scanned": len(merged),
    }
