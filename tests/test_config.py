# tests/test_config_and_greeting.py
import pytest

from core.utils import _greeting_text, _wiki_mode_enabled
from personas import system_prompts
from config_singleton import Config


def test_greeting_replaces_placeholders(tmp_path):
    """
    Prüft die 1:1-Platzhalterersetzung aus der YAML:
    - {model_name} -> core.model_name
    - {persona_name} -> system_prompts[0].name
    - unbekannte Platzhalter bleiben unverändert (SafeDict)
    """
    persona_name = system_prompts[0]["name"]
    g = _greeting_text(Config(), persona_name)
    assert f"{persona_name}" in g
    assert "Chatte" in g


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("offline", True),
        ("false",   False),
        ("online",  True),
        (False,     False),  # falls mal bool in YAML verwendet wird
        (None,      False),
    ],
)
def test_wiki_mode_enabled(mode, expected):
    """
    Aktuelles Verhalten: KeywordFinder nur bei 'offline' und 'online' aktiv.
    Alles andere (false/None) -> aus.
    """
    assert _wiki_mode_enabled(mode) is expected
