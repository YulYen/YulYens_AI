"""Wer bedient die Web-UI? — die Identitäts-Naht (#53).

**Der Wert liegt in der Naht, nicht im Feature.** Für den Einzelplatz-Betrieb
ist eine Anmeldung reiner Aufwand; gebraucht wird sie, weil Gesprächslogs und
Feedback-Votes ohne Nutzerbegriff niemandem zugeordnet werden können — genau
das brauchen #25 (Verlauf-Tab), #40b und #24 (Langzeit-Gedächtnis).

**Ehrliche Einordnung:** Gradios Basic-Auth geht über HTTP im Klartext. Ohne
TLS ist das eine *Trennung* von Nutzern, kein Schutz gegen jemanden, der
mitliest. Wer echten Schutz braucht, stellt einen Reverse-Proxy davor — und
genau dafür gibt es :class:`HeaderAuth`.

**Warum kein OIDC/Keycloak hier:** Gradios ``auth=``-Callable bekommt nur
Benutzername und Passwort. Es gibt keinen Redirect-Flow und keine
Token-Validierung, ein echter OIDC-Client ließe sich darin nicht unterbringen.
Der realistische Weg ist oauth2-proxy oder Authelia davor, die die
authentifizierte Identität als Header durchreichen — deshalb ist ``HeaderAuth``
Teil der ersten Fassung und nicht ein späterer Umbau.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from core.utils import LOCAL_USER, resolve_secret


@dataclass(frozen=True)
class Identity:
    """Wer gerade bedient. ``source`` sagt, woher das Wissen stammt."""

    name: str
    source: str  # "disabled" | "local" | "header" | "anonymous"

    @property
    def is_known(self) -> bool:
        return bool(self.name) and self.source != "anonymous"


ANONYMOUS = Identity(name="", source="anonymous")


class AuthProvider(Protocol):
    """Zwei Fragen: wie meldet man sich an, und wer ist da gerade."""

    name: str

    def gradio_auth(self) -> Any | None:
        """Wert für ``demo.launch(auth=…)`` — ``None`` heißt: kein Login."""

    def identity_from_request(self, request: Any) -> Identity:
        """Identität zu einem Gradio-Request (``gr.Request``)."""


class DisabledAuth:
    """Default: kein Login, alle sind ``local``.

    Verhält sich damit exakt wie das Projekt vor #53 — wer allein am eigenen
    Rechner arbeitet, soll von diesem Ticket nichts merken.
    """

    name = "disabled"

    def gradio_auth(self) -> None:
        return None

    def identity_from_request(self, request: Any) -> Identity:
        return Identity(name=LOCAL_USER, source=self.name)


class LocalUsersAuth:
    """Benutzer/Passwort aus der Config.

    Passwörter über die Projekt-Konvention (``env:NAME`` / ``${NAME}``), damit
    Klartext-Geheimnisse nicht in der eingecheckten ``config.yaml`` landen.
    Nutzer ohne auflösbares Passwort werden verworfen **und** gemeldet — sonst
    stünde jemand vor einem Login, das nie aufgeht.
    """

    name = "local"

    def __init__(self, users: dict[str, Any] | None) -> None:
        self._users: dict[str, str] = {}
        for username, secret in (users or {}).items():
            resolved = resolve_secret(secret)
            if not str(username).strip() or not resolved:
                logging.warning(
                    "[AUTH] Nutzer '%s' hat kein auflösbares Passwort und wird "
                    "übersprungen (env:-Variable gesetzt?).",
                    username,
                )
                continue
            self._users[str(username)] = resolved

    @property
    def usernames(self) -> list[str]:
        return sorted(self._users)

    def check(self, username: str, password: str) -> bool:
        expected = self._users.get(username or "")
        # Kein früher Abbruch bei unbekanntem Nutzer: sonst verrät die Laufzeit,
        # welche Namen existieren.
        return bool(expected) and _constant_time_equals(expected, password or "")

    def gradio_auth(self):
        if not self._users:
            # Ohne gültige Nutzer wäre die App unbedienbar. Lieber offen und
            # laut als zugesperrt und rätselhaft.
            logging.error(
                "[AUTH] provider='local', aber kein einziger Nutzer ist nutzbar — "
                "die Anmeldung bleibt deshalb aus."
            )
            return None
        return self.check

    def identity_from_request(self, request: Any) -> Identity:
        username = getattr(request, "username", None)
        if not username:
            return ANONYMOUS
        return Identity(name=str(username), source=self.name)


class HeaderAuth:
    """Identität aus einem Header, den ein vorgeschalteter Proxy setzt.

    Das ist der Weg zu Keycloak & Co.: oauth2-proxy oder Authelia
    authentifizieren, dieser Provider glaubt ihnen. **Er glaubt dem Header
    bedingungslos** — er darf deshalb nur hinter einem Proxy laufen, der den
    Header von außen entfernt. Steht so auch in der Doku.
    """

    name = "header"

    def __init__(self, header_name: str = "X-Forwarded-User") -> None:
        self.header_name = (header_name or "X-Forwarded-User").strip()

    def gradio_auth(self) -> None:
        # Der Proxy hat die Anmeldung schon erledigt.
        return None

    def identity_from_request(self, request: Any) -> Identity:
        headers = getattr(request, "headers", None)
        value = ""
        if headers is not None:
            try:
                value = headers.get(self.header_name) or ""
            except AttributeError:  # pragma: no cover - exotische Request-Doubles
                value = ""
        if not value:
            return ANONYMOUS
        return Identity(name=str(value), source=self.name)


def _constant_time_equals(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


def build_auth_provider(web_cfg: dict | None) -> AuthProvider:
    """Baut den Provider aus ``ui.web``.

    Fällt auf das alte ``share_auth`` zurück, wenn kein ``auth``-Abschnitt
    existiert: bestehende Installationen sollen durch #53 nicht kaputtgehen.
    Neu ist dabei, dass die Anmeldung **unabhängig von ``share``** greift — vorher
    horchte die App auf ``0.0.0.0``, verlangte im LAN aber nichts.
    """
    web_cfg = web_cfg or {}
    auth_cfg = web_cfg.get("auth")

    if not isinstance(auth_cfg, dict):
        legacy = web_cfg.get("share_auth") or {}
        username = str(legacy.get("username") or "").strip()
        password = legacy.get("password") or ""
        if username and password:
            logging.warning(
                "[AUTH] 'ui.web.share_auth' ist veraltet — bitte auf "
                "'ui.web.auth' umstellen (provider: local). Die Anmeldung gilt "
                "jetzt auch ohne share."
            )
            return LocalUsersAuth({username: password})
        return DisabledAuth()

    provider = str(auth_cfg.get("provider") or "disabled").strip().lower()
    if provider == "local":
        return LocalUsersAuth(auth_cfg.get("users"))
    if provider == "header":
        return HeaderAuth(str(auth_cfg.get("header_name") or "X-Forwarded-User"))
    if provider not in ("disabled", ""):
        logging.warning(
            "[AUTH] Unbekannter provider '%s' — es bleibt bei 'disabled'.", provider
        )
    return DisabledAuth()
