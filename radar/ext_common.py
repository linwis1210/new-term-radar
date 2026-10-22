"""Shared helpers for Linwis fork free/Monid signals: AI relevance, HTTP, Monid CLI."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import UA

# Positive: writing / image / video / audio / agent / coding / model / API style tools.
AI_POS = re.compile(
    r"\b(ai|a\.i\.|llm|gpt|claude|gemini|mistral|qwen|llama|deepseek|copilot|cursor|"
    r"agent|agents|mcp|rag|embedding|tokenizer|diffusion|stable[\s-]?diffusion|"
    r"midjourney|runway|kling|sora|veo|tts|asr|stt|ocr|whisper|codec|"
    r"codegen|code[\s-]?gen|autocomplete|finetun|fine[\s-]?tun|open[\s-]?source|"
    r"huggingface|hugging[\s-]?face|langchain|llamaindex|vllm|ollama|"
    r"prompt|chatbot|chat[\s-]?bot|generative|multimodal|vision[\s-]?model|"
    r"text[\s-]?to[\s-]?(image|video|speech|audio)|image[\s-]?to[\s-]?(text|video)|"
    r"speech[\s-]?to[\s-]?text|voice[\s-]?clon|lip[\s-]?sync|avatar|"
    r"api\b|sdk\b|inference|benchmark|dataset|transformer)\b",
    re.I,
)

# Exclude gossip / sports scores / politics noise.
AI_NEG = re.compile(
    r"\b(football|soccer|nba|nfl|mlb|nhl|premier league|champions league|world cup|"
    r"election|president|senator|parliament|celebrity|gossip|box[\s-]?office|"
    r"box score|final score|vs\.|versus|transfer window|stock market crash)\b",
    re.I,
)

# Pure traditional games on Steam (keep AI-tool-ish titles).
GAME_ONLY = re.compile(
    r"\b(fps|rpg|roguelike|roguelite|shooter|platformer|metroidvania|mmorpg|"
    r"battle royale|multiplayer shooter|open world adventure)\b",
    re.I,
)

TOOLISH = re.compile(
    r"\b(tool|editor|studio|generator|assistant|agent|api|sdk|plugin|extension|"
    r"workflow|automation|simulator|sandbox for|dev\b|developer)\b",
    re.I,
)


def ai_related(text: str) -> bool:
    """True when text looks like an AI tool / model / agent signal, not sports/politics gossip."""
    if not text or not text.strip():
        return False
    if AI_NEG.search(text) and not AI_POS.search(text):
        return False
    return bool(AI_POS.search(text))


def steam_ai_toolish(text: str) -> bool:
    """Steam: keep AI-related; drop pure traditional games unless they look tool/dev oriented."""
    if not ai_related(text):
        return False
    if GAME_ONLY.search(text) and not TOOLISH.search(text):
        return False
    return True


def http_get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def http_get_text(url: str, timeout: int = 40, encoding: str = "utf-8") -> str:
    return http_get(url, timeout=timeout).decode(encoding, errors="replace")


def monid_which() -> str | None:
    return shutil.which("monid")


def monid_run(endpoint: str, body: dict, wait: int = 30, out_path: Path | None = None) -> dict:
    """Call `monid run` for an AnyAPI endpoint. Returns the run JSON (status/cost/output).

    Writes to out_path when given. Graceful callers should catch Exception.
    Prefer -j on stdout: -o has been unreliable on some CLI builds.
    """
    exe = monid_which()
    if not exe:
        raise FileNotFoundError("monid CLI not found on PATH")
    env = {**os.environ, "NO_COLOR": "1"}
    cmd = [
        exe, "run", "-p", "anyapi", "-e", endpoint,
        "-i", json.dumps(body, ensure_ascii=False),
        "-w", str(wait), "-j",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=wait + 60)
    raw = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(raw or json.dumps({"error": "empty monid output", "returncode": proc.returncode}))
    if not raw:
        raise RuntimeError(f"monid empty output rc={proc.returncode}: {(proc.stderr or '')[:200]}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Some builds return a start payload then need `runs get`.
        raise RuntimeError(f"monid non-JSON: {raw[:200]}") from exc
    if isinstance(data, dict) and data.get("status") in (None, "RUNNING") and data.get("runId"):
        data = monid_runs_get(data["runId"], wait=wait, out_path=out_path)
    return data


def monid_runs_get(run_id: str, wait: int = 30, out_path: Path | None = None) -> dict:
    exe = monid_which()
    if not exe:
        raise FileNotFoundError("monid CLI not found on PATH")
    env = {**os.environ, "NO_COLOR": "1"}
    cmd = [exe, "runs", "get", "-r", run_id, "-w", str(wait), "-j"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=wait + 60)
    raw = (proc.stdout or "").strip()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(raw or "{}")
    if not raw:
        raise RuntimeError(f"monid runs get empty rc={proc.returncode}")
    return json.loads(raw)


def monid_cost_usd(run: dict) -> float:
    cost = run.get("cost") or {}
    try:
        return float(cost.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def term_row(term: str, note: str, examples: list[str] | None = None, recent: int = 1, **extra) -> dict:
    row = {"term": term.strip().lower(), "note": note, "examples": examples or [], "recent": recent}
    row.update(extra)
    return row
