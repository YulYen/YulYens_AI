"""Persona configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config_singleton import Config

_BASE_PATH = Path(__file__).with_name("personas_base.yaml")
_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"


def _load_system_prompts() -> list[dict[str, Any]]:
    """Loads persona data from the base and locale YAML files."""

    cfg = Config()
    base_data = yaml.safe_load(_BASE_PATH.read_text(encoding="utf-8"))
    locale_path = _LOCALES_DIR / cfg.language / "personas.yaml"
    locale_data = yaml.safe_load(locale_path.read_text(encoding="utf-8"))

    personas: list[dict[str, Any]] = []
    for base_persona in base_data["personas"]:
        persona_name = base_persona["name"]
        localized = locale_data["personas"][persona_name]

        entry: dict[str, Any] = {
            "name": localized.get("name", persona_name),
            "prompt": localized["prompt"],
            "description": localized.get("description", ""),
            "drink": localized.get("drink", "Coffee"),
            "llm_options": base_persona.get("llm_options", {}),
        }

        defaults = base_persona.get("defaults")
        if defaults:
            entry["defaults"] = defaults

        personas.append(entry)

    return personas


system_prompts: list[dict[str, Any]] = _load_system_prompts()


def get_prompt_by_name(name: str) -> str:
    """Returns the prompt text for a persona by name."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona["prompt"]
    raise ValueError(f"Persona '{name}' not found.")


def get_options(name: str) -> dict[str, Any] | None:
    """Returns the options for a persona by name."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona.get("llm_options") or None
    raise ValueError(f"Persona '{name}' not found.")


def get_all_persona_names() -> list[str]:
    """Returns a list of all persona names."""
    return [p["name"] for p in system_prompts]


def get_drink(name: str) -> str:
    """Returns a persona's favorite drink."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona.get("drink", "Coffee")
    raise ValueError(f"Persona '{name}' not found.")
