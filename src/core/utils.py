# --------- Utilities (ohne Seiteneffekte nach außen) ---------
import logging
import math
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, Union

from config.personas import get_prompt_by_name

Message = Dict[str, Any]


def _token_stats(messages: Sequence[Message], chars_per_token: float) -> Tuple[int, int, int]:
    """Return (message_count, total_chars, content_tokens)."""

    total_chars = 0
    message_count = 0

    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not content:
            continue
        normalized = re.sub(r"\s+", " ", str(content)).strip()
        if not normalized:
            continue
        message_count += 1
        total_chars += len(normalized)

    if total_chars:
        content_tokens = math.ceil(total_chars / max(chars_per_token, 0.1))
    else:
        content_tokens = 0

    return message_count, total_chars, content_tokens


def karl_prepare_quick_and_dirty(
    messages: Sequence[Message],
    num_ctx: int,
    *,
    headroom_tokens: int = 256,
    headroom_ratio: float = 0.20,
    min_keep_tail: int = 2,
    chars_per_token: float = 4.0,
) -> List[Message]:
    """Trim conversation history to leave space for the upcoming response."""

    items = list(messages)
    if not items or num_ctx <= 0:
        return items

    target = max(0, num_ctx - max(headroom_tokens, int(num_ctx * headroom_ratio)))
    used_before = _token_stats(items, chars_per_token)[2]

    if used_before <= target:
        return items

    head = items[:1] if items[0].get("role") == "system" else []
    keep_tail = max(0, min(min_keep_tail, len(items) - len(head)))
    tail = items[-keep_tail:] if keep_tail else []
    core = items[len(head) : len(items) - keep_tail]

    dropped = 0
    while core and _token_stats(head + core + tail, chars_per_token)[2] > target:
        core.pop(0)
        dropped += 1
    result = head + core + tail
    used_after = _token_stats(result, chars_per_token)[2]
    logging.info(
        "[karl_prepare] used=%s→%s, target=%s, dropped=%s (Karl später geeignet ersetzen)",
        used_before,
        used_after,
        target,
        dropped,
    )
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
        base = f"{base} | Heute ist der {today}."
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

_UNWANTED_TOKENS = {"assistant", "assistent:", "antwort:"}


def clean_token(token: str) -> str:
    # Dummy-Tags raus
    token = re.sub(r"<dummy\d+>", "", token)

    # Einzelne irrelevante Tokens rausfiltern
    if token.strip().lower() in _UNWANTED_TOKENS:
        return ""

    return token


def approx_token_count(
    messages: Sequence[Message],
    *,
    chars_per_token: float = 4.0,  # ~4 Zeichen pro Token (heuristisch, konservativ)
    per_message_overhead: int = 3,  # Format/Role-Overhead je Nachricht
    per_request_overhead: int = 3,  # Einmaliger Zuschlag für System/Meta
) -> int:
    """Schätzt grob die Anzahl Tokens für Chatnachrichten ohne externen Tokenizer."""

    message_count, total_chars, content_tokens = _token_stats(messages, chars_per_token)
    overhead_tokens = per_request_overhead + message_count * per_message_overhead
    estimate = max(content_tokens + overhead_tokens, 0)

    logging.info(
        "[approx_token_count] chars_per_token=%s, n_msgs=%s, total_chars=%s, "
        "content_tokens≈%s, overhead=%s, estimate=%s",
        chars_per_token,
        message_count,
        total_chars,
        content_tokens,
        overhead_tokens,
        estimate,
    )

    return estimate


def context_near_limit(
    history: Sequence[Message],
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
