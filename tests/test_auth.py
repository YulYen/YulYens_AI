"""Identitäts-Naht der Web-UI (#53).

Der Wert liegt in der Naht, nicht im Feature — deshalb prüfen die Tests vor
allem zwei Dinge: dass der Default sich exakt wie vorher verhält, und dass die
Identität dort ankommt, wo #25/#24 sie später brauchen (Gesprächslog, Votes).
"""

from types import SimpleNamespace

import pytest
from auth import (
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


def test_local_auth_without_usable_users_does_not_lock_everyone_out(caplog):
    """Lieber offen und laut als zugesperrt und rätselhaft."""
    provider = LocalUsersAuth({})

    assert provider.gradio_auth() is None
    assert "kein einziger Nutzer" in caplog.text


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
