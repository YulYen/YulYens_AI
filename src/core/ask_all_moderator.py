"""Das Fazit über eine Ask-All-Runde (#27).

Die Regel, die dieses Modul besitzt: **die Antworten werden gekürzt, bevor sie
in den Prompt gehen — und das Fazit ist ein Artefakt, kein Gespräch.**

Vier Antworten an ein 8k-Kontextfenster zu hängen ist der naheliegende Fehler:
es geht meistens gut und reißt genau dann, wenn die Personas ausführlich waren.
Deshalb bekommt jede Antwort ein Zeichenbudget, abgeleitet aus dem ``num_ctx``
des Ensembles statt fest verdrahtet.

Zwei Entwurfsentscheidungen, die man beim Anfassen leicht umdreht:

1. **Kein Kontext-Kanal (#75).** Die vier Antworten sind kein abgerufener
   Fremdtext, sondern die eigene Modellausgabe desselben Turns — sie sind auf
   dem Weg nach draußen bereits durch ``_StreamModerator`` gelaufen (PII
   maskiert, Blocklist angewandt). Sie hier ein zweites Mal durch
   ``inject_context`` zu schicken prüfte die Maskierung, nicht das Modell —
   dasselbe Argument, mit dem ``respond_one_shot`` keine zweite
   ``check_output`` fährt. Vorbild ist Karl (``context_summarizer``), der
   Gesprächsverlauf ebenso direkt in einen Prompt gibt.
2. **Aufgezeichnet wird nichts.** Ask-All zeichnet bewusst nicht auf (das
   Datenmodell der Ablage ist „eine Persona, ein Faden"), und ein Fazit über
   vier Fäden passt dort noch weniger hinein. Der Streamer bekommt deshalb nie
   eine Gesprächs-ID; ``record_conversation`` wird hier nicht gerufen.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Mapping

from config import personas
from config.config_singleton import Config

from core.context_utils import chars_per_token

# Interner Name des Moderator-Streamers. Er taucht nur im Log und im
# JSONL-Mitschnitt auf — die Überschrift im UI kommt aus den Locales.
MODERATOR_PERSONA = "MODERATOR"

# Wie viel des Kontextfensters die Antworten zusammen belegen dürfen. Der Rest
# trägt Systemprompt, Frage und das Fazit selbst.
PROMPT_BUDGET_RATIO = 0.5

# Nur als letzte Rückfallebene: ein Ensemble ohne `num_ctx` in den Optionen.
DEFAULT_NUM_CTX = 8192

# Unter zwei verwertbaren Antworten gibt es nichts zu moderieren — ein „Fazit"
# über eine einzige Antwort wäre eine Umformulierung zum vollen Modellpreis.
MIN_REPLIES = 2

# Kürzeste sinnvolle Antwortlänge; darunter schneidet das Budget mitten im
# ersten Satz und der Moderator bekommt vier Wortfetzen.
MIN_CHARS_PER_REPLY = 200


def usable_replies(replies: Mapping[str, str]) -> dict[str, str]:
    """Antworten, über die sich ein Fazit lohnt.

    Fällt der Platzhalter „…" der noch laufenden Sektionen heraus, ebenso wie
    leere Antworten — eine abgebrochene Runde soll kein Fazit über Auslassungs-
    zeichen erzeugen.
    """
    usable: dict[str, str] = {}
    for persona, reply in replies.items():
        text = (reply or "").strip()
        if not text or text == "…":
            continue
        usable[persona] = text
    return usable


def moderator_options() -> dict:
    """Die Optionen der ruhigsten Persona — abgeleitet, nicht verdrahtet.

    Dieselbe Wahl wie beim Bench-Default (#42): die niedrigste Temperatur
    liefert die sachlichste Zusammenfassung, und abgeleitet stimmt sie auch für
    ein fremdes Ensemble. Zusammenfassen ist keine kreative Aufgabe.
    """
    names = personas.get_all_persona_names()
    if not names:
        return {}
    return dict(personas.get_options(personas.quietest_persona_name(names)) or {})


def reply_char_budget(count: int, num_ctx: int) -> int:
    """Zeichen je Antwort, damit alle zusammen in den halben Kontext passen."""
    if count <= 0:
        return 0
    total = int(max(num_ctx, 0) * PROMPT_BUDGET_RATIO * chars_per_token)
    return max(MIN_CHARS_PER_REPLY, total // count)


def trim(text: str, budget: int, marker: str) -> str:
    """Kürzt auf ``budget`` Zeichen und sagt es dazu.

    Der Marker ist nicht Kosmetik: ohne ihn liest der Moderator einen mitten im
    Satz endenden Absatz als vollständige Antwort und zieht daraus Schlüsse.
    """
    if len(text) <= budget:
        return text
    return text[:budget].rstrip() + marker


def build_messages(
    question: str, replies: Mapping[str, str], *, num_ctx: int
) -> list[dict[str, str]]:
    """Frage und (gekürzte) Antworten als *eine* user-Nachricht.

    Die Anweisung an das Modell steht im Systemprompt des Streamers, der Stoff
    kommt als ``user`` — dieselbe Rollentrennung wie bei injiziertem Fremdtext
    (#60). Genau eine user-Nachricht, damit der Eingangs-Guard von ``stream()``
    sie auch sieht.
    """
    cfg = Config()
    budget = reply_char_budget(len(replies), num_ctx)
    marker = cfg.t("ask_all_moderator_truncated")
    blocks = [
        f"### {persona}\n{trim(reply, budget, marker)}"
        for persona, reply in replies.items()
    ]
    return [
        {
            "role": "user",
            "content": cfg.t(
                "ask_all_moderator_task",
                question=question.strip(),
                answers="\n\n".join(blocks),
            ),
        }
    ]


def iter_verdict(
    factory,
    question: str,
    replies: Mapping[str, str],
    *,
    stop_event: threading.Event | None = None,
) -> Iterator[dict[str, str]]:
    """Streamt das Fazit über eine fertige Ask-All-Runde.

    Yields:
        ``{"type": "token", "token": ...}`` je Token und zum Schluss genau ein
        ``{"type": "done", "reply": ...}``. Gibt es nichts zu moderieren, wird
        **gar nichts** geliefert — der Aufrufer zeigt die Sektion dann nicht an,
        statt eine leere Überschrift stehenzulassen.
    """
    usable = usable_replies(replies)
    if len(usable) < MIN_REPLIES:
        logging.info(
            "[ASK-ALL] Fazit übersprungen: %d verwertbare Antwort(en)", len(usable)
        )
        return

    options = moderator_options()
    try:
        num_ctx = int(options.get("num_ctx") or DEFAULT_NUM_CTX)
    except (TypeError, ValueError):
        num_ctx = DEFAULT_NUM_CTX

    messages = build_messages(question, usable, num_ctx=num_ctx)
    streamer = factory.get_streamer_for_guest(
        MODERATOR_PERSONA,
        Config().t("ask_all_moderator_system"),
        options,
    )

    parts: list[str] = []
    token_stream = streamer.stream(messages=messages)
    try:
        for token in token_stream:
            if stop_event is not None and stop_event.is_set():
                break
            parts.append(token)
            yield {"type": "token", "token": token}
    finally:
        # Schließt den Backend-Stream, auch wenn der Aufrufer uns zumacht.
        token_stream.close()
    yield {"type": "done", "reply": "".join(parts).strip()}
