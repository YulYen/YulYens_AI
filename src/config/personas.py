"""Persona configuration loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config_singleton import Config

_BASE_PATH = Path(__file__).with_name("personas_base.yaml")
_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"


def _load_system_prompts() -> List[Dict[str, Any]]:
    """Loads persona data from the base and locale YAML files."""

    cfg = Config()
    base_data = yaml.safe_load(_BASE_PATH.read_text(encoding="utf-8"))
    locale_path = _LOCALES_DIR / cfg.language / "personas.yaml"
    locale_data = yaml.safe_load(locale_path.read_text(encoding="utf-8"))

    personas: List[Dict[str, Any]] = []
    for base_persona in base_data["personas"]:
        persona_name = base_persona["name"]
        localized = locale_data["personas"][persona_name]

        entry: Dict[str, Any] = {
            "name": localized.get("name", persona_name),
            "prompt": localized["prompt"],
            "description": localized.get("description", ""),
            "drink": localized.get("drink", "Kaffee"),
            "image_path": base_persona["image_path"],
            "llm_options": base_persona.get("llm_options", {}),
        }

        defaults = base_persona.get("defaults")
        if defaults:
            entry["defaults"] = defaults

        personas.append(entry)

    return personas


system_prompts: List[Dict[str, Any]] = _load_system_prompts()


def get_prompt_by_name(name: str) -> str:
    """Gibt den Prompt-Text für eine Persona anhand des Namens zurück."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona["prompt"]
    raise ValueError(f"Persona '{name}' nicht gefunden.")


def get_options(name: str) -> Optional[Dict[str, Any]]:
    """Gibt die Options für eine Persona anhand des Namens zurück."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona.get("llm_options") or None
    raise ValueError(f"Persona '{name}' nicht gefunden.")


def get_all_persona_names() -> List[str]:
    """Gibt eine Liste aller Persona-Namen zurück."""
    return [p["name"] for p in system_prompts]


def get_drink(name: str) -> str:
    """Gibt das Lieblingsgetränk einer Persona zurück."""
    for persona in system_prompts:
        if persona["name"].lower() == name.lower():
            return persona.get("drink", "Kaffee")
    raise ValueError(f"Persona '{name}' nicht gefunden.")
