"""Das Register der Kontext-Kanäle — die einzige Tür in den Prompt (#75).

Abgerufener Fremdtext betritt den Prompt an genau zwei Stellen: ein
Wikipedia-Snippet aus einer heruntergeladenen ZIM-Datei, eine Meldung aus einem
abonnierten Feed. Beide werden gefiltert (``accepted_context``) und markiert
(``injected_message``) — bisher aber **jeder für sich**, an je eigener Stelle.
Das war richtig und ist dokumentiert; die Lücke lag woanders: ein *dritter*
Kanal, der ``injected_message`` direkt benutzt und den Guard vergisst, sähe
völlig unauffällig aus. Er wäre eine Injection-Lücke mit System-Autorität,
weil direkt davor eine ``system``-Anweisung steht, genau diesem Kontext zu
folgen.

**Deshalb ist das Filtern hier keine Höflichkeit des Aufrufers, sondern der
Weg selbst.** :func:`inject_context` filtert, klammert, markiert und hängt an —
in einem Aufruf, ohne Schalter zum Weglassen. Am Guard vorbei kommt nur, wer
diese Tür umgeht, und genau das nagelt ``tests/test_context_channels.py``
fest: ``injected_message`` wird in ``src/`` von niemandem sonst gerufen.

**Der Kanal muss im Register stehen.** Ein ad hoc gebautes
:class:`ContextChannel` wird abgewiesen, nicht durchgereicht. Das ist der
zweite Grund für dieses Modul: eine neue Quelle trägt sich in ``CHANNELS``
ein, und damit prüft der Test ihren Guardrail-Text in beiden Locales mit —
statt dass sie mit einem fehlenden Locale-Key still ohne Guardrail injiziert.

**Gefiltert wird über die Einträge, nicht über das Ergebnis** — und dass die
Tür beides in der Hand hat, ist der Grund, warum sie es garantieren kann:
``bodies_of`` sieht ausschließlich das, was der Guard durchgelassen hat.

Der erste Entwurf ließ RSS seinen Block wie bisher selbst zusammenfügen und
schickte nur diesen einen Block durch die Tür — mit der Begründung, ein
zweiter Durchgang könne nichts verschlimmern, weil die Guard-Brücken seit #62
keine Zeilengrenze überspringen. **Die Begründung war falsch, und der Test hat
sie widerlegt:** ``[^,.!?\\n]`` steht nur in einem Teil der Regeln, andere
verbinden mit ``\\s+`` — und das schließt ``\\n`` ein. Zwei harmlose
Schlagzeilen, die zufällig aneinandergrenzen, hätten den ganzen
Nachrichtenblock gerissen, still und schwer zu finden. Der Fall steht als
``test_the_guard_bridges_can_span_a_line_break`` im Korpus, damit die Annahme
nicht ein zweites Mal plausibel wirkt.

**Die frühere Filterung bleibt trotzdem, wo sie ist.**
``WikiLookup.snippets()`` filtert weiter selbst, weil die Quellen-Karte (#32)
sonst Ausschnitte auflistet, die das Modell nie gesehen hat. Für das Wiki ist
der zweite Durchgang hier gefahrlos: er prüft *dieselben* Einheiten, ist also
schlicht idempotent. Die Asymmetrie zu RSS ist damit keine mehr — beide Kanäle
filtern genau einmal pro Einheit, die sie auch injizieren.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from config.config_singleton import Config
from security.tinyguard import BasicGuard, accepted_context

from core.context_injection import injected_message


@dataclass(frozen=True)
class ContextChannel:
    """Eine Quelle abgerufenen Fremdtexts.

    ``name`` ist der Marker-Wert an der injizierten Nachricht (``"wiki"``,
    ``"rss"``) und taucht so im Mitschnitt auf. ``guardrail_key`` ist der
    Locale-Key der ``system``-Anweisung, die dem zitierten Block vorangeht —
    unser eigener Satz, der Systemautorität haben darf.
    """

    name: str
    guardrail_key: str


@dataclass(frozen=True)
class Injection:
    """Was die Tür durchgelassen und was sie verworfen hat.

    ``injected`` ist die Zahl angehängter Fremdtext-Nachrichten, nicht die der
    angenommenen Einträge — RSS fügt viele Meldungen zu **einer** zusammen. Die
    Oberflächen brauchen genau diese Unterscheidung: ``dropped`` speist den
    Hinweis „Quellen verworfen", ``injected`` die Entscheidung, ob überhaupt
    etwas zu erzählen ist.
    """

    injected: int
    dropped: int

    def __bool__(self) -> bool:
        return self.injected > 0


WIKI = ContextChannel("wiki", "wiki_context_guardrail")
RSS = ContextChannel("rss", "rss_context_guardrail")

# Wer eine dritte Quelle baut, trägt sie hier ein — sonst weist
# `inject_context` sie ab. Die Liste ist damit die Antwort auf „welche Kanäle
# gibt es?", und zwar eine, die nicht veralten kann.
CHANNELS: dict[str, ContextChannel] = {channel.name: channel for channel in (WIKI, RSS)}


def inject_context(
    history: list,
    channel: ContextChannel,
    items: Sequence[Any],
    *,
    guard: BasicGuard | None = None,
    text_of: Callable[[Any], str],
    label_of: Callable[[Any], str],
    bodies_of: Callable[[list[Any]], list[str]],
) -> Injection:
    """Hängt Guardrail + zitierten Fremdtext an ``history``.

    ``text_of`` liefert den Text, den der Guard sieht, ``label_of`` den Namen
    für die Logzeile. ``bodies_of`` macht aus den *angenommenen* Einträgen die
    Nachrichtentexte.

    **Die Reihenfolge ist die eigentliche Zusicherung: erst filtern, dann
    zusammenfügen.** ``bodies_of`` bekommt ausschließlich das, was der Guard
    durchgelassen hat — der Kanal *kann* gar nicht zuerst zusammenfügen. Für
    RSS ist das keine Kosmetik, sondern die Regel aus #73: über den fertigen
    Block geprüft, risse eine einzige schräge Schlagzeile alle anderen mit
    (nachgemessen in ``test_the_guard_bridges_can_span_a_line_break``). Genau
    deshalb ist die Liste eine Liste: das Wiki hängt eine Nachricht **je
    Snippet** an, RSS fügt alle Meldungen zu **einer** zusammen. Der Zuschnitt
    gehört dem Kanal, das Filtern und Markieren dieser Funktion.

    ``guard=None`` lässt alles durch — wie bei ``inject_wiki_context`` seit
    jeher, damit Aufrufer ohne Guard und die Bestandstests unverändert bleiben.
    Das ist die eine Stelle, an der ein Kanal sich selbst entwaffnen kann; sie
    ist es wert, weil die Alternative (Pflichtparameter) jeden Testaufbau
    zwingt, einen echten Guard zu bauen.
    """
    if CHANNELS.get(channel.name) is not channel:
        raise ValueError(
            f"Unbekannter Kontext-Kanal {channel.name!r}. Kanäle tragen sich in "
            "core.context_channels.CHANNELS ein — sonst prüft nichts ihren "
            "Guardrail-Text."
        )

    accepted = accepted_context(guard, list(items), text_of=text_of, label_of=label_of)
    dropped = len(items) - len(accepted)
    if not accepted:
        return Injection(injected=0, dropped=dropped)

    cfg = Config()
    bodies = bodies_of(accepted)
    if not bodies:
        return Injection(injected=0, dropped=dropped)

    history.append({"role": "system", "content": cfg.t(channel.guardrail_key)})
    for body in bodies:
        history.append(
            injected_message(cfg.t("context_quote_wrapper", body=body), channel.name)
        )
    return Injection(injected=len(bodies), dropped=dropped)
