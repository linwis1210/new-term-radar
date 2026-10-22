"""Independent Markdown renderer for Linwis extension signals + SEO gate (简体中文)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SIG_LABEL = {
    "hn": "Hacker News / Show HN",
    "ph": "Product Hunt",
    "steam": "Steam AI",
    "trends_rss": "Google Trends RSS",
    "monid_reddit": "Reddit (Monid)",
    "monid_tiktok": "TikTok (Monid)",
    "seo_gate": "建站四关",
}


def _state(block: dict) -> str:
    if not block:
        return "—"
    if block.get("skipped"):
        return "跳过" + (f"（{block.get('error')}）" if block.get("error") else "")
    if block.get("error"):
        return f"错误：{block['error']}"
    n = len(block.get("terms") or block.get("candidates") or [])
    return f"OK · {n} 条"


def _cost_line(blocks: dict[str, dict]) -> str:
    total = 0.0
    parts = []
    for k in ("monid_reddit", "monid_tiktok"):
        b = blocks.get(k) or {}
        c = float(b.get("cost_usd") or 0)
        if c:
            parts.append(f"{SIG_LABEL.get(k, k)} ${c:.4f}")
        total += c
    if not parts:
        return "本轮 Monid 花费：无（或已跳过）。"
    return f"本轮 Monid 花费：{' + '.join(parts)} = **${total:.4f}**。"


def render(blocks: dict[str, dict], *, when: datetime | None = None, title: str | None = None) -> str:
    """Full Linwis Markdown report in 简体中文."""
    tz = ZoneInfo("Asia/Singapore")
    now = when or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    stamp = now.strftime("%Y-%m-%d %H:%M")
    lines = [
        title or f"# 新词雷达 · Linwis 扩展 · {stamp}（新加坡时间，UTC+8）",
        "",
        "面向 **linwis**（SEO 新词建站，AI 工具相关）。本报告只含扩展信号与建站四关，不含需 AIsa 的 X/usecases。",
        "",
        "## 来源状态",
        "",
        "| 来源 | 状态 | 说明 |",
        "|------|------|------|",
    ]
    for key in ("trends_rss", "hn", "ph", "steam", "monid_reddit", "monid_tiktok", "seo_gate"):
        b = blocks.get(key) or {}
        extra = ""
        if b.get("errors"):
            extra = "; ".join(b["errors"][:2])
        elif key != "seo_gate" and b.get("terms"):
            extra = ", ".join(t["term"] for t in b["terms"][:5])
        elif key == "seo_gate":
            extra = f"入选 {len(b.get('candidates') or [])} · 排除 {len(b.get('excluded') or [])}"
        lines.append(f"| {SIG_LABEL.get(key, key)} | {_state(b)} | {extra or '—'} |")

    gate = blocks.get("seo_gate") or {}
    cands = gate.get("candidates") or []
    lines += ["", "## 一、建站候选（四关全过）", ""]
    if not cands:
        lines.append("本轮没有词同时过四项。宁缺毋滥。")
    else:
        lines += ["| 词 | 来源 | 理由 | 长尾 | 域名 | 接近词 |",
                  "|----|------|------|------|------|--------|"]
        for c in cands:
            dom = ", ".join(
                f"{d['domain']}({d['status']})" for d in (c.get("domains") or [])[:3]
            ) or "—"
            tails = ", ".join((c.get("long_tails") or [])[:5])
            src = ",".join(c.get("sources") or [])
            near = ", ".join(c.get("near") or []) or "—"
            lines.append(
                f"| **{c['term']}** | {src} | {c.get('reason', '')} | {tails} | {dom} | {near} |"
            )
            if c.get("long_tails"):
                lines.append("")
                lines.append(f"- **{c['term']}** 长尾：" + "；".join(c["long_tails"]))

    excl = gate.get("excluded") or []
    lines += ["", "## 二、接近入选但被排除", ""]
    if not excl:
        lines.append("无。")
    else:
        lines += ["| 词 | 来源 | 原因 |", "|----|------|------|"]
        for e in excl[:25]:
            lines.append(
                f"| {e.get('term', '')} | {','.join(e.get('sources') or [])} | {e.get('reason', '')} |"
            )

    lines += ["", "## 三、花费与方法", "", _cost_line(blocks),
              "", "SERP 无 GoAnyAPI/AIsa 时用轻量公开抓取，失败则标 `serp: unchecked`；域名用 Verisign RDAP（404=可注册）。",
              ""]
    return "\n".join(lines)


def append_section(blocks: dict[str, dict]) -> str:
    """Short section to append under the upstream daily report when linwis_ext.enabled."""
    if not blocks:
        return ""
    gate = blocks.get("seo_gate") or {}
    n = len(gate.get("candidates") or [])
    lines = ["", "---", "", "## Linwis 扩展（fork）", "",
             f"建站候选 {n} 个。详情见扩展信号块。", ""]
    for key in ("hn", "ph", "steam", "trends_rss", "monid_reddit", "monid_tiktok"):
        b = blocks.get(key)
        if not b:
            continue
        lines.append(f"- {SIG_LABEL.get(key, key)}：{_state(b)}")
    if gate:
        lines.append(f"- 建站四关：{_state(gate)}")
    lines.append("")
    return "\n".join(lines)
