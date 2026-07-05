# --------- General utilities (no external side effects) ---------
import re
from datetime import datetime
from pathlib import Path

from config.personas import get_prompt_by_name


def _wiki_mode_enabled(mode_val) -> bool:
    if isinstance(mode_val, bool):
        return mode_val
    s = str(mode_val).strip().lower()
    return s in ("online", "offline")


_ZIM_DATE_RE = re.compile(r"(\d{4})-(\d{2})")


def extract_zim_date(zim_prefix: str | None) -> str | None:
    """Pull the YYYY-MM data date out of a Kiwix ZIM prefix such as
    'wikipedia_de_all_nopic_2025-06'. Returns None when no date is present."""
    if not zim_prefix:
        return None
    match = _ZIM_DATE_RE.search(zim_prefix)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _cutoff_timestamp_text(cfg) -> str:
    """The model's training-knowledge cutoff, looked up per model name."""
    core = getattr(cfg, "core", {}) or {}
    cutoffs = core.get("knowledge_cutoffs") or {}
    cutoff = (
        cutoffs.get(core.get("model_name", "")) if isinstance(cutoffs, dict) else None
    )
    if cutoff:
        return cfg.t("persona_ts_cutoff", cutoff=cutoff)
    return cfg.t("persona_ts_cutoff_unknown")


def _wiki_timestamp_text(cfg) -> str | None:
    """The data date of the wiki knowledge source, or None when wiki is off."""
    wiki = getattr(cfg, "wiki", {}) or {}
    mode = str(wiki.get("mode")).strip().lower()
    if mode == "offline":
        date = extract_zim_date((wiki.get("offline") or {}).get("zim_prefix"))
        if date:
            return cfg.t("persona_ts_wiki_offline", date=date)
        return cfg.t("persona_ts_wiki_offline_unknown")
    if mode == "online":
        return cfg.t("persona_ts_wiki_online")
    return None


def _system_prompt_with_date(name: str, cfg) -> str:
    """Append a clearly separated 'three timestamps' block to the persona prompt:
    today's date, the model's training cutoff, and the wiki data date. Keeping
    the three distinct stops personas from claiming their knowledge reaches today.
    Missing values are stated honestly ('unknown') rather than faked or dropped
    silently; the wiki line is omitted entirely when no wiki source is active.
    Master switch: core.include_date."""
    base = get_prompt_by_name(name)
    core = getattr(cfg, "core", {}) or {}
    if not core.get("include_date"):
        return base
    parts = [
        cfg.t("persona_ts_today", date=datetime.now().strftime("%Y-%m-%d")),
        _cutoff_timestamp_text(cfg),
    ]
    wiki_part = _wiki_timestamp_text(cfg)
    if wiki_part:
        parts.append(wiki_part)
    parts.append(cfg.t("persona_ts_guidance"))
    return f"{base} | {' '.join(parts)}"


def _greeting_text(cfg, bot) -> str:
    tpl = cfg.texts["greeting"]
    values = {
        "model_name": cfg.core["model_name"],
        "persona_name": bot,
    }
    return tpl.format_map(values)


def is_broadcast_enabled(config) -> bool:
    """Return True when experimental broadcast/ask-all mode is enabled in the config."""
    ui_cfg = getattr(config, "ui", {}) or {}
    try:
        experimental_cfg = ui_cfg.get("experimental") or {}
    except AttributeError:
        experimental_cfg = getattr(ui_cfg, "experimental", {}) or {}
    return bool(experimental_cfg.get("broadcast_mode"))


def is_broadcast_parallel(config) -> bool:
    """Return True when ask-all should stream all personas concurrently (default)."""
    ui_cfg = getattr(config, "ui", {}) or {}
    try:
        experimental_cfg = ui_cfg.get("experimental") or {}
    except AttributeError:
        experimental_cfg = getattr(ui_cfg, "experimental", {}) or {}
    return bool(experimental_cfg.get("broadcast_parallel", True))


def ensure_dir_exists(path: str | Path) -> None:
    """Create a directory if it does not already exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def is_ollama_module_not_found(exc: ModuleNotFoundError) -> bool:
    """Return True when a ModuleNotFoundError points to the missing 'ollama' package."""
    missing_name = getattr(exc, "name", None)
    return missing_name == "ollama" or (
        missing_name is None and "ollama" in str(exc).lower()
    )
