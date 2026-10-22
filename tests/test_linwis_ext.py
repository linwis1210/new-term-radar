"""Pure-logic tests for Linwis fork extensions. No network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar import __main__ as cli
from radar import config, ext_common, ext_hn, ext_ph, ext_report, ext_seo_gate, ext_steam, ext_trends_rss
from radar.ext_common import ai_related, steam_ai_toolish


def test_ai_related_keeps_tools_drops_sports():
    assert ai_related("Show HN: an LLM agent for code review")
    assert ai_related("New TTS voice cloning API")
    assert not ai_related("Premier League final score Chelsea vs Arsenal")
    assert not ai_related("election results senator race")


def test_steam_filters_pure_games():
    assert steam_ai_toolish("AI Level Editor Studio for developers")
    assert not steam_ai_toolish("Cyber Shooter FPS multiplayer battle royale")
    assert not steam_ai_toolish("Farming Adventure RPG")


def test_term_row_shape():
    r = ext_common.term_row("FooBar", "note", examples=["x"], recent=3)
    assert r["term"] == "foobar" and r["recent"] == 3


def test_hn_title_term_strips_show_prefix():
    assert ext_hn._title_term("Show HN: Sphinx – git hooks for AI code") == "Sphinx"


def test_trends_traffic_parse():
    assert ext_trends_rss._traffic("1,000+") == 1000
    assert ext_trends_rss._traffic("500+") == 500
    assert ext_trends_rss._traffic("") == 0


def test_steam_parse_results_html():
    html = '''
    <a href="https://store.steampowered.com/app/111/Foo/" data-ds-appid="111"
       data-ds-itemkey="App_111"><div class="tab_item_name"><span class="title">Foo AI Tool</span></div></a>
    <div data-ds-appid="222"><span class="title">Bar Game</span></div>
    '''
    rows = ext_steam._parse_results_html(html)
    assert {r["appid"] for r in rows} >= {"111", "222"}


def test_ph_handles_error_dict_not_crash(monkeypatch):
    def boom(url, timeout=30):
        raise OSError("network down")
    monkeypatch.setattr(ext_ph, "http_get_text", boom)
    out = ext_ph.fetch_ph({})
    assert out["terms"] == [] and "error" in out


def test_hn_handles_error_dict(monkeypatch):
    monkeypatch.setattr(ext_hn, "_ids", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    out = ext_hn.fetch_hn({})
    assert "error" in out and out["terms"] == []


def test_prior_terms_from_radar_md(tmp_path):
    md = tmp_path / "2026-10-21.md"
    md.write_text("# x\n去重：KiviDB / DeepInfer / OXR\n\n| **Sphinx** | ok |\n", encoding="utf-8")
    found = ext_seo_gate.prior_terms(tmp_path)
    assert "kividb" in found and "deepinfer" in found and "sphinx" in found


def test_long_tails_and_domains():
    tails = ext_seo_gate.long_tails("oxr", n=8)
    assert len(tails) >= 5 and tails[0].startswith("oxr")
    doms = ext_seo_gate.domain_candidates("OXR Parser", n=3)
    assert all(d.endswith(".com") for d in doms) and 2 <= len(doms) <= 3


def test_gates_logic():
    ok, _ = ext_seo_gate.gate1_new_rising("deepinfer", {"sources": ["hn", "trends_rss"], "score": 100})
    assert ok
    bad, _ = ext_seo_gate.gate1_new_rising("ab", {"sources": [], "score": 0})
    assert not bad
    ok2, _ = ext_seo_gate.gate2_ai_tool("voice clonr", {"examples": ["new TTS voice cloning API"], "blob": ""})
    assert ok2
    bad2, _ = ext_seo_gate.gate2_ai_tool("chelsea", {"examples": ["Premier League final score"], "blob": ""})
    assert not bad2


def test_serp_and_rdap_hooks():
    serp = ext_seo_gate.serp_check("obscuretoolxyz", fetch=lambda t: "result__a " * 3)
    assert serp["status"] in ("empty", "unchecked")
    crowded = ext_seo_gate.serp_check("chatgpt", fetch=lambda t: "wikipedia.org github.com producthunt.com apps.apple.com " + "result__a " * 25)
    assert crowded["status"] == "crowded"
    avail = ext_seo_gate.rdap_available("nosuch-linwis-test.com", fetch=lambda d: (404, b""))
    assert avail["status"] == "available"
    taken = ext_seo_gate.rdap_available("google.com", fetch=lambda d: (200, b"{}"))
    assert taken["status"] == "taken"


def test_seo_gate_full_offline(tmp_path):
    (tmp_path / "old.md").write_text("去重：OldTerm\n", encoding="utf-8")
    blocks = {
        "hn": {"terms": [
            {"term": "voiceclonr", "recent": 80, "examples": ["Show HN: VoiceClonr TTS API"]},
            {"term": "oldterm", "recent": 90, "examples": ["AI tool OldTerm"]},
            {"term": "chelsea fc", "recent": 200, "examples": ["Premier League final score"]},
        ]},
        "trends_rss": {"terms": [
            {"term": "voiceclonr", "recent": 500, "traffic": 500, "examples": ["US:500+"]},
        ]},
    }
    cfg = {"linwis_ext": {"serp_check": True, "rdap_check": True, "radar_dir": str(tmp_path)}}
    out = ext_seo_gate.run_seo_gate(
        cfg, blocks, radar_dir=tmp_path,
        serp_fetch=lambda t: "result__a link",
        rdap_fetch=lambda d: (404, b""),
    )
    terms = {c["term"] for c in out["candidates"]}
    assert "voiceclonr" in terms
    assert "oldterm" not in terms  # prior
    excl = {e["term"] for e in out["excluded"]}
    assert "chelsea fc" in excl or "oldterm" in excl


def test_ext_report_renders_chinese():
    blocks = {
        "hn": {"terms": [{"term": "sphinx", "note": "HN"}]},
        "ph": {"skipped": True},
        "steam": {"error": "down"},
        "trends_rss": {"terms": []},
        "monid_reddit": {"skipped": True, "error": "monid CLI not found"},
        "monid_tiktok": {"terms": [], "cost_usd": 0},
        "seo_gate": {"candidates": [{
            "term": "sphinx", "sources": ["hn"], "reason": "ok",
            "long_tails": ["sphinx ai", "sphinx tool"], "domains": [{"domain": "sphinxai.com", "status": "available"}],
            "near": [],
        }], "excluded": []},
    }
    text = ext_report.render(blocks)
    assert "建站候选" in text and "**sphinx**" in text and "来源状态" in text
    assert "Linwis" in ext_report.append_section(blocks)


def test_config_linwis_ext_defaults(tmp_path):
    cfg_path = tmp_path / "config.json"
    # minimal valid config
    cfg_path.write_text(json.dumps({
        "x_accounts": {"labs": [], "bloggers": []},
        "sitemaps": {},
    }))
    cfg = config.load(cfg_path)
    assert cfg["linwis_ext"]["enabled"] is False
    assert "LocalLLaMA" in cfg["linwis_ext"]["reddit_subs"]


def test_skippable_includes_linwis():
    for name in ("hn", "ph", "steam", "trends_rss", "monid_reddit", "monid_tiktok", "seo_gate"):
        assert name in cli.SKIPPABLE


def test_linwis_help():
    with pytest.raises(SystemExit) as ei:
        cli.main(["linwis", "--help"])
    assert ei.value.code == 0


def test_run_linwis_blocks_respects_skip(monkeypatch, tmp_path):
    calls = []

    def track(name):
        def fn(*a, **k):
            calls.append(name)
            return {"terms": [], "rows": []}
        return fn

    monkeypatch.setattr(cli.ext_hn, "fetch_hn", track("hn"))
    monkeypatch.setattr(cli.ext_ph, "fetch_ph", track("ph"))
    monkeypatch.setattr(cli.ext_steam, "fetch_steam", track("steam"))
    monkeypatch.setattr(cli.ext_trends_rss, "fetch_trends_rss", track("trends_rss"))
    monkeypatch.setattr(cli.ext_monid_reddit, "fetch_monid_reddit", track("monid_reddit"))
    monkeypatch.setattr(cli.ext_monid_tiktok, "fetch_monid_tiktok", track("monid_tiktok"))
    cfg = {"linwis_ext": {"enabled": True}}
    blocks = cli.run_linwis_blocks(cfg, tmp_path, skip={"monid_reddit", "monid_tiktok"})
    assert blocks["monid_reddit"].get("skipped")
    assert "monid_reddit" not in calls and "hn" in calls


def test_cmd_linwis_writes_report(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run_linwis_blocks", lambda cfg, state, skip: {
        "hn": {"terms": [{"term": "demoai", "note": "HN", "examples": ["demo"], "recent": 10}]},
        "ph": {"terms": []}, "steam": {"terms": []}, "trends_rss": {"terms": []},
        "monid_reddit": {"skipped": True}, "monid_tiktok": {"skipped": True},
    })
    monkeypatch.setattr(cli.ext_seo_gate, "run_seo_gate", lambda *a, **k: {
        "candidates": [], "excluded": [{"term": "demoai", "reason": "test", "sources": ["hn"]}],
    })
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"x_accounts": {"labs": [], "bloggers": []}, "sitemaps": {}}))
    out = tmp_path / "linwis.md"
    assert cli.main(["linwis", "--config", str(cfg_path), "--state", str(tmp_path / "s"),
                     "--out", str(out), "--skip", "monid_reddit,monid_tiktok"]) == 0
    assert out.exists() and out.with_suffix(".json").exists()
    assert "建站候选" in out.read_text()


def test_daily_unchanged_when_linwis_disabled(monkeypatch, tmp_path):
    """Default enabled=false: daily must not call extension fetchers."""
    called = []

    def boom(*a, **k):
        called.append(1)
        raise AssertionError("linwis should not run")

    monkeypatch.setattr(cli, "run_linwis_blocks", boom)

    def down(*a, **k):
        raise OSError("network is down")
    for mod, fn in ((cli.sources, "x_new"), (cli.sources, "hf_new"), (cli.breakout, "breakouts"), (cli.sitemaps, "diff")):
        monkeypatch.setattr(mod, fn, down)
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"x_accounts": {"labs": [], "bloggers": []}, "sitemaps": {}, "lang": "en"}))
    out = tmp_path / "d.md"
    assert cli.main(["daily", "--config", str(cfg_path), "--state", str(tmp_path / "s"),
                     "--out", str(out), "--skip", "newsites,review,gsc,revenue,asks,sellers,usecases,tutorials"]) == 0
    assert called == []
    assert "Linwis 扩展" not in out.read_text()
