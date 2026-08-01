"""Darf ein gespeichertes Gespräch als Ensemble-Persona fortgesetzt werden?

**Bewusst über alle Einstiegspunkte parametrisiert, nicht einer pro Oberfläche.**
Genau daran ist die Regel zweimal gescheitert: #55 baute sie für den Verlauf,
über den JSON-Upload lief der Gast weiter als echte Persona; die Korrektur
zog beide zusammen — und übersah den dritten Weg, den Ladepfad im Terminal,
der dieselbe Datei liest.

Ein neuer Weg ins Gespräch muss hier eine Zeile hinzufügen, sonst fällt der
Test nicht auf, dass es ihn gibt.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from config.texts import Texts
from ui.continuation import GUEST_APP, continuable_persona, persona_info_from_names
from ui.session import SessionContext
from ui.terminal_ui import TerminalUI
from wiki.lookup import WikiLookup

PERSONA_INFO = {"leah": {"name": "LEAH", "description": "warm"}}


def _meta(persona: str, app: str) -> dict:
    return {
        "created_at": "2026-07-31T10:00:00",
        "model": "dummy",
        "persona": persona,
        "app": app,
        "user": "local",
    }


# ---- Die Regel selbst -------------------------------------------------------


@pytest.mark.parametrize(
    "persona, app, continuable",
    [
        ("LEAH", "web", True),  # echte Persona, eigenes Gespräch
        ("LEAH", "terminal", True),  # dieselbe, aus dem Terminal
        ("LEAH", "web-import", True),  # hochgeladen, aber echte Persona
        ("LEAH", GUEST_APP, False),  # Gast, der sich LEAH nennt
        ("Leah", GUEST_APP, False),  # Gast mit abweichender Schreibweise
        ("Leah", "web", False),  # Altzeile ohne Marker — Name fängt sie
        ("Unbekannt", "web", False),  # Persona gibt es nicht (mehr)
    ],
)
def test_continuable_persona_decides_on_app_and_exact_name(persona, app, continuable):
    result = continuable_persona(persona, app, PERSONA_INFO)

    assert (result is not None) is continuable


def test_persona_info_from_names_keeps_the_exact_name():
    """Das Terminal hat nur Namen — die Tabelle muss den Gast-Fall tragen."""
    info = persona_info_from_names(["LEAH", "DORIS"])

    assert continuable_persona("LEAH", "web", info) == {"name": "LEAH"}
    assert continuable_persona("Leah", "web", info) is None


def _write_conversation(tmp_path, persona: str, app: str) -> Path:
    path = tmp_path / "gespraech.json"
    path.write_text(
        json.dumps(
            {
                "meta": _meta(persona, app),
                "messages": [
                    {"role": "user", "content": "Was hast du mir vorhin geraten?"},
                    {"role": "assistant", "content": "Antwort der GAST-Persona."},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


# ---- Weg 1 und 2: die WebUI -------------------------------------------------


def _web_ui(tmp_path):
    from tests.test_web_ui import _history_web_ui

    return _history_web_ui(tmp_path)


def test_way_1_history_refuses_a_guest_conversation(tmp_path):
    web_ui, store = _web_ui(tmp_path)
    session = SessionContext()
    cid = store.start(user="local", persona="LEAH", model="m", app=GUEST_APP)
    store.append(cid, "user", "Hallo Gast")

    web_ui._on_history_open(session, cid, "local", PERSONA_INFO, "Tippe")

    assert session.bot is None


def test_way_2_upload_refuses_a_guest_conversation(tmp_path):
    web_ui, _store = _web_ui(tmp_path)
    session = SessionContext()
    path = _write_conversation(tmp_path, "LEAH", GUEST_APP)

    web_ui._on_load_conversation(session, str(path), PERSONA_INFO, "Tippe")

    assert session.bot is None


# ---- Weg 3: das Terminal ----------------------------------------------------


def _terminal_ui() -> TerminalUI:
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    catalog = Texts(language="de", locales_dir=locales_dir)
    cfg = SimpleNamespace(
        texts=catalog,
        t=catalog.format,
        core={"model_name": "dummy"},
        ui={"experimental": {"broadcast_mode": True}},
    )
    ui = TerminalUI(factory=Mock(), config=cfg, wiki=WikiLookup())
    ui.file_exchange_enabled = True
    return ui


def test_way_3_terminal_load_refuses_a_guest_conversation(
    tmp_path, monkeypatch, capsys
):
    """Der Weg, den #55 übersehen hat.

    Das Terminal prüfte nur `meta['persona'] in get_all_persona_names()` und
    setzte ein Gast-Gespräch damit still unter dem System-Prompt der echten
    Persona fort.
    """
    ui = _terminal_ui()
    path = _write_conversation(tmp_path, "LEAH", GUEST_APP)
    monkeypatch.setattr("builtins.input", lambda _: str(path))
    monkeypatch.setattr(
        "ui.terminal_ui.get_all_persona_names", lambda: ["LEAH", "DORIS"]
    )

    accepted = ui._load_conversation_from_prompt()

    assert accepted is False
    assert ui.bot is None
    assert "Gast-Persona" in capsys.readouterr().out


def test_way_3_terminal_load_still_accepts_a_real_persona(tmp_path, monkeypatch):
    """Gegenprobe: der normale Ladepfad darf nicht kaputtgehen."""
    ui = _terminal_ui()
    path = _write_conversation(tmp_path, "LEAH", "terminal")
    monkeypatch.setattr("builtins.input", lambda _: str(path))
    monkeypatch.setattr(
        "ui.terminal_ui.get_all_persona_names", lambda: ["LEAH", "DORIS"]
    )
    monkeypatch.setattr(ui, "_set_persona", lambda name: setattr(ui, "bot", name))

    accepted = ui._load_conversation_from_prompt()

    assert accepted is True
    assert ui.bot == "LEAH"
    assert len(ui.history) == 2
