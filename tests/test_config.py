# tests/test_config_and_greeting.py
import yaml
import pytest

from jk_ki_main import format_greeting, _wiki_mode_enabled
from system_prompts import leah_system_prompts


def test_greeting_replaces_placeholders(tmp_path):
    """
    Prüft die 1:1-Platzhalterersetzung aus der YAML:
    - {model_name} -> core.model_name
    - {persona_name} -> system_prompts[0].name
    - unbekannte Platzhalter bleiben unverändert (SafeDict)
    """
    cfg_text = """
core:
  model_name: "TestModel"
ui:
  type: "web"
  greeting: "Chatte mit {persona_name} auf Basis von {model_name}!"
wiki:
  wiki_mode: "offline"
  snippet_limit: 1600
logging:
  level: "INFO"
"""
    p = tmp_path / "config.yaml"
    p.write_text(cfg_text, encoding="utf-8")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))

    persona_name = leah_system_prompts[0]["name"]
    g = format_greeting(cfg)
    assert f"{persona_name}" in g
    assert "TestModel" in g


def test_greeting_missing_keys_raises(tmp_path):
    """
    Keine Defaults: Wenn Pflicht-Keys fehlen, soll es knallen (KeyError).
    """
    cfg_text = """
ui:
  type: "web"
  greeting: "Hallo {model_name}"
wiki:
  wiki_mode: "offline"
  snippet_limit: 1600
logging:
  level: "INFO"
"""
    p = tmp_path / "config.yaml"
    p.write_text(cfg_text, encoding="utf-8")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))

    with pytest.raises(KeyError):
        _ = format_greeting(cfg)


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
def test_wiki_mode_enabled_current_behavior(mode, expected):
    """
    Aktuelles Verhalten: KeywordFinder nur bei 'offline' und 'online' aktiv.
    Alles andere (false/None) -> aus.
    """
    assert _wiki_mode_enabled(mode) is expected
