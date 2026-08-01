"""Identitäts-Naht der Web-UI (#53).

Der Wert liegt in der Naht, nicht im Feature — deshalb prüfen die Tests vor
allem zwei Dinge: dass der Default sich exakt wie vorher verhält, und dass die
Identität dort ankommt, wo #25/#24 sie später brauchen (Gesprächslog, Votes).
"""

import logging
from types import SimpleNamespace

import pytest
from auth import (
    AuthConfigError,
    DisabledAuth,
    HeaderAuth,
    Identity,
    LocalUsersAuth,
    build_auth_provider,
)


def _request(username=None, headers=None):
    return SimpleNamespace(username=username, headers=headers or {})


# ---- Default: nichts ändert sich -------------------------------------------


def test_disabled_auth_needs_no_login_and_names_the_local_user():
    provider = DisabledAuth()

    assert provider.gradio_auth() is None
    assert provider.identity_from_request(_request()).name == "local"


def test_missing_config_falls_back_to_disabled():
    assert isinstance(build_auth_provider(None), DisabledAuth)
    assert isinstance(build_auth_provider({}), DisabledAuth)


def test_unknown_provider_falls_back_to_disabled(caplog):
    provider = build_auth_provider({"auth": {"provider": "keycloak"}})

    assert isinstance(provider, DisabledAuth)
    assert "keycloak" in caplog.text


# ---- Lokale Nutzer ---------------------------------------------------------


def test_local_auth_accepts_the_right_password_only():
    provider = LocalUsersAuth({"yulyen": "geheim"})

    assert provider.check("yulyen", "geheim") is True
    assert provider.check("yulyen", "falsch") is False
    assert provider.check("niemand", "geheim") is False
    assert provider.gradio_auth() is not None


def test_local_auth_resolves_env_secrets(monkeypatch):
    monkeypatch.setenv("YULYEN_TEST_PW", "ausdemenv")
    provider = LocalUsersAuth({"yulyen": "env:YULYEN_TEST_PW"})

    assert provider.check("yulyen", "ausdemenv") is True


def test_local_auth_drops_users_without_a_resolvable_password(caplog):
    """Sonst steht jemand vor einem Login, das nie aufgeht."""
    provider = LocalUsersAuth({"leer": "env:GIBT_ES_NICHT", "ok": "pw"})

    assert provider.usernames == ["ok"]
    assert "leer" in caplog.text


def test_local_auth_without_usable_users_refuses_to_start():
    """Umgekehrte Entscheidung: zu statt offen.

    Vorher fiel der Provider hier auf „keine Anmeldung" zurück, begründet mit
    „lieber offen und laut als zugesperrt und rätselhaft". Die Begründung
    unterstellt, der Auslöser sei ein Tippfehler in der Nutzerliste. Der
    häufigere Auslöser ist ein nicht durchgereichtes `env:` — eine
    systemd-Unit ohne EnvironmentFile, ein Container ohne --env. Dann startet
    die App genau dort ohne Anmeldung, wo jemand ausdrücklich eine
    konfiguriert hat, und niemand merkt es.

    Das Fehlverhalten „zu" kostet einen Supportfall, das Fehlverhalten
    „offen" ist unbegrenzt.
    """
    provider = LocalUsersAuth({})

    with pytest.raises(AuthConfigError) as excinfo:
        provider.gradio_auth()

    # Die Meldung muss den wahrscheinlichsten Auslöser nennen, sonst sucht
    # jemand in der falschen Ecke.
    assert "env:" in str(excinfo.value)
    assert "disabled" in str(excinfo.value)


def test_local_auth_with_one_usable_user_still_works(caplog):
    """Gegenprobe: ein einziger auflösbarer Nutzer genügt, der Rest darf fehlen."""
    provider = LocalUsersAuth({"ok": "geheim", "kaputt": "env:GIBT_ES_NICHT"})

    assert callable(provider.gradio_auth())
    assert provider.usernames == ["ok"]


def test_local_auth_reads_the_name_from_the_request():
    provider = LocalUsersAuth({"yulyen": "pw"})

    assert provider.identity_from_request(_request("yulyen")).name == "yulyen"
    assert provider.identity_from_request(_request()).is_known is False


# ---- Header (der Keycloak-Pfad) --------------------------------------------


def test_header_auth_trusts_the_proxy_header():
    provider = HeaderAuth("X-Forwarded-User")

    identity = provider.identity_from_request(
        _request(headers={"X-Forwarded-User": "aus-dem-proxy"})
    )

    assert identity == Identity(name="aus-dem-proxy", source="header")
    # Der Proxy hat die Anmeldung erledigt — Gradio soll keine zweite verlangen.
    assert provider.gradio_auth() is None


def test_header_auth_without_the_header_is_anonymous():
    provider = HeaderAuth("X-Forwarded-User")

    assert provider.identity_from_request(_request(headers={})).is_known is False


# ---- Rückwärtskompatibilität ------------------------------------------------


def test_legacy_share_auth_still_produces_a_login(caplog):
    provider = build_auth_provider(
        {"share_auth": {"username": "alt", "password": "pw"}}
    )

    assert isinstance(provider, LocalUsersAuth)
    assert provider.check("alt", "pw") is True
    assert "veraltet" in caplog.text


def test_empty_legacy_share_auth_stays_disabled():
    provider = build_auth_provider({"share_auth": {"username": "", "password": ""}})

    assert isinstance(provider, DisabledAuth)


@pytest.mark.parametrize("share", [True, False])
def test_login_applies_regardless_of_share(share):
    """Der 0.0.0.0-Befund: früher griff share_auth nur beim Share-Link."""
    provider = build_auth_provider(
        {"share": share, "auth": {"provider": "local", "users": {"a": "b"}}}
    )

    assert provider.gradio_auth() is not None


# ---- Warnung, wenn die App im Netz hängt und niemand sich anmelden muss ----


@pytest.mark.parametrize(
    "host, has_auth, expect_warning",
    [
        ("0.0.0.0", False, True),  # im Netz, ohne Login → laut
        ("192.168.1.20", False, True),  # feste LAN-Adresse, ohne Login → laut
        ("0.0.0.0", True, False),  # im Netz, aber mit Login → in Ordnung
        ("127.0.0.1", False, False),  # nur lokal → niemanden geht es etwas an
        ("localhost", False, False),
        ("::1", False, False),
    ],
)
def test_exposure_warning_only_when_it_matters(host, has_auth, expect_warning, caplog):
    """Zwei harmlose Einstellungen, deren Kombination es nicht ist.

    `ui.web.host` und `ui.web.auth` stehen in der Config weit auseinander. Dass
    die App im Netz hängt *und* niemanden nach einem Passwort fragt, sieht man
    beim Lesen deshalb leicht nicht.

    Bewusst nur eine Warnung: „im Heimnetz ohne Login" ist ein legitimer
    Betriebsmodus. Abgebrochen wird nur, wenn eine Anmeldung konfiguriert, aber
    kaputt ist — dort wollte jemand ausdrücklich Schutz.
    """
    from ui.web_ui import _warn_if_exposed_without_login

    with caplog.at_level(logging.WARNING):
        _warn_if_exposed_without_login(
            host, 7860, (lambda u, p: True) if has_auth else None
        )

    assert ("[SICHERHEIT]" in caplog.text) is expect_warning
