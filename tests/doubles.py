"""Test-Doubles, die nicht von der echten Schnittstelle abdriften können (#67).

**Warum das ein eigenes Modul ist.** An einem einzigen Tag ist viermal dasselbe
passiert: ein Kollaborateur bekam eine Methode dazu, und die Doubles blieben
zurück — Mock-Streamer ohne ``guard``, ``AllowAllGuard`` ohne
``output_match_crossing``, ``SimpleNamespace``-Streamer ohne
``record_conversation``, Mock-Factory ohne ``build_guard``.

Das ging in zwei Richtungen, und nur eine davon war laut:

* **Laut:** handgeschriebene Doubles (``SimpleNamespace``, eigene Stub-Klassen)
  scheitern mit ``AttributeError``, sobald der Produktivcode etwas Neues ruft.
  Ärgerlich, aber der Fehler zeigt wenigstens hin.
* **Still — und teuer:** ein nacktes ``Mock()`` liefert für *jedes* Attribut ein
  wahrheitswertiges Mock. ``getattr(streamer, "guard", None)`` bekam damit nie
  ``None``, sondern ein Objekt, das gar keine Prüfung ist. Der Test blieb grün,
  obwohl die Verdrahtung falsch war, und fiel erst tief im Guard mit
  ``'Mock' object is not subscriptable``.

**Die Lösung ist ``create_autospec``, nicht mehr Disziplin.** Sie erledigt beide
Richtungen von selbst:

* Neue Methoden am Produktivcode sind am Double **automatisch** da — kein
  Nachziehen mehr nötig.
* Instanzattribute, die niemand gesetzt hat, fehlen ehrlich. ``getattr(…, None)``
  liefert damit ``None`` statt eines truthy Mocks — genau das Verhalten, das der
  Produktivcode erwartet.
* Aufrufe mit falscher Signatur fliegen als ``TypeError`` auf, statt stumm
  aufgezeichnet zu werden.

**Die Frage aus dem Ticket ist damit beantwortet:** Klassen-Annotationen an
``YulYenStreamingProvider`` braucht es *nicht*. Sie würden ``guard`` und
``persona_options`` zwar in ``dir()`` sichtbar machen — aber das ist gar nicht
das Problem. Ein nie gesetztes Attribut *soll* fehlen; nur dann verhält sich das
Double wie ein Objekt, an dem der Aufrufer noch nichts konfiguriert hat.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import create_autospec

from auth import DisabledAuth
from core.factory import AppFactory
from core.streaming_provider import YulYenStreamingProvider
from rss.feeds import RssCache
from security.tinyguard import BasicGuard
from storage import NullStore


def streamer_double(**overrides: Any):
    """Ein Streamer-Double nach dem Vorbild des echten Streamers.

    Vorbelegt ist nur, was praktisch jeder Test braucht. Alles andere fehlt
    bewusst — ``guard`` etwa, damit ``getattr(streamer, "guard", None)``
    ``None`` ergibt und der Kontext-Filter nicht gegen ein Phantom läuft.
    """
    double = create_autospec(YulYenStreamingProvider, instance=True)
    double.persona_options = {}
    double.model_name = "dummy"
    double.last_stream_stats = None
    # Bewusst eine Liste und kein `iter([])`: der Produktivcode iteriert nur,
    # und ein Iterator wäre nach dem ersten `stream()`-Aufruf stumm leer.
    double.stream.return_value = []
    for name, value in overrides.items():
        setattr(double, name, value)
    return double


def permissive_guard_double(**overrides: Any):
    """Ein Guard, der alles durchlässt — ohne eigene Stub-Klasse.

    Ersetzt das handgeschriebene ``AllowAllGuard``: das musste bei jeder neuen
    Guard-Methode nachgezogen werden und ist genau deshalb zweimal aufgelaufen.

    ``enabled``/``flags`` bleiben ungesetzt, damit ``_output_checks_active``
    ``False`` liefert und der Holdback entfällt — dasselbe Verhalten wie beim
    bisherigen Stub, nur ohne Wartungslast.
    """
    double = create_autospec(BasicGuard, instance=True)
    double.check_input.return_value = {"ok": True, "reason": "ok", "detail": None}
    double.check_output.return_value = {"ok": True, "reason": "ok", "detail": None}
    double.process_output.side_effect = lambda text: {
        "blocked": False,
        "reason": None,
        "text": text,
        "masked": False,
    }
    double.output_match_crossing.return_value = None
    for name, value in overrides.items():
        setattr(double, name, value)
    return double


def factory_double(**overrides: Any):
    """Eine AppFactory nach dem Vorbild der echten.

    Vorbelegt ist, was sonst als *wahrheitswertiges* Mock durchginge und damit
    die stille Richtung öffnet:

    * ``build_guard()`` — sonst prüft der Kontext-Filter gegen etwas, das keine
      Prüfung ist.
    * ``get_auth_provider()`` — sonst ist ``gradio_auth()`` ein Mock statt
      ``None``, und die Web-UI startet im Test mit einer Anmeldung, die es nicht
      gibt.
    * ``get_store()`` — sonst ist ``records`` ein truthy Mock, und ein Test
      gegen eine abgeschaltete Ablage liefe gegen eine eingeschaltete.
    * ``get_rss_cache()`` — sonst ist ``feed_names`` ein truthy Mock, und der
      Briefing-Knopf erscheint in einer Oberfläche ohne konfigurierte Feeds
      (#73). Genau so aufgefallen: ein Test, der „standardmäßig aus" prüft,
      bekam „an".

    Alle drei sind die echten Produktionsvorgaben, nicht Attrappen: kein
    Login, keine Ablage, keine Feeds.
    """
    double = create_autospec(AppFactory, instance=True)
    double.build_guard.return_value = None
    double.get_auth_provider.return_value = DisabledAuth()
    double.get_store.return_value = NullStore()
    double.get_rss_cache.return_value = RssCache(feeds=[])
    return _apply(double, overrides)


def _apply(double: Any, overrides: dict[str, Any]) -> Any:
    for name, value in overrides.items():
        setattr(double, name, value)
    return double
