# --------- Utilities für die Prüfung und Kürzung des LLM-Context (ohne Seiteneffekte nach außen) ---------
import logging
import math
import re
from typing import Any, Dict, List, Sequence, Tuple

Message = Dict[str, Any]

chars_per_token: float = 3.25  # ~3,25 Zeichen pro Token (heuristisch, konservativ)

threshold: float = 0.75 # Kontext nur zu 75% Füllen

headroom_tokens: int = 500 # 500 Token mindestens 'Luft' 
headroom_ratio: float = 0.5 # oder 50% 'Luft lassen, wenn ohnehin gekürzt wird


def _token_stats(messages: Sequence[Message]) -> Tuple[int, int, int]:
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
    min_keep_tail: int = 2,
) -> List[Message]:
    """Trim conversation history to leave space for the upcoming response."""

    items = list(messages)
    if not items or num_ctx <= 0:
        return items

    target = max(0, num_ctx - max(headroom_tokens, int(num_ctx * headroom_ratio)))
    used_before = _token_stats(items)[2]

    if used_before <= target:
        return items

    head = items[:1] if items[0].get("role") == "system" else []
    keep_tail = max(0, min(min_keep_tail, len(items) - len(head)))
    tail = items[-keep_tail:] if keep_tail else []
    core = items[len(head) : len(items) - keep_tail]

    dropped = 0
    while core and _token_stats(head + core + tail)[2] > target:
        core.pop(0)
        dropped += 1
    result = head + core + tail
    used_after = _token_stats(result)[2]
    logging.info(
        "[karl_prepare] used=%s→%s, target=%s, dropped=%s (Karl später geeignet ersetzen)",
        used_before,
        used_after,
        target,
        dropped,
    )
    return result


def approx_token_count(
    messages: Sequence[Message],
    *,
    per_message_overhead: int = 3,  # Format/Role-Overhead je Nachricht
    per_request_overhead: int = 400,  # Einmaliger Zuschlag für System-Prompt/Meta
) -> int:
    """Schätzt grob die Anzahl Tokens für Chatnachrichten ohne externen Tokenizer."""

    message_count, total_chars, content_tokens = _token_stats(messages)
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
) -> bool:
    """Return True if the conversation is close to the persona's context limit."""

    if not persona_options:
        return False

    limit = int(persona_options.get("num_ctx") or 0)
    if not limit:
        return False

    used = approx_token_count(history)
    return used >= limit * threshold
