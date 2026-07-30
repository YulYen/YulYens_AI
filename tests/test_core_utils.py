"""Kleine Helfer aus core/utils.py."""

import logging

from core.context_utils import approx_token_count
from core.utils import SAME_AS_CHAT, resolve_model_name

# ---- same_as_chat-Sentinel ---------------------------------------------------
# Karl (#12) und der Eval-Judge (#41) benutzen denselben Sentinel. Die Auflösung
# lag doppelt im Code, bis sie hierher gezogen wurde.


def test_sentinel_resolves_to_the_chat_model():
    assert resolve_model_name(SAME_AS_CHAT, "ministral-3:8b") == "ministral-3:8b"


def test_explicit_model_wins():
    assert resolve_model_name("llama3:70b", "ministral-3:8b") == "llama3:70b"


def test_missing_or_blank_falls_back_to_the_chat_model():
    assert resolve_model_name(None, "chat") == "chat"
    assert resolve_model_name("", "chat") == "chat"
    assert resolve_model_name("   ", "chat") == "chat"


def test_surrounding_whitespace_is_stripped():
    assert resolve_model_name("  llama3  ", "chat") == "llama3"


# ---- Logspam ------------------------------------------------------------------


def test_token_estimate_logs_on_debug_not_info(caplog):
    """Seit der OpenAI-API (#37) läuft das zweimal pro Request.

    Auf INFO wäre das Logspam im ganz normalen Betrieb.
    """
    messages = [{"role": "user", "content": "Hallo Welt"}]

    with caplog.at_level(logging.INFO):
        approx_token_count(messages)
    assert "approx_token_count" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        approx_token_count(messages)
    assert "approx_token_count" in caplog.text
