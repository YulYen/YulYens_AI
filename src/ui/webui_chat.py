"""Ein Turn im Persona-Chat: Kontext holen, streamen, aufzeichnen (#56).

Das hier ist der Lebenszyklus einer Antwort — von „Nutzer drückt Senden" bis
„der Gesprächsstand steht in der Ablage". Er liegt in einem eigenen Modul, weil
er eine **Regel** besitzt und nicht bloß Zeilen: an ihm hängen vier Entscheidungen,
die das Projekt teuer erkauft hat und die man beim Umbau leicht umdreht.

1. **Die Button-Updates reisen im selben Yield wie der Text (#35).** Der
   naheliegende Weg — ein kleines Event vor dem Stream, `btn.click(toggle)
   .then(stream)` — kostete gemessen ~3,5 s bis zum ersten Token, weil das
   gequeuete `.then()` erst nach einem vollen Roundtrip startet. `with_controls`
   hängt sie stattdessen an jeden Yield an.

2. **Aufgezeichnet wird erst, wenn der Turn steht (#59).** Nicht in `stream()`,
   denn dort entstehen *Versuche*: „Nochmal 🔄" dreimal gedrückt schrieb drei
   Fragen und drei Antworten in die Ablage, während die Oberfläche eine zeigte,
   und „Stop ⏹" verlor die Antwort ganz. Deshalb genau ein
   `record_conversation` am Ende von `stream_reply` — **auch beim Abbruch**, denn
   die Teilantwort ist das, was der Nutzer behält.

3. **Der Kill-Switch wird über Identität geprüft, nicht über den Wert.** Ein
   neuer Stream ersetzt `session.stream_stop`; ein noch laufender alter
   Generator darf auf den Schalter des neuen nicht reagieren. Deshalb
   `session.stream_stop is stop` und nicht `stop.is_set()` allein.

4. **Hinweis-Bubbles bleiben aus der LLM-History heraus.** Wiki-Hinweis,
   RSS-Hinweis, Kompressionswarnung stehen in derselben Spalte wie eine Antwort,
   sind aber keine — und genau daran erkennt der Vote-Kanal sie (#40). Wer eine
   neue Hinweis-Bubble einführt, bekommt den Schutz geschenkt, solange er sie
   nicht ins Kontextfenster gibt.

**Die RSS-Schalter werden abgeleitet, nicht mitgeführt.** Vorher standen
`rss_cache`, `rss_enabled` und `briefing_enabled` als drei Felder nebeneinander,
die von Hand konsistent gehalten werden mussten — ein `rss_enabled = True` neben
einem Cache ohne Feeds war ein Zustand, den der Code widerspruchslos annahm.
Jetzt ist der Cache die einzige Eingabe und die beiden Schalter sind Properties.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

import gradio as gr
from config.personas import get_drink
from core.context_utils import context_near_limit, shrink_history_for_context
from core.streaming_provider import StreamStats
from rss.feeds import RssCache, build_context_block, inject_rss_context
from rss.trigger import feeds_for_question
from ui.session import SessionContext
from ui.webui_format import (
    ChatMessage,
    bot_bubble,
    format_status_line,
    format_wiki_sources,
    user_bubble,
)
from wiki.lookup import WikiLookup, WikiSnippet, inject_wiki_context

if TYPE_CHECKING:
    from config.config_singleton import Config

Message = dict[str, str]

# Wie oft gestreamte Updates höchstens an den Browser gehen (Sekunden). Ohne
# Drossel schickt Gradio ein Websocket-Frame pro Token. Der erste Chunk geht
# immer sofort durch (last_flush startet bei 0.0). Zweite Timing-Stellschraube
# neben security.stream_holdback_chars (#51).
STREAM_FLUSH_INTERVAL_S = 0.1


class ChatController:
    """Die streamenden Antwortwege der WebUI: Chat, Briefing, Nochmal.

    Hält **keinen** Sitzungszustand — der liegt im `SessionContext`, der durch
    jeden Aufruf gereicht wird (die WebUI ist ein Singleton für alle Browser).
    Was hier steht, ist für alle Sitzungen gleich.
    """

    def __init__(
        self,
        t: Callable[..., str],
        cfg: Config,
        wiki: WikiLookup,
        rss_cache: RssCache,
        rss_cfg: dict | None = None,
    ) -> None:
        self._t = t
        self.cfg = cfg
        self.wiki = wiki
        self.rss_cache = rss_cache
        self.rss_cfg = rss_cfg or {}

    # ---------- Abgeleitete Schalter ----------
    @property
    def rss_enabled(self) -> bool:
        """Die Quelle ist an, sobald Feeds konfiguriert sind."""
        return bool(self.rss_cache.feed_names)

    @property
    def briefing_enabled(self) -> bool:
        """Der Knopf ist eine zweite, getrennte Frage (#73)."""
        return self.rss_enabled and bool(self.rss_cfg.get("show_button", True))

    # ---------- Ablage ----------
    @staticmethod
    def record_conversation(
        session: SessionContext, messages: list[Message] | None
    ) -> None:
        """Den Gesprächsstand in die Ablage spiegeln (#59)."""
        recorder = getattr(session.streamer, "record_conversation", None)
        if callable(recorder):
            recorder(list(messages or []))

    # ---------- Kontext-Kompression ----------
    def handle_context_warning(
        self,
        session: SessionContext,
        llm_history: list[Message],
        chat_history: list[ChatMessage],
    ) -> bool:
        if not context_near_limit(llm_history, session.streamer.persona_options):
            return False

        drink = get_drink(session.bot or "")
        warn = self._t("context_wait_message", persona_name=session.bot, drink=drink)

        chat_history.append(bot_bubble(warn))

        persona_options = getattr(session.streamer, "persona_options", {}) or {}
        llm_history[:] = shrink_history_for_context(
            llm_history,
            self.cfg,
            persona_options,
            llm_core=getattr(session.streamer, "_llm_core", None),
            chat_model_name=getattr(session.streamer, "model_name", ""),
            persona_name=session.bot,
        )
        return True

    # ---------- Statuszeile (#36) ----------
    @staticmethod
    def last_stream_stats(session: SessionContext) -> StreamStats | None:
        """Kennzahlen des Providers — nur, wenn es wirklich welche sind.

        Vor dem ersten Stream ist das Attribut None; Testdoubles setzen es gar
        nicht. Die isinstance-Prüfung hält halbe Werte aus der Anzeige heraus,
        statt sie zu formatieren.
        """
        stats = getattr(session.streamer, "last_stream_stats", None)
        return stats if isinstance(stats, StreamStats) else None

    def status_update(
        self,
        session: SessionContext,
        history: list[Message] | None,
        stats: StreamStats | None,
    ) -> Any:
        line = format_status_line(
            self._t,
            getattr(session.streamer, "persona_options", None),
            history,
            stats,
        )
        return gr.update(value=line, visible=bool(line))

    # ---------- Wiki-Quellen (#32) ----------
    def wiki_source_updates(self, snippets: list[WikiSnippet] | None) -> tuple:
        """Accordion + Markdown; ohne Treffer bleibt das Accordion unsichtbar."""
        markdown = format_wiki_sources(snippets, self._t)
        return gr.update(visible=bool(markdown)), gr.update(value=markdown)

    @staticmethod
    def wiki_sources_unchanged() -> tuple:
        return gr.update(), gr.update()

    # ---------- Kill-Switch (#35) ----------
    @staticmethod
    def _arm_stream_stop(session: SessionContext) -> threading.Event:
        """Fresh kill switch for the stream that is about to start (#35)."""
        stop = threading.Event()
        session.stream_stop = stop
        return stop

    @staticmethod
    def _stop_requested(session: SessionContext, stop: threading.Event) -> bool:
        """True when *this* stream was asked to stop.

        Identity check on purpose: a newer stream replaces `stream_stop`, and a
        stale generator must not react to the new stream's switch.
        """
        return session.stream_stop is stop and stop.is_set()

    # ---------- Der Stream selbst ----------
    def stream_reply(
        self,
        session: SessionContext,
        message_history: list[Message],
        chat_history: list[ChatMessage],
    ) -> Iterator[tuple]:
        # Die Quellen-Slots stehen vor dem Stream schon fest und bleiben hier
        # unangetastet — gr.update() ohne Wert ist ein No-op für die Anzeige.
        keep = self.wiki_sources_unchanged()
        # Statuszeile erst im Schluss-Yield: Tempo und Füllstand stehen vorher
        # nicht fest, und jeder Wert pro Yield kostet Bandbreite (#36).
        status_keep = gr.update()
        # Gedrosselt wie in der Ask-All-Ansicht: nicht jedes Token einzeln über
        # den Socket schicken; last_flush=0.0 lässt den ersten Chunk sofort durch.
        reply = ""
        last_flush = 0.0
        stop = self._arm_stream_stop(session)
        stopped = False
        # Explizites Iterator-Handle, damit der Stream beim Stop deterministisch
        # geschlossen wird (close() löst das finally im Streaming-Provider aus und
        # beendet damit den Ollama-Stream) statt erst irgendwann per GC.
        tokens = session.streamer.stream(messages=message_history)
        try:
            for token in tokens:
                if self._stop_requested(session, stop):
                    stopped = True
                    break
                reply += token
                now = time.monotonic()
                if now - last_flush >= STREAM_FLUSH_INTERVAL_S:
                    last_flush = now
                    yield (
                        None,
                        chat_history + [bot_bubble(reply)],
                        message_history,
                        *keep,
                        status_keep,
                    )
        finally:
            close = getattr(tokens, "close", None)
            if close is not None:
                close()
            if session.stream_stop is stop:
                session.stream_stop = None

        if stopped:
            # Teilantwort behalten — sie ist der Grund, warum man abbricht.
            reply += self._t("web_stream_stopped_suffix")

        # Finalize: add the completed reply to the history
        chat_history.append(bot_bubble(reply))
        message_history.append({"role": "assistant", "content": reply})
        # Jetzt — und nur jetzt — steht der Gesprächsstand fest (#59). Auch beim
        # Abbruch: die Teilantwort ist das, was der Nutzer behält, also gehört
        # sie in die Ablage. Vorher zeichnete `stream()` Versuche auf, weshalb
        # „Nochmal" verdoppelte und „Stop" die Antwort ganz verlor.
        self.record_conversation(session, message_history)
        stats = self.last_stream_stats(session)
        yield (
            None,
            chat_history,
            message_history,
            *keep,
            self.status_update(session, message_history, stats),
        )

    # ---------- Der normale Turn ----------
    def respond_streaming(
        self,
        session: SessionContext,
        user_input: str,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:

        # Safety check: persona not selected yet → UI should prevent this, but we double-check
        if not session.bot:
            yield (
                "",
                chat_history,
                history_state,
                *self.wiki_sources_unchanged(),
                gr.update(),
            )
            return

        # 1) Maintain a dedicated LLM history without UI hints (and compress if needed)
        llm_history = list(history_state or [])

        # 2) Clear the input field and show the user message in the chat window
        #    Die Quellen der vorigen Antwort gehören nicht zur neuen Frage und
        #    verschwinden deshalb sofort (#32).
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append(user_bubble(user_input))
        yield "", chat_history, llm_history, *self.wiki_source_updates([]), gr.update()

        # 3) Wiki hint and snippet (top hit)
        wiki_hints, contexts = self.wiki.snippets(
            user_input, session.bot, getattr(session.streamer, "guard", None)
        )

        # Display the UI hints (do not add them to the LLM context window)
        for wiki_hint in wiki_hints:
            if wiki_hint:
                chat_history.append(bot_bubble(wiki_hint))
        if wiki_hints or contexts:
            yield (
                None,
                chat_history,
                llm_history,
                *self.wiki_source_updates(contexts),
                gr.update(),
            )

        # 4) Optional: inject wiki context
        if contexts:
            inject_wiki_context(
                llm_history, contexts, getattr(session.streamer, "guard", None)
            )

        # 4b) Optional: RSS-Meldungen, wenn die Frage danach ist (#73).
        #     Nichts wird hier geholt — der Cache ist schon gefüllt oder eben
        #     nicht; ein Turn wartet nie auf das Netz.
        rss_hint = self._inject_rss_if_asked(session, user_input, llm_history)
        if rss_hint:
            chat_history.append(bot_bubble(rss_hint))
            yield (
                None,
                chat_history,
                llm_history,
                *self.wiki_sources_unchanged(),
                gr.update(),
            )

        # 5) Send the user question to the LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Compress the context if needed and record that in chat history
        if self.handle_context_warning(session, llm_history, chat_history):
            yield (
                None,
                chat_history,
                llm_history,
                *self.wiki_sources_unchanged(),
                gr.update(),
            )

        # 7) Stream the answer
        yield from self.stream_reply(session, llm_history, chat_history)

    # ---------- RSS als Quelle (#73) ----------
    def _inject_rss_if_asked(
        self, session: SessionContext, user_input: str, llm_history: list[Message]
    ) -> str | None:
        """Hängt den Meldungs-Block an, wenn die Frage eine Nachrichtenfrage ist.

        Liefert den Hinweis für die Anzeige — oder ``None``, wenn nichts
        injiziert wurde. Der Hinweis ist Beiwerk und landet **nicht** in der
        LLM-History; genau daran erkennt der Vote-Kanal ihn (#40).
        """
        if not self.rss_enabled:
            return None
        names = feeds_for_question(user_input, self.rss_cache.feed_names)
        if not names:
            return None
        items = self.rss_cache.items_for(list(names))
        block, dropped = build_context_block(
            items, self.rss_cache, getattr(session.streamer, "guard", None)
        )
        if not block:
            return None
        inject_rss_context(llm_history, block)
        return self._rss_hint(session.bot, list(names), dropped)

    def _rss_hint(
        self, persona: str | None, names: list[str], dropped: int
    ) -> str | None:
        """„📰 LEAH hat dazu tagesschau gelesen (Stand 14:20)."

        Der Stand gehört sichtbar dazu: der Cache ist bis zu einer Stunde alt,
        und der Nutzer soll das wissen, ohne ins Log zu schauen.
        """
        if not names:
            return None
        stamp = self.rss_cache.filled_at
        hint = self._t(
            "rss_hint",
            persona_name=persona or "",
            feed_names=", ".join(names),
            stand=stamp.strftime("%H:%M") if stamp else "?",
        )
        if dropped:
            hint = f"{hint}\n{self._t('wiki_context_dropped', count=dropped)}"
        return hint

    # ---------- Senden ⇄ Stop (#35) ----------
    def streaming_button_updates(self, streaming: bool) -> tuple:
        """Send ⇄ Stop tauschen; Regenerate währenddessen sperren (#35)."""
        return (
            gr.update(visible=not streaming),
            gr.update(visible=streaming),
            gr.update(interactive=not streaming),
        )

    def with_controls(self, generator: Iterator[tuple]) -> Iterator[tuple]:
        """Hängt die Button-Updates an die Yields des Stream-Generators an.

        Bewusst im selben Yield statt als eigene `.then()`-Events davor und
        danach: der Umweg über ein zweites, gequeuetes Event kostete gemessen
        ~3,5 s bis zum ersten Token und hätte damit #17 zunichte gemacht.

        Der Schlusszustand wird als zusätzlicher Yield mit denselben Chat-/
        State-Werten geschickt — `gr.update()` ginge hier nicht, weil ein
        gr.State den Update-Marker als echten Wert übernehmen würde.
        """
        streaming = self.streaming_button_updates(streaming=True)
        unchanged = (gr.update(), gr.update(), gr.update())
        last: tuple | None = None
        first = True
        for item in generator:
            last = item
            yield (*item, *(streaming if first else unchanged))
            first = False
        if last is not None:
            yield (*last, *self.streaming_button_updates(streaming=False))

    def respond_streaming_with_controls(
        self,
        session: SessionContext,
        user_input: str,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self.with_controls(
            self.respond_streaming(session, user_input, chat_history, history_state)
        )

    def respond_briefing_with_controls(
        self,
        session: SessionContext,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self.with_controls(
            self.respond_briefing(session, chat_history, history_state)
        )

    def regenerate_with_controls(
        self,
        session: SessionContext,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self.with_controls(
            self.regenerate(session, chat_history, history_state)
        )

    def on_stop_stream(self, session: SessionContext) -> tuple:
        """Stoppt den laufenden Stream (#35).

        Eigenes Gradio-Event statt `cancels`: nur so läuft der Handler
        garantiert und der Generator kommt geordnet zum Ende — mit Teilantwort
        im Verlauf, statt sie wegzuwerfen.
        """
        stop = session.stream_stop
        if stop is not None:
            stop.set()
        return self.streaming_button_updates(streaming=False)

    # ---------- Nochmal (#35) ----------
    def regenerate(
        self,
        session: SessionContext,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        """Letzte Antwort verwerfen und mit identischem Kontext neu streamen.

        Varianz kommt allein aus der Temperatur der Persona — es wird nichts am
        Prompt gedreht. Die Quellen bleiben aus demselben Grund stehen: gleicher
        Kontext, gleiche Snippets (#32).
        """
        chat_history = list(chat_history or [])
        llm_history = list(history_state or [])
        keep = self.wiki_sources_unchanged()

        if not session.bot or not session.streamer:
            yield gr.update(), chat_history, llm_history, *keep, gr.update()
            return

        if not llm_history or llm_history[-1].get("role") != "assistant":
            gr.Warning(self._t("web_regenerate_nothing"))
            yield gr.update(), chat_history, llm_history, *keep, gr.update()
            return

        llm_history.pop()
        # In der Anzeige ist die Antwort die letzte Bot-Zeile; Wiki-/Briefing-Hints
        # sind ebenfalls Bot-Zeilen, stehen aber davor und bleiben stehen.
        if chat_history and chat_history[-1].get("role") == "assistant":
            chat_history.pop()
        yield gr.update(), chat_history, llm_history, *keep, gr.update()

        # gr.update() statt None: ein noch nicht abgeschickter Entwurf im
        # Eingabefeld soll durch das Neuerzeugen nicht verloren gehen.
        for _input_value, updated_chat, updated_state, *rest in self.stream_reply(
            session, llm_history, chat_history
        ):
            yield gr.update(), updated_chat, updated_state, *rest

    # ---------- Briefing (#73) ----------
    def respond_briefing(
        self,
        session: SessionContext,
        chat_history: list[ChatMessage],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        """Wie respond_streaming, nur mit RSS-Feeds statt Wiki als Kontext."""
        keep = self.wiki_sources_unchanged()
        if not session.bot or not self.briefing_enabled:
            yield gr.update(), chat_history, history_state, *keep, gr.update()
            return

        llm_history = list(history_state or [])
        briefing_prompt = self._t("briefing_user_prompt")
        chat_history.append(user_bubble(briefing_prompt))
        # Kein Wiki im Spiel — die Quellen der vorigen Antwort sind hier hinfällig.
        yield (
            gr.update(),
            chat_history,
            llm_history,
            *self.wiki_source_updates([]),
            gr.update(),
        )

        # Der Knopf holt nichts mehr selbst — er nimmt denselben Cache wie die
        # automatische Injektion (#73). Damit ist er eine Abkürzung, kein
        # zweiter Code-Pfad, und er wartet nie auf das Netz.
        items = self.rss_cache.items_for(self.rss_cache.feed_names)
        block, dropped = build_context_block(
            items, self.rss_cache, getattr(session.streamer, "guard", None)
        )
        hint = self._rss_hint(session.bot, self.rss_cache.feed_names, dropped)
        if hint:
            chat_history.append(bot_bubble(hint))
            yield None, chat_history, llm_history, *keep, gr.update()

        if not block:
            chat_history.append(bot_bubble(self._t("briefing_empty")))
            yield None, chat_history, llm_history, *keep, gr.update()
            return

        # Reihenfolge wie beim Wiki-Kontext: erst System-Messages, dann User-Turn
        inject_rss_context(llm_history, block)
        llm_history.append({"role": "user", "content": briefing_prompt})

        if self.handle_context_warning(session, llm_history, chat_history):
            yield None, chat_history, llm_history, *keep, gr.update()

        yield from self.stream_reply(session, llm_history, chat_history)
