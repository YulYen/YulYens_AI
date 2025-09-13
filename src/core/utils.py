# --------- Utilities (ohne Seiteneffekte nach außen) ---------
import socket
from datetime import datetime
from config.personas import  get_prompt_by_name
import re
from pathlib import Path
from typing import List, Dict, Any, Union
import logging
import math

def karl_prepare_quick_and_dirty(messages, num_ctx: int):
    """
    Quick & Dirty: Platz schaffen für Antwort-Headroom.
    Dropt alte Messages, bis geschätzte Länge <= num_ctx - headroom.
    TODO: Später durch Karl-Summarizer ersetzen.
    """
    import logging, math, re

    chars_per_token = 4.0
    headroom_tokens = 256
    headroom_ratio = 0.20
    min_keep_tail = 2

    def _approx_token_count(msgs):
        total_chars = 0
        for m in msgs:
            c = (m.get("content") or "") if isinstance(m, dict) else ""
            total_chars += len(re.sub(r"\s+", " ", c).strip())
        return math.ceil(total_chars / chars_per_token)

    target = max(0, num_ctx - max(headroom_tokens, int(num_ctx * headroom_ratio)))
    used_before = _approx_token_count(messages)

    if used_before <= target:
        return messages

    # Systemprompt (erste) und letzte n Nachrichten schützen
    protect_head = 1 if messages and messages[0].get("role") == "system" else 0
    core = messages[protect_head:-min_keep_tail] if min_keep_tail > 0 else messages[protect_head:]
    tail = messages[-min_keep_tail:] if min_keep_tail > 0 else []

    dropped = 0
    while core and _approx_token_count(messages[:protect_head] + core + tail) > target:
        core.pop(0)
        dropped += 1

    result = messages[:protect_head] + core + tail
    logging.debug("[karl_prepare] used=%s→%s, target=%s, dropped=%s (TODO: Karl ersetzen)",
                  used_before, _approx_token_count(result), target, dropped)
    return result


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


def ensure_dir_exists(path: Union[str, Path]) -> None:
    """Create a directory if it does not already exist."""
    Path(path).mkdir(parents=True, exist_ok=True)

def clean_token(token: str) -> str:
    # Dummy-Tags raus
    token = re.sub(r"<dummy\d+>", "", token)

    # Einzelne irrelevante Tokens rausfiltern
    stripped = token.strip().lower()
    if stripped in ["assistant", "assistent:", "antwort:"]:
        return ""

    return token


def approx_token_count(
    messages: List[Dict[str, str]],
    *,
    chars_per_token: float = 4.0,       # ~4 Zeichen pro Token (heuristisch, konservativ)
    per_message_overhead: int = 3,      # Format/Role-Overhead je Nachricht
    per_request_overhead: int = 3       # Einmaliger Zuschlag für System/Meta
) -> int:
    """
    Schätzt grob die Anzahl Tokens für Chatnachrichten ohne externen Tokenizer.

    Methode:
      - Zählt Zeichen (nach Whitespace-Normalisierung).
      - Rechnet sie in Tokens um: Zeichen / chars_per_token.
      - Addiert Overheads für Nachrichten und Anfrage.
    """
    total_chars = 0
    n_msgs = 0

    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else None
        if not content:
            continue
        n_msgs += 1
        normalized = re.sub(r"\s+", " ", content).strip()
        total_chars += len(normalized)

    content_tokens = math.ceil(total_chars / max(chars_per_token, 0.1))
    overhead_tokens = per_request_overhead + n_msgs * per_message_overhead
    estimate = max(content_tokens + overhead_tokens, 0)

    logging.debug(
        "[approx_token_count] "
        f"chars_per_token={chars_per_token}, "
        f"n_msgs={n_msgs}, total_chars={total_chars}, "
        f"content_tokens≈{content_tokens}, overhead={overhead_tokens}, "
        f"estimate={estimate}"
    )

    return estimate


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
