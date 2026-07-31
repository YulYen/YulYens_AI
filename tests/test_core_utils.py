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


def test_file_exchange_defaults_to_on_and_can_be_switched_off():
    from types import SimpleNamespace

    from core.utils import is_file_exchange_enabled

    # Ohne Sektion und ohne Schlüssel: an — der Austausch war immer da.
    assert is_file_exchange_enabled(SimpleNamespace()) is True
    assert is_file_exchange_enabled(SimpleNamespace(storage={})) is True
    assert (
        is_file_exchange_enabled(SimpleNamespace(storage={"file_exchange": False}))
        is False
    )


def test_module_available_survives_a_stub_without_spec():
    """`find_spec` wirft ValueError, wenn ein Modul ohne __spec__ registriert ist.

    Genau das passiert, sobald ein Test (oder ein Plugin) einen Platzhalter für
    eine optionale Abhängigkeit in `sys.modules` legt — die WebUI startete dann
    gar nicht mehr, statt den Vorlesen-Button einfach auszublenden.
    """
    import sys
    import types

    from core.utils import module_available

    name = "yulyen_stub_ohne_spec"
    sys.modules[name] = types.ModuleType(name)
    try:
        assert module_available(name) is False
    finally:
        del sys.modules[name]

    assert module_available("json") is True
    assert module_available("garantiert_nicht_installiert_xyz") is False
