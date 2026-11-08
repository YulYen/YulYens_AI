"""Shared helper for interactive persona selection in terminal-based UIs."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from config.personas import _load_system_prompts


def prompt_persona_choice(
    names: list[str],
    texts: Mapping[str, str],
    prompt_key: str,
    *,
    models: Mapping[str, str] | None = None,
) -> str:
    """Print numbered persona list, prompt for a choice, and return the selected name.

    ``models`` maps a persona to its own solo model (#85); only those that
    differ from the default are passed, and only those get the suffix.
    """
    print(texts["choose_persona"])
    for idx, name in enumerate(names, start=1):
        desc = next(p for p in _load_system_prompts() if p["name"] == name)[
            "description"
        ]
        model = (models or {}).get(name)
        suffix = f" [{model}]" if model else ""
        print(f"{idx}. {name}{suffix} – {desc}")
    while True:
        sel = input(f"{texts[prompt_key]} ").strip()
        try:
            choice = int(sel) - 1
            if 0 <= choice < len(names):
                return names[choice]
        except ValueError:
            logging.debug("Invalid persona selection: %r", sel)
        print(texts["terminal_invalid_selection"])
