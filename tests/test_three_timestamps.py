"""Tests for the three-timestamp transparency block (#19).

Three distinct dates land in the persona system prompt, each from its own
source: today's date (system clock), the model training cutoff (per-model config
map) and the wiki data date (parsed from the Kiwix ZIM prefix). Missing values
are stated honestly; the wiki line is dropped when no wiki source is active.
"""

from datetime import datetime

import core.utils as u
import pytest
from config.config_singleton import Config


@pytest.fixture
def cfg():
    Config.reset_instance()
    c = Config("config.yaml")
    yield c
    Config.reset_instance()


# ---- ZIM date extraction --------------------------------------------------


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("wikipedia_de_all_nopic_2025-06", "2025-06"),
        ("wikipedia_en_all_maxi_2024-12", "2024-12"),
        ("no_date_here", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_zim_date(prefix, expected):
    assert u.extract_zim_date(prefix) == expected


# ---- Model cutoff (per-model map) -----------------------------------------


def test_cutoff_known_model(cfg):
    cfg.override("core", {"model_name": "m1", "knowledge_cutoffs": {"m1": "2024-06"}})
    assert "2024-06" in u._cutoff_timestamp_text(cfg)


def test_cutoff_unlisted_model_is_unknown(cfg):
    cfg.override("core", {"model_name": "mX", "knowledge_cutoffs": {"m1": "2024-06"}})
    assert u._cutoff_timestamp_text(cfg) == cfg.t("persona_ts_cutoff_unknown")


def test_cutoff_no_map_is_unknown(cfg):
    cfg.override("core", {"model_name": "m1", "knowledge_cutoffs": None})
    assert u._cutoff_timestamp_text(cfg) == cfg.t("persona_ts_cutoff_unknown")


# ---- Wiki data date -------------------------------------------------------


def test_wiki_offline_with_date(cfg):
    cfg.override(
        "wiki",
        {
            "mode": "offline",
            "offline": {"zim_prefix": "wikipedia_de_all_nopic_2025-06"},
        },
    )
    assert "2025-06" in u._wiki_timestamp_text(cfg)


def test_wiki_offline_unparseable_date(cfg):
    cfg.override("wiki", {"mode": "offline", "offline": {"zim_prefix": "wikipedia_de"}})
    assert u._wiki_timestamp_text(cfg) == cfg.t("persona_ts_wiki_offline_unknown")


def test_wiki_online(cfg):
    cfg.override("wiki", {"mode": "online"})
    assert u._wiki_timestamp_text(cfg) == cfg.t("persona_ts_wiki_online")


def test_wiki_disabled_returns_none(cfg):
    cfg.override("wiki", {"mode": False})
    assert u._wiki_timestamp_text(cfg) is None


# ---- Full prompt assembly -------------------------------------------------


def test_include_date_off_returns_base_only(cfg, monkeypatch):
    cfg.override("core", {"include_date": False})
    monkeypatch.setattr(u, "get_prompt_by_name", lambda n: "BASE")
    assert u._system_prompt_with_date("LEAH", cfg) == "BASE"


def test_full_block_has_three_distinct_stamps(cfg, monkeypatch):
    cfg.override(
        "core",
        {
            "include_date": True,
            "model_name": "m1",
            "knowledge_cutoffs": {"m1": "2024-06"},
        },
    )
    cfg.override(
        "wiki",
        {
            "mode": "offline",
            "offline": {"zim_prefix": "wikipedia_de_all_nopic_2025-06"},
        },
    )
    monkeypatch.setattr(u, "get_prompt_by_name", lambda n: "BASE")

    out = u._system_prompt_with_date("LEAH", cfg)
    assert out.startswith("BASE | ")
    assert datetime.now().strftime("%Y-%m-%d") in out  # today
    assert "2024-06" in out  # model cutoff
    assert "2025-06" in out  # wiki data date
    assert cfg.t("persona_ts_guidance") in out


def test_wiki_disabled_omits_wiki_line_but_keeps_cutoff(cfg, monkeypatch):
    cfg.override(
        "core",
        {
            "include_date": True,
            "model_name": "m1",
            "knowledge_cutoffs": {"m1": "2024-06"},
        },
    )
    cfg.override("wiki", {"mode": False})
    monkeypatch.setattr(u, "get_prompt_by_name", lambda n: "BASE")

    out = u._system_prompt_with_date("LEAH", cfg)
    assert "Kiwix" not in out and "Wikipedia" not in out
    assert "2024-06" in out


# ---- End-to-end through the factory (no Ollama needed) --------------------


def test_factory_streamer_prompt_carries_three_stamps(cfg):
    cfg.ensemble = "classic"
    cfg.override(
        "core",
        {
            "backend": "dummy",
            "include_date": True,
            "model_name": "ministral-3:8b",
            "knowledge_cutoffs": {"ministral-3:8b": "2024-06"},
        },
    )
    cfg.override(
        "wiki",
        {
            "mode": "offline",
            "offline": {"zim_prefix": "wikipedia_de_all_nopic_2025-06"},
        },
    )
    from core.factory import AppFactory

    prompt = AppFactory().get_streamer_for_persona("LEAH").persona_prompt
    assert datetime.now().strftime("%Y-%m-%d") in prompt
    assert "2024-06" in prompt
    assert "2025-06" in prompt
