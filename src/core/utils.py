# --------- General utilities (no external side effects) ---------
from datetime import datetime
from pathlib import Path

from config.config_singleton import Config
from config.personas import get_prompt_by_name


def _wiki_mode_enabled(mode_val) -> bool:
    if isinstance(mode_val, bool):
        return mode_val
    s = str(mode_val).strip().lower()
    return s in ("online", "offline")


def _system_prompt_with_date(name, include_date) -> str:
    base = get_prompt_by_name(name)
    if include_date:
        today = datetime.now().strftime("%Y-%m-%d")
        cfg = Config()
        suffix = cfg.t("persona_prompt_date_suffix", date=today)
        base = f"{base} | {suffix}"
    return base


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


def ensure_dir_exists(path: str | Path) -> None:
    """Create a directory if it does not already exist."""
    Path(path).mkdir(parents=True, exist_ok=True)
