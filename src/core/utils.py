# --------- Utilities (ohne Seiteneffekte nach außen) ---------
import socket
from datetime import datetime
from config.personas import system_prompts, get_prompt_by_name
import re
from typing import List, Dict, Any


def _wiki_mode_enabled(mode_val) -> bool:
    if isinstance(mode_val, bool):
        return mode_val
    s = str(mode_val).strip().lower()
    return s in ("online", "offline")

def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def _system_prompt_with_date(name, include_date) -> str:
    base = get_prompt_by_name(name)
    today = datetime.now().strftime("%Y-%m-%d")
    if include_date:
        base =  f"{base} | Heute ist der {today}."
    return base

def _greeting_text(cfg, bot) -> str:
    tpl = cfg.texts["greeting"]
    values = {
        "model_name":   cfg.core["model_name"],
        "persona_name": bot,
    }
    return tpl.format_map(values)

def clean_token(token: str) -> str:
    # Dummy-Tags raus
    token = re.sub(r"<dummy\d+>", "", token)

    # Einzelne irrelevante Tokens rausfiltern
    stripped = token.strip().lower()
    if stripped in ["assistant", "assistent:", "antwort:"]:
        return ""

    return token


def approx_token_count(messages: List[Dict[str, str]]) -> int:
    """Estimate a rough token count for a list of chat messages.

    We approximate the number of tokens by counting whitespace separated
    words of each message content. This keeps the implementation lightweight
    and avoids external tokenizer dependencies.
    """
    total = 0
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else None
        if content:
            total += len(content.split())
    return total


def context_near_limit(
    history: List[Dict[str, str]],
    persona_options: Dict[str, Any],
    threshold: float = 0.9,
) -> bool:
    """Return True if the conversation is close to the persona's context limit."""

    if not persona_options:
        return False

    limit = int(persona_options.get("num_ctx") or 0)
    if not limit:
        return False

    used = approx_token_count(history)
    return used >= limit * threshold
