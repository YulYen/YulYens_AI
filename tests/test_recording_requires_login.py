"""Ohne Anmeldung wird nichts aufgezeichnet (#72).

Der Befund dahinter: ``DisabledAuth`` — der Default — gibt *jedem* Besucher die
Identität ``local``. Alle Gespräche tragen damit denselben Eigentümer, und die
Eigentümerprüfung im Verlauf (aus Runde 2) prüft etwas, das immer zutrifft. Wer
die Seite erreicht, sieht die Gespräche aller anderen, kann sie fortsetzen und
löschen.

Geprüft wird deshalb nicht "der Store schreibt", sondern **wann er es darf**:
mit Anmeldung, mit ausdrücklichem Schalter, und in den Kanälen ohne
Anmeldungsbegriff (Terminal, API) — sonst nicht.
"""

import logging

import pytest
from config.config_singleton import Config
from core.factory import AppFactory


@pytest.fixture()
def cfg(tmp_path):
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    # Die autouse-Fixture schaltet die Ablage global ab; hier ist sie der
    # Prüfgegenstand, also an — aber in tmp_path, nie in der echten Datei.
    cfg.storage = {
        "enabled": True,
        "path": str(tmp_path / "conversations.sqlite3"),
        "shared_without_login": False,
    }
    yield cfg
    Config.reset_instance()


def _web(cfg, **web_cfg):
    cfg.override("ui", {"type": "web", "web": web_cfg})


def test_no_login_means_no_recording(cfg):
    _web(cfg, auth={"provider": "disabled"})

    assert AppFactory().get_store().records is False


def test_a_configured_login_records(cfg, monkeypatch):
    monkeypatch.setenv("YULYEN_TEST_PW", "geheim")
    _web(
        cfg,
        auth={"provider": "local", "users": {"yulyen": "env:YULYEN_TEST_PW"}},
    )

    assert AppFactory().get_store().records is True


def test_header_auth_records(cfg):
    """Der Proxy-Fall: die Identität kommt von außen, aber es gibt eine."""
    _web(cfg, auth={"provider": "header", "header_name": "X-Forwarded-User"})

    assert AppFactory().get_store().records is True


def test_the_opt_in_switch_records_and_says_so(cfg, caplog):
    _web(cfg, auth={"provider": "disabled"})
    cfg.storage["shared_without_login"] = True

    with caplog.at_level(logging.WARNING):
        store = AppFactory().get_store()

    assert store.records is True
    # Die Warnung ist der halbe Sinn des Schalters: wer ihn setzt, soll beim
    # Start lesen, was er damit teilt.
    assert any(
        "shared_without_login" in record.message for record in caplog.records
    ), "der Schalter darf nicht stumm gelten"


def test_the_refusal_says_how_to_get_out_of_it(cfg, caplog):
    """Eine abgeschaltete Ablage ohne Begründung wäre ein Rätsel."""
    _web(cfg, auth={"provider": "disabled"})

    with caplog.at_level(logging.WARNING):
        AppFactory().get_store()

    text = " ".join(record.message for record in caplog.records)
    assert "ui.web.auth.provider" in text and "shared_without_login" in text


def test_the_terminal_records_without_any_login(cfg):
    """Im Terminal gibt es keine Anmeldung, die fehlen könnte."""
    cfg.override("ui", {"type": "terminal"})

    assert AppFactory().get_store().records is True


def test_api_only_records_without_any_login(cfg):
    cfg.override("ui", {"type": None})

    assert AppFactory().get_store().records is True


def test_an_explicitly_disabled_store_stays_disabled(cfg):
    """Kein Umweg: `storage.enabled: false` bleibt aus, auch mit Anmeldung."""
    _web(cfg, auth={"provider": "header"})
    cfg.storage["enabled"] = False

    assert AppFactory().get_store().records is False
