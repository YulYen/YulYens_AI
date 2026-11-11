"""Eine Ask-All-Runde in der WebUI: Kontext, Broadcast, Fazit.

Herausgelöst aus `web_ui.py`, weil dieser Weg inzwischen **eigene Regeln**
besitzt — der Maßstab aus `docs/entwurf/webui.md` („ein Modul bekommt eine
Regel, nicht hundert Zeilen"). Als #56 die Handler stehen ließ, hatten sie
keine; seither sind vier dazugekommen, und jede ist einmal als Fehler
passiert:

1. **Erst der Guard, dann das Netz (#88).** Ask-All hat beim Nachschlagen noch
   keinen Streamer; der Guard kommt deshalb frisch aus der Factory. Die Absage
   selbst liefert danach jede Persona aus ihrem eigenen Stream.
2. **Der Kill-Switch gehört dieser Runde und wird vom Broadcast nur gelesen
   (#27).** `stop` ist hier ein verlässliches „der Nutzer hat abgebrochen" —
   nur deshalb darf das Fazit dahinter stehen. Früher setzte der Broadcast ihn
   beim normalen Ende selbst, und das Fazit wurde nie erreicht.
3. **Das Fazit ist Zugabe.** Ein Fehler dort darf die Runde nicht mitnehmen:
   der Schluss-Yield gibt die Eingabe wieder frei, komme was wolle.
4. **Wiki-Hinweis und Quellen reisen in jedem Yield mit (#32a)** — sie
   entstehen einmal vorab, und ein Yield ohne sie blendete sie wieder aus.

Aufgezeichnet wird nichts (#77).

Hält wie `ChatController` **keinen** Sitzungszustand: der liegt im
`SessionContext`. Was hier steht, kommt beim Bauen herein und ist für alle
Sitzungen gleich.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import gradio as gr
from config.personas import get_all_persona_names
from core.ask_all_moderator import iter_verdict
from core.orchestrator import iter_broadcast_events, iter_broadcast_events_parallel
from security.tinyguard import input_refused
from ui.session import SessionContext
from ui.webui_chat import STREAM_FLUSH_INTERVAL_S
from ui.webui_format import format_ask_all_results, format_wiki_sources
from wiki.lookup import WikiLookup, inject_wiki_context

if TYPE_CHECKING:
    from core.factory import AppFactory

Message = dict[str, str]


class AskAllController:
    """Der streamende Antwortweg „Frage an alle"."""

    def __init__(
        self,
        t: Callable[..., str],
        factory: AppFactory,
        wiki: WikiLookup,
        *,
        enabled: bool,
        parallel: bool,
        placeholder: str,
    ) -> None:
        self._t = t
        self.factory = factory
        self.wiki = wiki
        self.enabled = enabled
        self.parallel = parallel
        self.placeholder = placeholder

    @staticmethod
    def cancel(session: SessionContext) -> None:
        """Stoppt die Worker einer laufenden Runde dieser Sitzung (falls vorhanden)."""
        stop = session.ask_all_stop
        if stop is not None:
            stop.set()
            session.ask_all_stop = None

    def state(
        self,
        question: str,
        results_md: str,
        *,
        editable: bool = False,
        submit_visible: bool = True,
        submit_interactive: bool = True,
        status: str = "",
        sources_md: str = "",
    ) -> tuple:
        """Builds the tuple of updates every Ask-All yield consists of.

        ``sources_md`` läuft wie ``status`` durch alle Yields mit: der
        Wiki-Lookup passiert einmal vorab, das Ergebnis muss danach in jedem
        Update wieder mitgeschickt werden (#32a).

        Der Default ist der **laufende** Broadcast: Eingabe gesperrt, Senden
        weg. Vorher stand dafür ein `running`-dict, das an drei Stellen mit
        `**` hineingereicht wurde — eine Form, die weder mypy noch ein Leser
        auf die Parameter abbilden kann. Die drei Werte gehören ohnehin
        zusammen; sie einzeln setzen konnte niemand gebrauchen.
        """
        return (
            gr.update(
                value=question,
                visible=True,
                interactive=editable,
                placeholder=self.placeholder,
            ),
            gr.update(value=status, visible=bool(status)),
            gr.update(value=results_md, visible=bool(results_md)),
            gr.update(visible=submit_visible, interactive=submit_interactive),
            gr.update(visible=True),
            gr.update(visible=bool(sources_md)),
            gr.update(value=sources_md),
        )

    def submit(
        self,
        session: SessionContext,
        question: str | None,
        current_results: str | None = None,
        with_verdict: bool = False,
    ) -> Iterator[tuple]:
        question = (question or "").strip()
        existing = current_results or ""

        if not self.enabled:
            yield self.state(
                question,
                existing,
                editable=True,
                submit_interactive=False,
                status=self._t("ask_all_disabled"),
            )
            return

        if not question:
            yield self.state(
                "",
                existing,
                editable=True,
                status=self._t("empty_question"),
            )
            return

        # Alle Personas vorab mit Platzhalter anlegen, dann Token für Token
        # hineinstreamen; gedrosselt, damit nicht jedes Token den kompletten
        # Markdown-Block über den Socket schickt.
        replies = {name: "…" for name in get_all_persona_names()}
        yield self.state(
            question,
            format_ask_all_results(replies),
        )

        # Wiki-Lookup einmal für alle Personas; Hints nur anzeigen, Snippets
        # als geteilter System-Kontext vor die Frage jedes Broadcasts legen.
        # Erst der Guard, dann das Netz (#88) — die Absage selbst liefert danach
        # jede Persona aus ihrem eigenen `stream()`.
        wiki_hints, contexts = (
            ([], [])
            if input_refused(self.factory.build_guard(), question)
            else self.wiki.snippets(question, "ask_all", self.factory.build_guard())
        )
        context_messages: list[Message] = []
        if contexts:
            # Ask-All hat hier noch keinen Streamer: der Kontext entsteht
            # einmal für alle Personas, bevor die Worker gebaut werden.
            inject_wiki_context(context_messages, contexts, self.factory.build_guard())
        wiki_status = "\n\n".join(hint for hint in wiki_hints if hint)
        # Die Quellen stehen hier bereits fest und reisen ab jetzt in jedem
        # Yield mit — genau wie wiki_status (#32a).
        sources_md = format_wiki_sources(contexts, self._t)
        if wiki_status or sources_md:
            yield self.state(
                question,
                format_ask_all_results(replies),
                status=wiki_status,
                sources_md=sources_md,
            )

        # Der Kill-Switch gilt in beiden Zweigen: der sequenzielle Broadcast
        # kennt ihn zwar nicht, das Fazit danach (#27) aber schon — sonst liefe
        # ein zusätzlicher Modelllauf weiter, nachdem der Nutzer abgebrochen hat.
        stop = threading.Event()
        session.ask_all_stop = stop

        # Parallel: alle Personas streamen gleichzeitig in ihre Sektionen;
        # sequenzieller Fallback per ui.experimental.broadcast_parallel: false.
        if self.parallel:
            events_iter = iter_broadcast_events_parallel(
                self.factory,
                question,
                context_messages=context_messages,
                stop_event=stop,
            )
        else:
            events_iter = iter_broadcast_events(
                self.factory, question, context_messages=context_messages
            )
        # Der laufende Text wird hier gesammelt, nicht vom Orchestrator in jedes
        # Token-Event gelegt (#64d). Zusammengefügt wird nur, wenn wirklich
        # gezeigt wird — also ein paar Mal pro Sekunde statt einmal pro Token.
        parts: dict[str, list[str]] = {name: [] for name in replies}
        finished: set[str] = set()
        last_flush = 0.0
        for event in events_iter:
            persona = event["persona"]
            if event["type"] == "done":
                # Der fertige Text ist der maßgebliche — er ist gestrippt.
                replies[persona] = event["reply"] or "…"
                finished.add(persona)
            else:
                parts.setdefault(persona, []).append(event["token"])

            now = time.monotonic()
            if event["type"] == "done" or now - last_flush >= STREAM_FLUSH_INTERVAL_S:
                for name, chunks in parts.items():
                    if name not in finished and chunks:
                        replies[name] = "".join(chunks)
                last_flush = now
                yield self.state(
                    question,
                    format_ask_all_results(replies),
                    status=wiki_status,
                    sources_md=sources_md,
                )

        # Das Fazit läuft *nach* der Runde und nur auf Wunsch (#27): es kostet
        # einen vollen Modelllauf. Bricht der Nutzer ab, bleibt der Text stehen,
        # den es bis dahin geschrieben hat — wie „Stop" im Einzelchat.
        verdict = ""
        verdict_heading = self._t("ask_all_moderator_heading")
        # `stop` ist hier ein verlässliches „der Nutzer hat abgebrochen": der
        # Broadcast setzt es seit dieser Runde nicht mehr selbst (siehe
        # `iter_broadcast_events_parallel`).
        if with_verdict and not stop.is_set():
            verdict_parts: list[str] = []
            last_flush = 0.0
            try:
                for event in iter_verdict(
                    self.factory, question, replies, stop_event=stop
                ):
                    if event["type"] == "done":
                        verdict = event["reply"]
                    else:
                        verdict_parts.append(event["token"])

                    now = time.monotonic()
                    if (
                        event["type"] == "done"
                        or now - last_flush >= STREAM_FLUSH_INTERVAL_S
                    ):
                        last_flush = now
                        yield self.state(
                            question,
                            format_ask_all_results(
                                replies,
                                verdict=verdict or "".join(verdict_parts),
                                verdict_heading=verdict_heading,
                            ),
                            status=wiki_status,
                            sources_md=sources_md,
                        )
            except Exception:
                # Das Fazit ist Zugabe — es darf die Runde nicht mitnehmen.
                # Ohne diesen Riegel bliebe die Eingabe gesperrt und
                # `session.ask_all_stop` stehen: der Schluss-Yield unten wird
                # nie erreicht, und der Nutzer verlöre Bedienbarkeit und
                # Antworten für einen Fehler im Nachspann.
                logging.exception("Ask-All: das Fazit ist fehlgeschlagen")

        session.ask_all_stop = None
        # Broadcast fertig: Eingabe und Senden wieder freigeben für Folgefragen
        yield self.state(
            question,
            format_ask_all_results(
                replies, verdict=verdict, verdict_heading=verdict_heading
            ),
            status=wiki_status,
            sources_md=sources_md,
            editable=True,
        )
