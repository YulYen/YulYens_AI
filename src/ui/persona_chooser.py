"""Shared helper for interactive persona selection in terminal-based UIs."""

from __future__ import annotations

import logging

from config.personas import _load_system_prompts


def prompt_persona_choice(names: list[str], texts: dict, prompt_key: str) -> str:
    """Print numbered persona list, prompt for a choice, and return the selected name."""
    print(texts["choose_persona"])
    for idx, name in enumerate(names, start=1):
        desc = next(p for p in _load_system_prompts() if p["name"] == name)[
            "description"
        ]
        print(f"{idx}. {name} – {desc}")
    while True:
        sel = input(f"{texts[prompt_key]} ").strip()
        try:
            choice = int(sel) - 1
            if 0 <= choice < len(names):
                return names[choice]
        except ValueError:
            logging.debug("Invalid persona selection: %r", sel)
        print(texts["terminal_invalid_selection"])
