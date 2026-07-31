from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gradio as gr
import requests
from auth import build_auth_provider
from briefing.feeds import fetch_briefing_items, inject_briefing_context
from config.personas import _load_system_prompts, get_all_persona_names, get_drink
from core.context_utils import (
    context_near_limit,
    shrink_history_for_context,
)
from core.orchestrator import iter_broadcast_events, iter_broadcast_events_parallel
from core.streaming_provider import StreamStats
from core.system_checks import fetch_model_names
from core.utils import (
    ensure_dir_exists,
    is_broadcast_enabled,
    is_broadcast_parallel,
    is_file_exchange_enabled,
    module_available,
)
from stt.whisper_stt import is_stt_available, transcribe_wav
from ui.continuation import GUEST_APP as _GUEST_APP
from ui.continuation import continuable_persona
from ui.conversation_io_terminal import load_conversation
from ui.self_talk import SelfTalkRunner
from ui.session import SessionContext
from ui.webui_format import (
    conversation_markdown,
    find_question_for_row,
    format_ask_all_results,
    format_status_line,
    format_wiki_sources,
    history_label,
    messages_to_chat_history,
)
from ui.webui_layout import (
    ASK_ALL_OUTPUT_KEYS,
    PERSONA_OUTPUT_KEYS,
    STREAM_CONTROL_KEYS,
    STREAM_OUTPUT_KEYS,
    as_persona_outputs,
    build_ui,
)
from wiki.lookup import (
    WikiLookup,
    WikiSnippet,
    inject_wiki_context,
)

if TYPE_CHECKING:
    from config.config_singleton import Config
    from core.factory import AppFactory

# One chatbot entry: (user_text, bot_text) — either side may be None.
ChatPair = tuple[str | None, str | None]
Message = dict[str, str]

# Wie oft gestreamte Updates höchstens an den Browser gehen (Sekunden). Ohne
# Drossel schickt Gradio ein Websocket-Frame pro Token. Der erste Chunk geht
# immer sofort durch (last_flush startet bei 0.0). Zweite Timing-Stellschraube
# neben security.stream_holdback_chars (#51).
STREAM_FLUSH_INTERVAL_S = 0.1

# Feedback votes (#40) are appended from Gradio event handlers that may run
# concurrently for multiple browser sessions sharing one WebUI instance.
_feedback_log_lock = threading.Lock()

# GUEST_APP und die Fortsetzbarkeits-Regel liegen in ui/continuation.py, weil
# sie das Terminal genauso braucht (es liest dieselben JSON-Dateien). Hier nur
# re-exportiert, damit bestehende Importe aus web_ui weiter funktionieren.
GUEST_APP = _GUEST_APP

# Hochgeladene Gespräche ebenfalls: sie sind fortsetzbar wie ein eigenes, aber
# im Verlauf soll erkennbar bleiben, dass sie von außen kamen.
IMPORT_APP = "web-import"

# Auslieferungsdateien (WAV, JSON, Markdown) liegen in einem eigenen
# Verzeichnis, das am Prozessende komplett verschwindet. Sie müssen den
# Response überleben, können also nicht sofort nach dem Schreiben weg.
_tmp_dir_lock = threading.Lock()
_tmp_dir: str | None = None


def _delivery_dir(register=atexit.register) -> str:
    """Verzeichnis der Auslieferungsdateien; wird beim Beenden abgeräumt.

    ``register`` ist injizierbar, damit der Test nicht `atexit.register` global
    ersetzen muss — sonst verschwindet still, was in diesem Fenster sonst noch
    registriert.
    """
    global _tmp_dir
    with _tmp_dir_lock:
        if _tmp_dir is None:
            _tmp_dir = tempfile.mkdtemp(prefix="yulyen-webui-")
            register(shutil.rmtree, _tmp_dir, True)
    return _tmp_dir


class WebUI:
    """
    Web chat interface built with Gradio.
    Provides a graphical persona selector (with avatar) and a live chat history in the browser.
    Wiki hints and snippets are handled like the terminal UI (hint only visible, snippet as context).
    Responses from the AI model are streamed token by token and updated directly in the UI.
    """

    def __init__(
        self,
        factory: AppFactory,
        config: Config,
        wiki: WikiLookup,
        web_host: str,
        web_port: int | str,
    ) -> None:
        self.cfg = config
        self.factory = factory
        self.wiki = wiki
        self.web_host = web_host
        self.web_port = int(web_port)
        self.texts = getattr(config, "texts", {}) or {}
        self._t = getattr(config, "t", getattr(self.texts, "format", None))
        # Wer bedient die UI (#53). Default DisabledAuth = Verhalten wie bisher.
        ui_cfg = getattr(config, "ui", {}) or {}
        self.auth = build_auth_provider(
            ui_cfg.get("web") if isinstance(ui_cfg, dict) else None
        )
        # Datei-Austausch (JSON rein/raus) ist abschaltbar (#54).
        self.file_exchange_enabled = is_file_exchange_enabled(self.cfg)
        self.broadcast_enabled = is_broadcast_enabled(self.cfg)
        self.broadcast_parallel = is_broadcast_parallel(self.cfg)
        # Persona, Streamer, Kill-Switches und der Self-Talk-Runner gehören
        # *nicht* hierher: die WebUI ist ein Singleton und bedient alle Browser
        # gleichzeitig. Sie liegen in einem SessionContext pro Sitzung
        # (`ui/session.py`) und werden als gr.State durchgereicht.
        self.ask_all_placeholder = ""
        self.self_talk_prompt_placeholder = ""
        # STT nur anbieten, wenn eingeschaltet UND faster-whisper installiert
        # ist — sonst bleibt das Mikro unsichtbar und die App läuft normal.
        self.stt_cfg = getattr(config, "stt", {}) or {}
        self.stt_available = bool(self.stt_cfg.get("enabled")) and is_stt_available()
        # Briefing (RSS): Button nur zeigen, wenn eingeschaltet und Feeds da sind
        self.briefing_cfg = getattr(config, "briefing", {}) or {}
        self.briefing_enabled = bool(self.briefing_cfg.get("enabled")) and bool(
            self.briefing_cfg.get("feeds")
        )
        # Vorlesen (TTS): wie beim Mikro nur anbieten, wenn Piper installiert ist
        self.tts_cfg = getattr(config, "tts", {}) or {}
        tts_features = self.tts_cfg.get("features", {}) or {}
        self.tts_web_enabled = (
            bool(self.tts_cfg.get("enabled"))
            and bool(tts_features.get("web_read_aloud"))
            and module_available("piper")
        )
        if (
            self.tts_cfg.get("enabled")
            and tts_features.get("web_read_aloud")
            and not self.tts_web_enabled
        ):
            logging.info(
                "TTS-Vorlesen aktiviert, aber piper ist nicht installiert — "
                "Button bleibt ausgeblendet (pip install piper-tts)."
            )
        if self.stt_cfg.get("enabled") and not self.stt_available:
            logging.info(
                "STT aktiviert, aber faster-whisper ist nicht installiert — "
                "Mikrofon bleibt ausgeblendet (pip install faster-whisper)."
            )
        # Lazily resolved on first vote; tests may pre-set an explicit path.
        self.feedback_log_path: str | None = None
        if self._t is None:
            self._t = lambda key, **kwargs: key

    def _reset_conversation_state(self) -> list[Message]:
        return []

    def _reset_meta_state(self) -> dict:
        return {}

    def _open_conversation(self, persona_name: str, user: str, app: str = "web") -> str:
        """Neues Gespräch anlegen (#54).

        Die ID gehört ab hier der Oberfläche: sie liegt im `gr.State` und wird
        nach einem Streamer-Neubau erneut gesetzt, statt dass ein zweites
        Gespräch entsteht.
        """
        return self.factory.open_conversation(
            persona_name, app, user or self._fallback_user()
        )

    @staticmethod
    def _delivery_file(session: SessionContext, kind: str, suffix: str) -> Path:
        """Pfad für eine Datei, die diese Sitzung gleich ausliefert.

        Die vorherige Datei derselben Art wird dabei gelöscht: löschte man
        sofort nach dem Schreiben, wäre sie weg, bevor der Browser sie abholt.
        Die Ablage hängt an der Sitzung, damit ein Download in einem Browser
        nicht die Datei eines anderen wegräumt.
        """
        previous = session.tmp_files.get(kind)
        if previous:
            try:
                os.unlink(previous)
            except OSError:
                logging.debug("Temporäre Datei %s war schon weg", previous)
        handle, path = tempfile.mkstemp(suffix=suffix, dir=_delivery_dir())
        os.close(handle)
        session.tmp_files[kind] = path
        return Path(path)

    def _stamp_conversation(
        self, session: SessionContext, conversation_id: str
    ) -> None:
        setter = getattr(session.streamer, "set_conversation", None)
        if callable(setter):
            setter(conversation_id)

    def _stamp_user(self, session: SessionContext, user: str) -> None:
        """Identität an den frischen Streamer geben (#53).

        Sie hängt dadurch am Gespräch in der Ablage — die Grundlage für den
        Verlauf (#25) und später die Suche (#49).
        """
        setter = getattr(session.streamer, "set_user", None)
        if callable(setter):
            setter(user or self._fallback_user())

    def _on_page_load(self, request: gr.Request) -> str:
        """Identität der Browser-Sitzung einmal beim Laden einsammeln (#53).

        Bewusst hier statt `gr.Request` an jedem Handler: die Persona-Buttons
        laufen über `functools.partial`, und ob Gradio dort die Signatur
        durchschaut, ist nichts, worauf man bauen sollte. Ein Wert im
        `gr.State` ist zudem sauber pro Browser-Sitzung.
        """
        identity = self.auth.identity_from_request(request)
        if not identity.is_known:
            logging.debug(
                "Sitzung ohne erkennbare Identität (provider=%s)", self.auth.name
            )
            return self._fallback_user()
        return identity.name

    def _fallback_user(self) -> str:
        """Nutzername, wenn die Session-Identität (noch) nicht vorliegt.

        Ohne Login ist das der lokale Standardnutzer; mit Login wäre ein leerer
        Wert eine Lüge, deshalb "unknown".
        """
        identity = self.auth.identity_from_request(None)
        return identity.name or "unknown"

    def _build_meta(self, persona_name: str, user: str = "", app: str = "web") -> dict:
        # `app` muss mitkommen: sonst trägt die heruntergeladene JSON eines
        # Gasts „web" statt GUEST_APP, und beim Hochladen wäre die Markierung
        # verloren, an der _continuable_persona den Gast erkennt.
        return {
            "created_at": datetime.now().isoformat(),
            "model": str(self.cfg.core.get("model_name")),
            "persona": persona_name,
            "app": app,
            # Nie leer: ohne Anmeldung der lokale Standardnutzer, sonst der
            # angemeldete Name — #25 und #24 sollen sich darauf verlassen können.
            "user": user or self._fallback_user(),
        }

    def _persona_thumbnail_path(self, persona_name: str) -> str:
        ensemble = getattr(self.cfg, "ensemble", None)
        if not ensemble:
            raise RuntimeError("No persona ensemble configured for the web UI.")
        return f"ensembles/{ensemble}/static/personas/{persona_name}/thumb.webp"

    def _persona_full_image_path(self, persona_name: str) -> str:
        ensemble = getattr(self.cfg, "ensemble", None)
        if not ensemble:
            raise RuntimeError("No persona ensemble configured for the web UI.")
        return f"ensembles/{ensemble}/static/personas/{persona_name}/full.webp"

    def _handle_context_warning(
        self,
        session: SessionContext,
        llm_history: list[Message],
        chat_history: list[ChatPair],
    ) -> bool:

        if not context_near_limit(llm_history, session.streamer.persona_options):
            return False

        drink = get_drink(session.bot)
        warn = self._t("context_wait_message", persona_name=session.bot, drink=drink)

        chat_history.append((None, warn))

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
    def _last_stream_stats(session: SessionContext) -> StreamStats | None:
        """Kennzahlen des Providers — nur, wenn es wirklich welche sind.

        Vor dem ersten Stream ist das Attribut None; Testdoubles setzen es gar
        nicht. Die isinstance-Prüfung hält halbe Werte aus der Anzeige heraus,
        statt sie zu formatieren.
        """
        stats = getattr(session.streamer, "last_stream_stats", None)
        return stats if isinstance(stats, StreamStats) else None

    def _status_update(
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
    def _wiki_source_updates(self, snippets: list[WikiSnippet] | None) -> tuple:
        """Accordion + Markdown; ohne Treffer bleibt das Accordion unsichtbar."""
        markdown = format_wiki_sources(snippets, self._t)
        return gr.update(visible=bool(markdown)), gr.update(value=markdown)

    @staticmethod
    def _wiki_sources_unchanged() -> tuple:
        return gr.update(), gr.update()

    # Stream the response (UI updates continuously)
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

    def _stream_reply(
        self,
        session: SessionContext,
        message_history: list[Message],
        chat_history: list[ChatPair],
    ) -> Iterator[tuple]:
        # Die Quellen-Slots stehen vor dem Stream schon fest und bleiben hier
        # unangetastet — gr.update() ohne Wert ist ein No-op für die Anzeige.
        keep = self._wiki_sources_unchanged()
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
                        chat_history + [(None, reply)],
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
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        stats = self._last_stream_stats(session)
        yield (
            None,
            chat_history,
            message_history,
            *keep,
            self._status_update(session, message_history, stats),
        )

    def respond_streaming(
        self,
        session: SessionContext,
        user_input: str,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:

        # Safety check: persona not selected yet → UI should prevent this, but we double-check
        if not session.bot:
            yield (
                "",
                chat_history,
                history_state,
                *self._wiki_sources_unchanged(),
                gr.update(),
            )
            return

        # 1) Maintain a dedicated LLM history without UI hints (and compress if needed)
        llm_history = list(history_state or [])

        # 2) Clear the input field and show the user message in the chat window
        #    Die Quellen der vorigen Antwort gehören nicht zur neuen Frage und
        #    verschwinden deshalb sofort (#32).
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append((user_input, None))
        yield "", chat_history, llm_history, *self._wiki_source_updates([]), gr.update()

        # 3) Wiki hint and snippet (top hit)
        wiki_hints, contexts = self.wiki.snippets(user_input, session.bot)

        # Display the UI hints (do not add them to the LLM context window)
        for wiki_hint in wiki_hints:
            if wiki_hint:
                chat_history.append((None, wiki_hint))
        if wiki_hints or contexts:
            yield (
                None,
                chat_history,
                llm_history,
                *self._wiki_source_updates(contexts),
                gr.update(),
            )

        # 4) Optional: inject wiki context
        if contexts:
            inject_wiki_context(
                llm_history, contexts, getattr(session.streamer, "guard", None)
            )

        # 5) Send the user question to the LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Compress the context if needed and record that in chat history
        if self._handle_context_warning(session, llm_history, chat_history):
            yield (
                None,
                chat_history,
                llm_history,
                *self._wiki_sources_unchanged(),
                gr.update(),
            )

        # 7) Stream the answer
        yield from self._stream_reply(session, llm_history, chat_history)

    def _streaming_button_updates(self, streaming: bool) -> tuple:
        """Send ⇄ Stop tauschen; Regenerate währenddessen sperren (#35)."""
        return (
            gr.update(visible=not streaming),
            gr.update(visible=streaming),
            gr.update(interactive=not streaming),
        )

    def _with_stream_controls(self, generator: Iterator[tuple]) -> Iterator[tuple]:
        """Hängt die Button-Updates an die Yields des Stream-Generators an.

        Bewusst im selben Yield statt als eigene `.then()`-Events davor und
        danach: der Umweg über ein zweites, gequeuetes Event kostete gemessen
        ~3,5 s bis zum ersten Token und hätte damit #17 zunichte gemacht.

        Der Schlusszustand wird als zusätzlicher Yield mit denselben Chat-/
        State-Werten geschickt — `gr.update()` ginge hier nicht, weil ein
        gr.State den Update-Marker als echten Wert übernehmen würde.
        """
        streaming = self._streaming_button_updates(streaming=True)
        unchanged = (gr.update(), gr.update(), gr.update())
        last: tuple | None = None
        first = True
        for item in generator:
            last = item
            yield (*item, *(streaming if first else unchanged))
            first = False
        if last is not None:
            yield (*last, *self._streaming_button_updates(streaming=False))

    def respond_streaming_with_controls(
        self,
        session: SessionContext,
        user_input: str,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self.respond_streaming(session, user_input, chat_history, history_state)
        )

    def respond_briefing_with_controls(
        self,
        session: SessionContext,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self.respond_briefing(session, chat_history, history_state)
        )

    def regenerate_with_controls(
        self,
        session: SessionContext,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self._on_regenerate(session, chat_history, history_state)
        )

    def _on_stop_stream(self, session: SessionContext) -> tuple:
        """Stoppt den laufenden Stream (#35).

        Eigenes Gradio-Event statt `cancels`: nur so läuft der Handler
        garantiert und der Generator kommt geordnet zum Ende — mit Teilantwort
        im Verlauf, statt sie wegzuwerfen.
        """
        stop = session.stream_stop
        if stop is not None:
            stop.set()
        return self._streaming_button_updates(streaming=False)

    def _on_regenerate(
        self,
        session: SessionContext,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        """Letzte Antwort verwerfen und mit identischem Kontext neu streamen.

        Varianz kommt allein aus der Temperatur der Persona — es wird nichts am
        Prompt gedreht. Die Quellen bleiben aus demselben Grund stehen: gleicher
        Kontext, gleiche Snippets (#32).
        """
        chat_history = list(chat_history or [])
        llm_history = list(history_state or [])
        keep = self._wiki_sources_unchanged()

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
        if chat_history and chat_history[-1][0] is None:
            chat_history.pop()
        yield gr.update(), chat_history, llm_history, *keep, gr.update()

        # gr.update() statt None: ein noch nicht abgeschickter Entwurf im
        # Eingabefeld soll durch das Neuerzeugen nicht verloren gehen.
        for _input_value, updated_chat, updated_state, *rest in self._stream_reply(
            session, llm_history, chat_history
        ):
            yield gr.update(), updated_chat, updated_state, *rest

    def respond_briefing(
        self,
        session: SessionContext,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        """Wie respond_streaming, nur mit RSS-Feeds statt Wiki als Kontext."""
        keep = self._wiki_sources_unchanged()
        if not session.bot or not self.briefing_enabled:
            yield gr.update(), chat_history, history_state, *keep, gr.update()
            return

        llm_history = list(history_state or [])
        briefing_prompt = self._t("briefing_user_prompt")
        chat_history.append((briefing_prompt, None))
        # Kein Wiki im Spiel — die Quellen der vorigen Antwort sind hier hinfällig.
        yield (
            gr.update(),
            chat_history,
            llm_history,
            *self._wiki_source_updates([]),
            gr.update(),
        )

        timeout = (
            float(self.briefing_cfg.get("timeout_connect", 5.0)),
            float(self.briefing_cfg.get("timeout_read", 8.0)),
        )
        hints, items = fetch_briefing_items(self.briefing_cfg, session.bot, timeout)

        for hint in hints:
            if hint:
                chat_history.append((None, hint))
        if hints:
            yield None, chat_history, llm_history, *keep, gr.update()

        if not items:
            chat_history.append((None, self._t("briefing_empty")))
            yield None, chat_history, llm_history, *keep, gr.update()
            return

        # Reihenfolge wie beim Wiki-Kontext: erst System-Messages, dann User-Turn
        inject_briefing_context(
            llm_history, items, getattr(session.streamer, "guard", None)
        )
        llm_history.append({"role": "user", "content": briefing_prompt})

        if self._handle_context_warning(session, llm_history, chat_history):
            yield None, chat_history, llm_history, *keep, gr.update()

        yield from self._stream_reply(session, llm_history, chat_history)

    def _reset_updates(self) -> dict:
        """Baseline 'back to start screen' state; handlers override what differs."""
        return {
            "selected_persona_state": gr.update(value=""),
            "grid_group": gr.update(visible=True),
            "focus_group": gr.update(visible=False),
            "focus_img": gr.update(value=None, visible=True),
            "focus_md": gr.update(value=""),
            "greeting_md": gr.update(value="", visible=False),
            "chatbot": gr.update(value=[], label="", visible=False),
            "input_box": gr.update(value="", visible=False, interactive=False),
            "send_btn": gr.update(visible=False, interactive=False),
            "new_chat_btn": gr.update(visible=False),
            "download_btn": gr.update(visible=False),
            "download_file": gr.update(value=None, visible=False),
            "save_status": gr.update(value="", visible=False),
            "history_state": self._reset_conversation_state(),
            "meta_state": self._reset_meta_state(),
            "ask_all_group": gr.update(visible=False),
            "ask_all_results": gr.update(value="", visible=False),
            "ask_all_question": gr.update(
                value=self.ask_all_placeholder, visible=False, interactive=True
            ),
            "ask_all_submit": gr.update(visible=False, interactive=True),
            "ask_all_new_chat": gr.update(visible=False),
            "ask_all_status": gr.update(value="", visible=False),
            "load_status": gr.update(value="", visible=False),
            "self_talk_group": gr.update(visible=False),
            "self_talk_status": gr.update(value="", visible=False),
            "self_talk_persona_a": gr.update(value=None, interactive=True),
            "self_talk_persona_b": gr.update(value=None, interactive=True),
            "self_talk_prompt": gr.update(
                value="",
                visible=False,
                interactive=True,
                placeholder=self.self_talk_prompt_placeholder,
            ),
            "self_talk_start_btn": gr.update(visible=False, interactive=True),
            "mic_audio": gr.update(value=None, visible=False),
            "briefing_btn": gr.update(visible=False),
            "read_aloud_btn": gr.update(visible=False),
            "tts_audio": gr.update(value=None, visible=False),
            "stop_btn": gr.update(visible=False),
            "regenerate_btn": gr.update(visible=False, interactive=True),
            "sources_accordion": gr.update(visible=False, open=False),
            "sources_md": gr.update(value=""),
            "ask_all_sources_accordion": gr.update(visible=False, open=False),
            "ask_all_sources_md": gr.update(value=""),
            "status_md": gr.update(value="", visible=False),
            "guest_group": gr.update(visible=False),
            "guest_status": gr.update(value="", visible=False),
            "conversation_state": "",
            "history_group": gr.update(visible=False),
            "history_status": gr.update(value="", visible=False),
            "history_pick": gr.update(choices=[], value=None),
            "history_preview": gr.update(value=""),
            # Muss zurück: ein gesetztes Häkchen überlebte sonst den Weg zur
            # Startseite und der nächste Klick löschte ohne neue Bestätigung.
            "history_confirm": gr.update(value=False),
        }

    def _persona_selected_updates(
        self,
        persona_key: str,
        persona: dict[str, Any],
        greeting_template: str,
        input_placeholder: str,
        user: str = "",
        conversation_id: str = "",
        image_path: str | None = "",
        app: str = "web",
    ) -> tuple:
        display_name = persona["name"].title()
        # Modell live aus der Config lesen (kann per Profi-Option gewechselt sein)
        model_name = str(self.cfg.core.get("model_name", ""))
        greeting = greeting_template.format(
            persona_name=display_name, model_name=model_name
        )
        focus_text = f"### {persona['name']}\n{persona['description']}"

        updates = self._reset_updates()
        updates.update(
            selected_persona_state=gr.update(value=persona_key),
            grid_group=gr.update(visible=False),
            focus_group=gr.update(visible=True),
            # Gast-Personas haben kein Portrait: Komponente ausblenden statt
            # einen leeren Bildrahmen zu zeigen (#28).
            focus_img=(
                gr.update(
                    value=self._persona_full_image_path(persona["name"]), visible=True
                )
                if image_path == ""
                else gr.update(value=None, visible=False)
            ),
            focus_md=gr.update(value=focus_text),
            greeting_md=gr.update(value=greeting, visible=True),
            chatbot=gr.update(value=[], label=display_name, visible=True),
            input_box=gr.update(
                value="", visible=True, interactive=True, placeholder=input_placeholder
            ),
            send_btn=gr.update(visible=True, interactive=True),
            new_chat_btn=gr.update(visible=True),
            download_btn=gr.update(visible=self.file_exchange_enabled),
            briefing_btn=gr.update(visible=self.briefing_enabled),
            read_aloud_btn=gr.update(visible=self.tts_web_enabled),
            meta_state=self._build_meta(persona["name"], user=user, app=app),
            conversation_state=conversation_id,
            ask_all_question=gr.update(
                value="",
                visible=False,
                interactive=True,
                placeholder=self.ask_all_placeholder,
            ),
            mic_audio=gr.update(value=None, visible=self.stt_available),
            # Regenerate ist ab Start sichtbar, aber erst nach einer Antwort
            # sinnvoll; ein Klick davor bringt nur einen Hinweis-Toast. Stop
            # erscheint ausschließlich während eines laufenden Streams.
            regenerate_btn=gr.update(visible=True, interactive=True),
            stop_btn=gr.update(visible=False),
        )
        return as_persona_outputs(updates)

    def _reset_ui_updates(self) -> tuple:
        return as_persona_outputs(self._reset_updates())

    def _on_persona_selected(
        self,
        session: SessionContext,
        user: str,
        *,
        key: str = "",
        persona_info: dict[str, dict[str, Any]] | None = None,
        greeting_template: str = "",
        input_placeholder: str = "",
    ) -> tuple:
        persona = (persona_info or {}).get(key)
        if not persona:
            session.clear_persona()
            return self._reset_ui_updates()

        session.bot = persona["name"]
        session.streamer = self.factory.get_streamer_for_persona(session.bot)
        self._stamp_user(session, user)
        conversation_id = self._open_conversation(session.bot, user)
        self._stamp_conversation(session, conversation_id)
        return self._persona_selected_updates(
            key,
            persona,
            greeting_template,
            input_placeholder,
            user=user,
            conversation_id=conversation_id,
        )

    @staticmethod
    def _cancel_ask_all_broadcast(session: SessionContext) -> None:
        """Stops the workers of a running ask-all broadcast (if any)."""
        stop = session.ask_all_stop
        if stop is not None:
            stop.set()
            session.ask_all_stop = None

    def _on_reset_to_start(self, session: SessionContext) -> tuple:
        self._cancel_ask_all_broadcast(session)
        # Zusätzlich zum `cancels` am Reset-Button: das cancels bricht nur den
        # asyncio-Task ab, der Kill-Switch beendet die Arbeit im Backend (#35).
        stop = session.stream_stop
        if stop is not None:
            stop.set()
        session.clear_persona()
        return self._reset_ui_updates()

    def _available_models(self, default_model: str) -> list[str]:
        """Installierte Ollama-Modelle für das Profi-Dropdown; Fallback: Default."""
        backend = str(self.cfg.core.get("backend", "ollama")).strip().lower()
        if backend != "ollama":
            return [default_model]
        try:
            names = fetch_model_names(self.cfg.core.get("ollama_url", ""), timeout=2.0)
        except (requests.RequestException, ValueError) as exc:
            logging.warning(
                "Modellliste nicht abrufbar (%s) — Dropdown zeigt nur den Standard.",
                exc,
            )
            return [default_model]
        choices = [n for n in names if n]
        if default_model and default_model not in choices:
            choices.insert(0, default_model)
        return choices or [default_model]

    def _on_model_selected(
        self, session: SessionContext, choice: str | None, conversation_id: str
    ):
        """Session-Override des Modells; config.yaml bleibt unangetastet."""
        choice = (choice or "").strip()
        if not choice:
            return gr.update(value="", visible=False)
        self.cfg.override("core", {"model_name": choice})
        if session.bot:
            # Laufendes Gespräch: Streamer neu bauen (History lebt im gr.State),
            # damit auch die Cutoff-Zeile im System-Prompt zum Modell passt.
            session.streamer = self.factory.get_streamer_for_persona(session.bot)
            # Der neue Streamer schreibt in dasselbe Gespräch weiter (#54).
            # Über die UI ist dieser Fall derzeit nicht auslösbar — das
            # Modell-Dropdown sitzt im „Erweitert"-Akkordeon der Startseite und
            # ist während eines Chats nicht sichtbar. Die Verdrahtung steht
            # trotzdem, damit sie nicht fehlt, sobald es das ist.
            self._stamp_conversation(session, conversation_id)
            self._stamp_user(session, "")
        logging.info("Modell per UI gewechselt: %s", choice)
        return gr.update(
            value=self._t("web_model_switched", model_name=choice), visible=True
        )

    def _on_mic_recorded(self, audio_path: str | None, current_text: str | None):
        """Transkribiert die Aufnahme und hängt den Text ans Eingabefeld an."""
        if not audio_path:
            # feuert z. B. auch beim Leeren der Komponente
            return gr.update(), gr.update()
        try:
            transcript = transcribe_wav(audio_path, stt_cfg=self.stt_cfg)
        except Exception as exc:
            logging.warning("STT: Transkription fehlgeschlagen: %s", exc)
            gr.Warning(self._t("stt_error", reason=str(exc)))
            return gr.update(), gr.update(value=None)
        if not transcript:
            return gr.update(), gr.update(value=None)
        combined = f"{current_text or ''} {transcript}".strip()
        return gr.update(value=combined), gr.update(value=None)

    def _on_read_aloud(
        self, session: SessionContext, history_state: list[Message] | None
    ):
        """Liest die letzte Antwort mit der Piper-Stimme der Persona vor."""
        last_reply = next(
            (
                m.get("content", "")
                for m in reversed(history_state or [])
                if m.get("role") == "assistant"
            ),
            "",
        )
        if not session.bot or not last_reply.strip():
            gr.Warning(self._t("tts_no_reply"))
            return gr.update(value=None, visible=False)
        try:
            # Lazy wie im Terminal: piper_tts importiert piper auf Modulebene
            from tts.piper_tts import create_wav

            out_wav = self._delivery_file(session, "tts", ".wav")
            create_wav(
                last_reply,
                session.bot,
                voices_dir=Path("voices"),
                out_wav=out_wav,
                tts_cfg=self.tts_cfg,
                language=getattr(self.cfg, "language", "de"),
            )
        except Exception as exc:
            logging.warning("TTS: Vorlesen fehlgeschlagen: %s", exc)
            gr.Warning(self._t("tts_error", reason=str(exc)))
            return gr.update(value=None, visible=False)
        return gr.update(value=str(out_wav), visible=True)

    def _on_show_ask_all(self, session: SessionContext) -> tuple:
        session.clear_persona()
        updates = self._reset_updates()
        updates.update(
            grid_group=gr.update(visible=False),
            ask_all_group=gr.update(visible=True),
            ask_all_question=gr.update(
                value="",
                visible=True,
                interactive=True,
                placeholder=self.ask_all_placeholder,
            ),
            ask_all_submit=gr.update(visible=True, interactive=True),
            ask_all_new_chat=gr.update(visible=True),
        )
        return as_persona_outputs(updates)

    # ---------- Verlauf (#25) ----------
    def _history_choices(self, user: str) -> list[tuple[str, str]]:
        """Gespräche des angemeldeten Nutzers — Beschriftung und ID.

        Die Filterung nach Nutzer ist der Grund, warum #53 vor diesem Ticket
        kam: ohne sie zeigt eine Verlaufsliste jedem alles.
        """
        storage_cfg = getattr(self.cfg, "storage", None) or {}
        try:
            limit = max(1, int(storage_cfg.get("history_limit", 50)))
        except (TypeError, ValueError):
            limit = 50
        try:
            refs = self.factory.get_store().list_conversations(
                user=user or self._fallback_user(), limit=limit
            )
        except Exception:
            logging.exception("Verlauf konnte nicht gelesen werden")
            return []
        return [(history_label(ref), ref.id) for ref in refs]

    def _on_show_history(self, session: SessionContext, user: str) -> tuple:
        session.clear_persona()
        choices = self._history_choices(user)
        updates = self._reset_updates()
        updates.update(
            grid_group=gr.update(visible=False),
            new_chat_btn=gr.update(visible=True),
            history_group=gr.update(visible=True),
            history_pick=gr.update(choices=choices, value=None),
            history_status=gr.update(
                value=self._t("history_empty"), visible=not choices
            ),
        )
        return as_persona_outputs(updates)

    def _on_history_selected(self, conversation_id: str | None, user: str) -> Any:
        """Vorschau des gewählten Gesprächs."""
        loaded = self._load_from_store(conversation_id, user)
        if loaded is None:
            return gr.update(value="")
        ref, messages = loaded
        return gr.update(value=conversation_markdown(ref, messages, self._t))

    def _load_from_store(self, conversation_id: str | None, user: str):
        """Gespräch aus der Ablage — **nur** das des angemeldeten Nutzers.

        Die Liste in ``_history_choices`` filtert nach Nutzer, die Handler
        dahinter taten es nicht: die Gesprächs-ID kommt aus einem
        ``gr.Dropdown``, und dessen ``preprocess`` reicht in Gradio 4.44 den
        Wert des Clients ungeprüft durch (``type="value"`` → ``return payload``).
        Wer eine fremde ID kannte, konnte das Gespräch lesen, exportieren,
        fortsetzen und löschen — nachgestellt mit zwei angemeldeten Nutzern.

        Deshalb liegt die Prüfung jetzt an der Stelle, an der alle vier
        Handler zwangsläufig vorbeikommen, statt viermal beim Aufrufer.
        """
        if not conversation_id:
            return None
        try:
            return self.factory.get_store().load(
                str(conversation_id), user=user or self._fallback_user()
            )
        except Exception:
            logging.exception("Gespräch %s nicht ladbar", conversation_id)
            return None

    # Die Regel selbst steht in ui/continuation.py — sie gilt für alle drei
    # Wege in ein gespeichertes Gespräch, auch für den im Terminal.
    _continuable_persona = staticmethod(continuable_persona)

    def _on_history_open(
        self,
        session: SessionContext,
        conversation_id: str | None,
        user: str,
        persona_info: dict[str, dict[str, Any]] | None = None,
        input_placeholder: str = "",
    ) -> tuple:
        """Gespräch in den Chat holen — fortsetzbar, nicht nur ansehbar."""
        loaded = self._load_from_store(conversation_id, user)
        if loaded is None:
            updates = self._reset_updates()
            updates.update(
                grid_group=gr.update(visible=False),
                new_chat_btn=gr.update(visible=True),
                history_group=gr.update(visible=True),
                history_status=gr.update(
                    value=self._t("history_not_found"), visible=True
                ),
            )
            return as_persona_outputs(updates)

        ref, messages = loaded
        persona = self._continuable_persona(ref.persona, ref.app, persona_info)
        if not persona:
            # Gast-Personas leben nur in ihrer Sitzung; ihr Verlauf bleibt
            # lesbar, fortsetzen lässt er sich ohne den Prompt aber nicht.
            updates = self._reset_updates()
            updates.update(
                grid_group=gr.update(visible=False),
                new_chat_btn=gr.update(visible=True),
                history_group=gr.update(visible=True),
                history_preview=gr.update(
                    value=conversation_markdown(ref, messages, self._t)
                ),
                history_status=gr.update(
                    value=self._t("history_persona_gone", persona=ref.persona),
                    visible=True,
                ),
            )
            return as_persona_outputs(updates)

        session.bot = persona["name"]
        session.streamer = self.factory.get_streamer_for_persona(session.bot)
        self._stamp_user(session, ref.user)
        self._stamp_conversation(session, ref.id)

        meta = {
            "created_at": ref.created_at,
            "model": ref.model,
            "persona": ref.persona,
            "app": ref.app,
            "user": ref.user,
        }
        updates = self._conversation_loaded_updates(
            ref.persona.lower(), persona, meta, messages, input_placeholder
        )
        # _conversation_loaded_updates kennt die Ablage nicht — die ID muss
        # gesetzt werden, sonst schreibt das fortgesetzte Gespräch ins Leere.
        as_dict = dict(zip(PERSONA_OUTPUT_KEYS, updates, strict=True))
        as_dict["conversation_state"] = ref.id
        return as_persona_outputs(as_dict)

    def _on_history_export(
        self, session: SessionContext, conversation_id: str | None, user: str
    ) -> Any:
        loaded = self._load_from_store(conversation_id, user)
        if loaded is None:
            return gr.update(value=None, visible=False)
        ref, messages = loaded
        path = self._delivery_file(session, "export", ".md")
        path.write_text(conversation_markdown(ref, messages, self._t), encoding="utf-8")
        return gr.update(value=str(path), visible=True)

    def _on_history_delete(
        self, conversation_id: str | None, confirmed: bool, user: str
    ) -> tuple:
        """Löschen ist endgültig — deshalb nur mit gesetztem Häkchen."""
        if not confirmed:
            return (
                gr.update(),
                gr.update(),
                gr.update(value=self._t("history_confirm_first"), visible=True),
                gr.update(),
                gr.update(),
            )

        deleted = False
        if conversation_id:
            try:
                # Nur eigene Gespräche: das Löschen ist der einzige der vier
                # Verlauf-Wege, der sich nicht rückgängig machen lässt.
                deleted = self.factory.get_store().delete(
                    str(conversation_id), user=user or self._fallback_user()
                )
            except Exception:
                logging.exception("Gespräch %s nicht löschbar", conversation_id)
        choices = self._history_choices(user)
        message = "history_deleted" if deleted else "history_not_found"
        return (
            gr.update(choices=choices, value=None),
            gr.update(value=""),
            gr.update(value=self._t(message), visible=True),
            gr.update(value=None, visible=False),
            # Häkchen zurücksetzen, damit der nächste Klick nicht durchrutscht.
            gr.update(value=False),
        )

    def _on_show_guest(self, session: SessionContext) -> tuple:
        """Formular für eine Gast-Persona zeigen (#28)."""
        session.clear_persona()
        updates = self._reset_updates()
        updates.update(
            grid_group=gr.update(visible=False),
            # Rückweg zur Startseite, solange noch kein Gast läuft
            new_chat_btn=gr.update(visible=True),
            guest_group=gr.update(visible=True),
        )
        return as_persona_outputs(updates)

    def _on_start_guest(
        self,
        session: SessionContext,
        name: str | None,
        prompt: str | None,
        temperature: float | None,
        user: str,
        *,
        greeting_template: str = "",
        input_placeholder: str = "",
    ) -> tuple:
        """Gast-Persona anlegen — nur im Sitzungsspeicher, kein YAML.

        Bewusst ohne Persistenz: ein Schreiben nach `ensembles/` müsste die
        Singleton-Kette Config → personas.py → Factory-Cache neu laden. Das ist
        eine eigene Ausbaustufe, kein Beiwerk.
        """
        name = (name or "").strip()
        prompt = (prompt or "").strip()

        if not name or not prompt:
            updates = self._reset_updates()
            updates.update(
                grid_group=gr.update(visible=False),
                new_chat_btn=gr.update(visible=True),
                guest_group=gr.update(visible=True),
                guest_status=gr.update(
                    value=self._t("guest_missing_fields"), visible=True
                ),
            )
            return as_persona_outputs(updates)

        options = {
            "temperature": float(temperature if temperature is not None else 0.7)
        }
        session.bot = name
        session.streamer = self.factory.get_streamer_for_guest(name, prompt, options)
        self._stamp_user(session, user)
        conversation_id = self._open_conversation(name, user, app=GUEST_APP)
        self._stamp_conversation(session, conversation_id)
        logging.info("Gast-Persona '%s' gestartet (nur Sitzung)", name)

        persona = {"name": name, "description": self._t("guest_description")}
        updates = self._persona_selected_updates(
            name.lower(),
            persona,
            greeting_template,
            input_placeholder,
            user=user,
            conversation_id=conversation_id,
            # Der Gast hat kein Bild — lieber leer als ein toter Pfad.
            image_path=None,
            # Markierung bis in die heruntergeladene JSON durchreichen.
            app=GUEST_APP,
        )
        return updates

    def _on_show_self_talk(self, session: SessionContext) -> tuple:
        session.clear_persona()
        session.self_talk_runner = None
        updates = self._reset_updates()
        updates.update(
            grid_group=gr.update(visible=False),
            # Rückweg zur Startseite, solange noch kein Dialog läuft
            new_chat_btn=gr.update(visible=True),
            self_talk_group=gr.update(visible=True),
            self_talk_prompt=gr.update(
                value="",
                visible=True,
                interactive=True,
                placeholder=self.self_talk_prompt_placeholder,
            ),
            self_talk_start_btn=gr.update(visible=True, interactive=True),
        )
        return as_persona_outputs(updates)

    def _on_start_self_talk(
        self,
        session: SessionContext,
        persona_a: str | None,
        persona_b: str | None,
        start_prompt: str | None,
    ) -> tuple:
        persona_a = (persona_a or "").strip()
        persona_b = (persona_b or "").strip()
        start_prompt = (start_prompt or "").strip()
        session.self_talk_runner = None

        if not persona_a or not persona_b:
            msg = self._t("self_talk_persona_required")
            return (
                gr.update(value=msg, visible=True),
                gr.update(value=[], visible=False),
                [],
                gr.update(value="", visible=False, interactive=False),
                gr.update(visible=False, interactive=False),
                gr.update(visible=False),
                gr.update(value=None),
                gr.update(value="", visible=False),
            )

        if persona_a == persona_b:
            msg = self._t("self_talk_persona_distinct_required")
            return (
                gr.update(value=msg, visible=True),
                gr.update(value=[], visible=False),
                [],
                gr.update(value="", visible=False, interactive=False),
                gr.update(visible=False, interactive=False),
                gr.update(visible=False),
                gr.update(value=None),
                gr.update(value="", visible=False),
            )

        if not start_prompt:
            msg = self._t("terminal_self_talk_initial_prompt_required")
            return (
                gr.update(value=msg, visible=True),
                gr.update(value=[], visible=False),
                [],
                gr.update(value="", visible=False, interactive=False),
                gr.update(visible=False, interactive=False),
                gr.update(visible=False),
                gr.update(value=None),
                gr.update(value="", visible=False),
            )

        session.self_talk_runner = SelfTalkRunner(
            self.factory,
            self.texts,
            persona_a,
            persona_b,
            start_prompt,
        )
        title = self._t(
            "self_talk_chat_label", persona_a=persona_a, persona_b=persona_b
        )
        chat_history = [(start_prompt, None)]
        history_state = [{"role": "user", "content": start_prompt}]
        meta = self._build_meta(f"self-talk:{persona_a},{persona_b}")
        return (
            gr.update(value="", visible=False),
            gr.update(value=chat_history, label=title, visible=True),
            history_state,
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False, interactive=False),
            gr.update(visible=True),
            meta,
            gr.update(value="", visible=False),
        )

    def _run_self_talk_stream(
        self,
        session: SessionContext,
        chat_history: list[ChatPair],
        history_state: list[Message],
    ) -> Iterator[tuple[list[ChatPair], list[Message]]]:
        runner = session.self_talk_runner
        if runner is None:
            return

        chat_history = list(chat_history or [])
        history_state = list(history_state or [])
        # Stop wirkt hier zwischen den Turns, nicht mitten drin: run_turn() holt
        # die Antwort in einem Zug ab, es gibt keinen Token-Strom zum Abbrechen.
        stop = self._arm_stream_stop(session)
        try:
            while True:
                if self._stop_requested(session, stop):
                    break
                persona_name, reply, should_stop, _ = runner.run_turn()
                shown_reply = f"{persona_name}: {reply}"
                # run_turn() liefert die Antwort bereits komplett; die
                # Zeichen-Schleife war reine Schreibmaschinen-Animation (ein
                # Websocket-Frame pro Zeichen). Mit der 0.1-s-Drossel erscheint
                # die Nachricht in wenigen großen Updates statt in len(reply).
                progressive = ""
                last_flush = 0.0
                for token in shown_reply:
                    progressive += token
                    now = time.monotonic()
                    if now - last_flush >= STREAM_FLUSH_INTERVAL_S:
                        last_flush = now
                        yield chat_history + [(None, progressive)], history_state
                chat_history.append((None, shown_reply))
                history_state.append({"role": "assistant", "content": shown_reply})
                yield chat_history, history_state
                if should_stop:
                    break
        finally:
            if session.stream_stop is stop:
                session.stream_stop = None

    def _ask_all_state(
        self,
        question: str,
        results_md: str,
        *,
        editable: bool,
        submit_visible: bool = True,
        submit_interactive: bool = True,
        status: str = "",
        sources_md: str = "",
    ) -> tuple:
        """Builds the tuple of updates every Ask-All yield consists of.

        ``sources_md`` läuft wie ``status`` durch alle Yields mit: der
        Wiki-Lookup passiert einmal vorab, das Ergebnis muss danach in jedem
        Update wieder mitgeschickt werden (#32a).
        """
        return (
            gr.update(
                value=question,
                visible=True,
                interactive=editable,
                placeholder=self.ask_all_placeholder,
            ),
            gr.update(value=status, visible=bool(status)),
            gr.update(value=results_md, visible=bool(results_md)),
            gr.update(visible=submit_visible, interactive=submit_interactive),
            gr.update(visible=True),
            gr.update(visible=bool(sources_md)),
            gr.update(value=sources_md),
        )

    def _on_submit_ask_all(
        self,
        session: SessionContext,
        question: str | None,
        current_results: str | None = None,
    ) -> Iterator[tuple]:
        question = (question or "").strip()
        existing = current_results or ""

        if not self.broadcast_enabled:
            yield self._ask_all_state(
                question,
                existing,
                editable=True,
                submit_interactive=False,
                status=self._t("ask_all_disabled"),
            )
            return

        if not question:
            yield self._ask_all_state(
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
        running = {
            "editable": False,
            "submit_visible": False,
            "submit_interactive": False,
        }
        yield self._ask_all_state(question, format_ask_all_results(replies), **running)

        # Wiki-Lookup einmal für alle Personas; Hints nur anzeigen, Snippets
        # als geteilter System-Kontext vor die Frage jedes Broadcasts legen.
        wiki_hints, contexts = self.wiki.snippets(question, "ask_all")
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
            yield self._ask_all_state(
                question,
                format_ask_all_results(replies),
                status=wiki_status,
                sources_md=sources_md,
                **running,
            )

        # Parallel: alle Personas streamen gleichzeitig in ihre Sektionen;
        # sequenzieller Fallback per ui.experimental.broadcast_parallel: false.
        if self.broadcast_parallel:
            stop = threading.Event()
            session.ask_all_stop = stop
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
        last_flush = 0.0
        for event in events_iter:
            replies[event["persona"]] = event["reply"] or "…"

            now = time.monotonic()
            if event["type"] == "done" or now - last_flush >= STREAM_FLUSH_INTERVAL_S:
                last_flush = now
                yield self._ask_all_state(
                    question,
                    format_ask_all_results(replies),
                    status=wiki_status,
                    sources_md=sources_md,
                    **running,
                )

        session.ask_all_stop = None
        # Broadcast fertig: Eingabe und Senden wieder freigeben für Folgefragen
        yield self._ask_all_state(
            question,
            format_ask_all_results(replies),
            status=wiki_status,
            sources_md=sources_md,
            editable=True,
        )

    def _load_failure_updates(self, message: str) -> tuple:
        updates = self._reset_updates()
        updates["load_status"] = gr.update(value=message, visible=True)
        return as_persona_outputs(updates)

    def _conversation_loaded_updates(
        self,
        persona_key: str,
        persona: dict[str, Any],
        meta: dict,
        messages: list[Message],
        input_placeholder: str,
        conversation_id: str = "",
    ) -> tuple:
        display_name = persona["name"].title()
        focus_text = f"### {persona['name']}\n{persona['description']}"
        chat_history = messages_to_chat_history(messages)

        greeting = self._t("web_load_status_success", persona_name=display_name)

        updates = self._reset_updates()
        updates.update(
            selected_persona_state=gr.update(value=persona_key),
            grid_group=gr.update(visible=False),
            focus_group=gr.update(visible=True),
            focus_img=gr.update(value=self._persona_full_image_path(persona["name"])),
            focus_md=gr.update(value=focus_text),
            greeting_md=gr.update(value=greeting, visible=True),
            chatbot=gr.update(value=chat_history, label=display_name, visible=True),
            input_box=gr.update(
                value="", visible=True, interactive=True, placeholder=input_placeholder
            ),
            send_btn=gr.update(visible=True, interactive=True),
            new_chat_btn=gr.update(visible=True),
            download_btn=gr.update(visible=self.file_exchange_enabled),
            briefing_btn=gr.update(visible=self.briefing_enabled),
            read_aloud_btn=gr.update(visible=self.tts_web_enabled),
            history_state=messages,
            meta_state=meta,
            ask_all_question=gr.update(
                value="",
                visible=False,
                interactive=True,
                placeholder=self.ask_all_placeholder,
            ),
            load_status=gr.update(value=greeting, visible=True),
            # Ohne die ID schriebe die Fortsetzung ins Leere: SqliteStore.append
            # steigt bei leerer conversation_id sofort aus.
            conversation_state=conversation_id,
        )
        return as_persona_outputs(updates)

    def _on_load_conversation(
        self,
        session: SessionContext,
        upload_path: str | None,
        persona_info: dict[str, dict[str, Any]],
        input_placeholder: str,
    ) -> tuple:
        if not upload_path:
            warning = self._t("web_load_missing_file")
            return self._load_failure_updates(warning)

        try:
            meta, messages = load_conversation(upload_path)
        except (OSError, ValueError) as exc:
            msg = self._t("web_load_status_error", reason=str(exc))
            return self._load_failure_updates(msg)

        persona_name = meta.get("persona")
        persona_key = (persona_name or "").lower()
        # Dieselbe Prüfung wie im Verlauf: eine hochgeladene Gast-Konversation
        # („Leah") darf nicht als die echte LEAH weiterlaufen — hier wöge das
        # sogar schwerer, weil das Gespräch danach fortsetzbar wäre.
        persona = self._continuable_persona(persona_name, meta.get("app"), persona_info)

        if not persona:
            msg = self._t(
                "web_load_invalid_persona", persona_name=persona_name or "<unknown>"
            )
            return self._load_failure_updates(msg)

        user = str(meta.get("user") or "")
        session.bot = persona["name"]
        session.streamer = self.factory.get_streamer_for_persona(session.bot)
        self._stamp_user(session, user)
        # Eine hochgeladene Datei wird ab hier fortgesetzt — also gehört sie in
        # die Ablage, sonst schriebe jeder weitere Turn ins Leere. Das Terminal
        # macht das nach dem Laden längst (`TerminalUI._set_persona`); die WebUI
        # war die Abweichlerin. Eigenes `app`, damit im Verlauf erkennbar
        # bleibt, dass dieses Gespräch von außen kam.
        conversation_id = self._open_conversation(session.bot, user, app=IMPORT_APP)
        self._stamp_conversation(session, conversation_id)

        normalized_meta = dict(meta)
        normalized_meta.setdefault("app", "web")

        return self._conversation_loaded_updates(
            persona_key,
            persona,
            normalized_meta,
            messages,
            input_placeholder,
            conversation_id=conversation_id,
        )

    def _on_download_conversation(
        self,
        session: SessionContext,
        messages: list[Message] | None,
        meta: dict | None,
    ) -> tuple:
        if not (meta and meta.get("persona")) and not session.bot:
            msg = self._t("no_selection_warning")
            return gr.update(value=None, visible=False), gr.update(
                value=msg, visible=True
            )

        try:
            payload = {
                "meta": meta or self._build_meta(session.bot or ""),
                "messages": messages or [],
            }

            path = self._delivery_file(session, "download", ".json")
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            file_path = str(path)
        except Exception as exc:  # pragma: no cover - UI utility
            msg = self._t("web_save_status_error", reason=str(exc))
            return gr.update(value=None, visible=False), gr.update(
                value=msg, visible=True
            )

        success = self._t("web_save_status_ready")
        return gr.update(value=file_path, visible=True), gr.update(
            value=success, visible=True
        )

    def _resolve_feedback_log_path(self) -> str:
        if self.feedback_log_path:
            return self.feedback_log_path
        log_cfg = getattr(self.cfg, "logging", None)
        log_dir = log_cfg.get("dir", "logs") if isinstance(log_cfg, dict) else "logs"
        ensure_dir_exists(log_dir)
        self.feedback_log_path = os.path.join(log_dir, "feedback_votes.jsonl")
        return self.feedback_log_path

    def _on_chat_like(
        self,
        session: SessionContext,
        chat_history: list[ChatPair] | None,
        meta: dict | None,
        evt: gr.LikeData,
    ) -> None:
        # Votes must never break the UI: any failure is logged and swallowed.
        try:
            row, col = -1, 1
            answer = str(evt.value)
            try:
                row, col = int(evt.index[0]), int(evt.index[1])
                answer = str(chat_history[row][col])
            except (TypeError, ValueError, IndexError):
                logging.warning("Feedback vote with unexpected index %r", evt.index)

            # Gradio 4.44 renders the thumbs on the user row as well (live
            # verified). A vote on one's own question is no training signal,
            # so only bot answers (column 1) are recorded.
            if col != 1:
                logging.debug("Ignoring feedback vote on a user message (row %s)", row)
                return

            meta = meta if isinstance(meta, dict) else {}
            entry = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "app": meta.get("app", "web"),
                "user": meta.get("user") or self._fallback_user(),
                "persona": meta.get("persona") or session.bot or "",
                "model": meta.get("model", ""),
                "vote": "up" if evt.liked else "down",
                "question": find_question_for_row(chat_history, row),
                "answer": answer,
                "index": [row, col],
            }
            path = self._resolve_feedback_log_path()
            with _feedback_log_lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError, AttributeError):
            logging.exception("Could not write feedback log %s", self.feedback_log_path)

    def _bind_events(
        self,
        components: dict[str, Any],
        persona_info: dict[str, dict[str, Any]],
        greeting_template: str,
        input_placeholder: str,
    ) -> None:
        chatbot = components["chatbot"]
        input_box = components["input_box"]
        send_btn = components["send_btn"]
        new_chat_btn = components["new_chat_btn"]
        download_btn = components["download_btn"]
        download_file = components["download_file"]
        save_status = components["save_status"]
        history_state = components["history_state"]
        meta_state = components["meta_state"]
        ask_all_results = components["ask_all_results"]
        ask_all_question = components["ask_all_question"]
        ask_all_submit = components["ask_all_submit"]
        ask_all_new_chat = components["ask_all_new_chat"]
        ask_all_card_btn = components["ask_all_card_btn"]
        ask_all_outputs = [components[key] for key in ASK_ALL_OUTPUT_KEYS]
        self_talk_card_btn = components["self_talk_card_btn"]
        self_talk_status = components["self_talk_status"]
        self_talk_persona_a = components["self_talk_persona_a"]
        self_talk_persona_b = components["self_talk_persona_b"]
        self_talk_prompt = components["self_talk_prompt"]
        self_talk_start_btn = components["self_talk_start_btn"]
        load_input = components["load_input"]
        load_status = components["load_status"]
        model_dropdown = components["model_dropdown"]
        model_status = components["model_status"]
        mic_audio = components["mic_audio"]
        briefing_btn = components["briefing_btn"]
        read_aloud_btn = components["read_aloud_btn"]
        tts_audio = components["tts_audio"]
        stop_btn = components["stop_btn"]
        regenerate_btn = components["regenerate_btn"]

        # Same order as the update dicts resolved via _as_persona_outputs()
        persona_outputs = [components[key] for key in PERSONA_OUTPUT_KEYS]

        # Parameter, die aus `inputs=` kommen, stehen bewusst ohne Default da:
        # ein Handler, der stillschweigend auf einen leeren Nutzer zurückfällt,
        # schreibt Gespräche unter der falschen Identität weg.
        user_state = components["user_state"]
        # Persona, Streamer und Kill-Switches dieser Browser-Sitzung (siehe
        # ui/session.py). Steht bewusst als *erster* Input jedes Handlers, der
        # sie braucht — die Reihenfolge hier ist die Parameterreihenfolge dort.
        session_state = components["session_state"]

        # Identität einmal pro Browser-Sitzung einsammeln (#53).
        components["demo"].load(
            fn=self._on_page_load, inputs=[], outputs=[user_state], queue=False
        )

        for key, btn in components["persona_buttons"]:
            btn.click(
                fn=partial(
                    self._on_persona_selected,
                    key=key,
                    persona_info=persona_info,
                    greeting_template=greeting_template,
                    input_placeholder=input_placeholder,
                ),
                inputs=[session_state, user_state],
                outputs=persona_outputs,
                queue=False,
            )

        load_input.upload(
            fn=partial(
                self._on_load_conversation,
                persona_info=persona_info,
                input_placeholder=input_placeholder,
            ),
            inputs=[session_state, load_input],
            outputs=persona_outputs,
            queue=False,
        )

        # Profi-Option: .change feuert nur bei Nutzer-Interaktion, nicht beim
        # Initialwert; bewusst außerhalb der PERSONA_OUTPUT_KEYS gehalten.
        model_dropdown.change(
            fn=self._on_model_selected,
            inputs=[session_state, model_dropdown, components["conversation_state"]],
            outputs=[model_status],
            queue=False,
        )

        # queue=True: die Whisper-Transkription dauert Sekunden (erste
        # Aufnahme lädt zusätzlich das Modell).
        mic_audio.stop_recording(
            fn=self._on_mic_recorded,
            inputs=[mic_audio, input_box],
            outputs=[input_box, mic_audio],
            queue=True,
        )

        # Stream-Steuerung (#35): die Button-Updates reisen in denselben Yields
        # mit (siehe _with_stream_controls) — ein vorgeschaltetes Event hätte den
        # ersten Token um Sekunden verzögert. Aus demselben Grund hängen auch die
        # Quellen (#32) an denselben Yields.
        stream_buttons = [components[key] for key in STREAM_CONTROL_KEYS]
        stream_outputs = [
            *(components[key] for key in STREAM_OUTPUT_KEYS),
            *stream_buttons,
        ]

        input_submit_evt = input_box.submit(
            fn=self.respond_streaming_with_controls,
            inputs=[session_state, input_box, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        send_click_evt = send_btn.click(
            fn=self.respond_streaming_with_controls,
            inputs=[session_state, input_box, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        # Kein `cancels`: der Kill-Switch beendet den Generator geordnet, damit
        # die Teilantwort im Verlauf bleibt.
        stop_btn.click(
            fn=self._on_stop_stream,
            inputs=[session_state],
            outputs=stream_buttons,
            queue=False,
        )

        regenerate_evt = regenerate_btn.click(
            fn=self.regenerate_with_controls,
            inputs=[session_state, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        download_btn.click(
            fn=self._on_download_conversation,
            inputs=[session_state, history_state, meta_state],
            outputs=[download_file, save_status],
            queue=False,
        )

        briefing_evt = briefing_btn.click(
            fn=self.respond_briefing_with_controls,
            inputs=[session_state, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        # queue=True: die Piper-Synthese längerer Antworten dauert Sekunden
        read_aloud_btn.click(
            fn=self._on_read_aloud,
            inputs=[session_state, history_state],
            outputs=[tts_audio],
            queue=True,
        )

        # Binding .like() auto-enables the thumb buttons on the chatbot (#40).
        chatbot.like(
            fn=self._on_chat_like,
            inputs=[session_state, chatbot, meta_state],
            outputs=[],
            queue=False,
        )

        if ask_all_card_btn is not None:
            ask_all_card_btn.click(
                fn=self._on_show_ask_all,
                inputs=[session_state],
                outputs=persona_outputs,
                queue=False,
            )

        components["history_card_btn"].click(
            fn=self._on_show_history,
            inputs=[session_state, user_state],
            outputs=persona_outputs,
            queue=False,
        )

        # user_state gehört in *jeden* Verlauf-Handler: die Gesprächs-ID kommt
        # vom Client und wird von Gradio nicht gegen die Auswahlliste geprüft.
        components["history_pick"].change(
            fn=self._on_history_selected,
            inputs=[components["history_pick"], user_state],
            outputs=[components["history_preview"]],
            queue=False,
        )

        components["history_open_btn"].click(
            fn=partial(
                self._on_history_open,
                persona_info=persona_info,
                input_placeholder=input_placeholder,
            ),
            inputs=[session_state, components["history_pick"], user_state],
            outputs=persona_outputs,
            queue=False,
        )

        components["history_export_btn"].click(
            fn=self._on_history_export,
            inputs=[session_state, components["history_pick"], user_state],
            outputs=[components["history_file"]],
            queue=False,
        )

        components["history_delete_btn"].click(
            fn=self._on_history_delete,
            inputs=[
                components["history_pick"],
                components["history_confirm"],
                user_state,
            ],
            outputs=[
                components["history_pick"],
                components["history_preview"],
                components["history_status"],
                components["history_file"],
                components["history_confirm"],
            ],
            queue=False,
        )

        components["guest_card_btn"].click(
            fn=self._on_show_guest,
            inputs=[session_state],
            outputs=persona_outputs,
            queue=False,
        )

        components["guest_start_btn"].click(
            fn=partial(
                self._on_start_guest,
                greeting_template=greeting_template,
                input_placeholder=input_placeholder,
            ),
            inputs=[
                session_state,
                components["guest_name"],
                components["guest_prompt"],
                components["guest_temperature"],
                user_state,
            ],
            outputs=persona_outputs,
            queue=False,
        )

        if self_talk_card_btn is not None:
            self_talk_card_btn.click(
                fn=self._on_show_self_talk,
                inputs=[session_state],
                outputs=persona_outputs,
                queue=False,
            )

        self_talk_stream_evt = self_talk_start_btn.click(
            fn=self._on_start_self_talk,
            inputs=[
                session_state,
                self_talk_persona_a,
                self_talk_persona_b,
                self_talk_prompt,
            ],
            outputs=[
                self_talk_status,
                chatbot,
                history_state,
                input_box,
                send_btn,
                new_chat_btn,
                meta_state,
                load_status,
            ],
            queue=False,
        ).then(
            fn=self._run_self_talk_stream,
            inputs=[session_state, chatbot, history_state],
            outputs=[chatbot, history_state],
            queue=True,
        )

        ask_all_submit_evt = ask_all_submit.click(
            fn=self._on_submit_ask_all,
            inputs=[session_state, ask_all_question, ask_all_results],
            outputs=ask_all_outputs,
            queue=True,
        )

        ask_all_question_evt = ask_all_question.submit(
            fn=self._on_submit_ask_all,
            inputs=[session_state, ask_all_question, ask_all_results],
            outputs=ask_all_outputs,
            queue=True,
        )

        # "New conversation" bricht laufende Streams aktiv ab (#2): das Schließen
        # des Generators löst über GeneratorExit das finally in
        # YulYenStreamingProvider.stream aus, das den LLM-Stream beendet.
        new_chat_btn.click(
            fn=self._on_reset_to_start,
            inputs=[session_state],
            outputs=persona_outputs,
            queue=False,
            cancels=[
                input_submit_evt,
                send_click_evt,
                self_talk_stream_evt,
                briefing_evt,
                regenerate_evt,
            ],
        )

        ask_all_new_chat.click(
            fn=self._on_reset_to_start,
            inputs=[session_state],
            outputs=persona_outputs,
            queue=False,
            cancels=[ask_all_submit_evt, ask_all_question_evt],
        )

    def _start_server(self, demo: gr.Blocks) -> None:
        launch_kwargs: dict[str, Any] = {
            "server_name": self.web_host,
            "server_port": self.web_port,
            "show_api": False,
        }

        # Anmeldung gilt jetzt unabhängig von `share` (#53): die App horcht per
        # Default auf 0.0.0.0, war im LAN aber ungeschützt, weil das alte
        # share_auth nur beim Share-Link griff.
        gradio_auth = self.auth.gradio_auth()
        if gradio_auth is not None:
            launch_kwargs["auth"] = gradio_auth
        logging.info("WebUI-Anmeldung: provider=%s", self.auth.name)

        ui_cfg = getattr(self.cfg, "ui", None)
        if ui_cfg is not None:
            if isinstance(ui_cfg, dict):
                web_cfg = ui_cfg.get("web") or {}
            else:
                web_cfg = getattr(ui_cfg, "web", {}) or {}

            if web_cfg.get("share"):
                if gradio_auth is None:
                    logging.warning(
                        "Gradio share disabled: 'ui.web.share' is on but no login is "
                        "configured — see 'ui.web.auth'."
                    )
                else:
                    launch_kwargs["share"] = True

        demo.launch(**launch_kwargs)

    def launch(self) -> None:
        ui = self.texts
        default_model = str(self.cfg.core.get("model_name", ""))
        project_title = ui.get("project_name")
        choose_persona_txt = ui.get("choose_persona")
        new_chat_label = ui.get("new_chat")
        send_button_label = ui.get("send_button")
        input_placeholder = ui.get("input_placeholder")
        greeting_template = ui.get("greeting")
        persona_btn_suffix = ui.get("persona_button_suffix")
        ask_all_button_label = ui.get("ask_all_button_label", "Frage an alle")
        ask_all_title = ui.get("ask_all_title", "Frage an alle Personas")
        ask_all_input_placeholder = ui.get(
            "ask_all_input_placeholder", "Stelle eine Frage an alle Personas …"
        )
        load_label = ui.get("web_load_label", "Gespräch laden (JSON)")
        self_talk_button_label = ui.get("self_talk_button_label", "AI Dialog")
        self_talk_title = ui.get("self_talk_title", "AI Dialog")
        self_talk_description = ui.get(
            "self_talk_description", "Zwei Personas sprechen automatisch."
        )
        self_talk_persona_a_label = ui.get("self_talk_persona_a_label", "Persona A")
        self_talk_persona_b_label = ui.get("self_talk_persona_b_label", "Persona B")
        self_talk_prompt_label = ui.get("self_talk_prompt_label", "Start-Prompt")
        self_talk_start_label = ui.get("self_talk_start_label", "AI Dialog starten")
        self_talk_prompt_placeholder = ui.get(
            "self_talk_prompt_placeholder", "Gib den Start-Prompt ein …"
        )
        save_button_label = ui.get("web_save_button", "Gespräch herunterladen (JSON)")
        advanced_label = ui.get("web_advanced_label", "Erweitert")
        model_dropdown_label = ui.get("web_model_dropdown_label", "Modell")
        model_hint = ui.get("web_model_hint", "")
        model_choices = self._available_models(default_model)
        mic_label = ui.get("web_mic_label", "Spracheingabe (Mikrofon)")
        briefing_label = ui.get("web_briefing_button", "Briefing 📰")
        read_aloud_label = ui.get("web_read_aloud_button", "Vorlesen 🔊")
        stop_label = ui.get("web_stop_button", "Stop ⏹")
        regenerate_label = ui.get("web_regenerate_button", "Nochmal 🔄")
        sources_label = ui.get("web_sources_label", "Quellen 📚")
        theme_light_label = ui.get("web_theme_light", "☀️ Hell")
        theme_dark_label = ui.get("web_theme_dark", "🌙 Dunkel")
        guest_card_label = ui.get("guest_card_label", "Gast anlegen")
        guest_title = ui.get("guest_title", "Gast-Persona")
        guest_description = ui.get(
            "guest_description", "Eigene Persona, nur für diese Sitzung."
        )
        guest_name_label = ui.get("guest_name_label", "Name")
        guest_prompt_label = ui.get("guest_prompt_label", "System-Prompt")
        guest_prompt_placeholder = ui.get("guest_prompt_placeholder", "Du bist …")
        guest_temperature_label = ui.get("guest_temperature_label", "Temperatur")
        guest_start_label = ui.get("guest_start_label", "Gast starten")
        history_card_label = ui.get("history_card_label", "Verlauf öffnen")
        history_title = ui.get("history_title", "Verlauf")
        history_description = ui.get("history_description", "Frühere Gespräche")
        history_pick_label = ui.get("history_pick_label", "Gespräch")
        history_open_label = ui.get("history_open_label", "Öffnen")
        history_export_label = ui.get("history_export_label", "Als Markdown")
        history_delete_label = ui.get("history_delete_label", "Löschen")
        history_confirm_label = ui.get("history_confirm_label", "Löschen bestätigen")

        self.ask_all_placeholder = ask_all_input_placeholder
        self.self_talk_prompt_placeholder = self_talk_prompt_placeholder

        persona_info = {p["name"].lower(): p for p in _load_system_prompts()}

        demo, components = build_ui(
            persona_thumbnail_path_fn=self._persona_thumbnail_path,
            persona_info=persona_info,
            broadcast_enabled=self.broadcast_enabled,
            project_title=project_title,
            choose_persona_txt=choose_persona_txt,
            persona_btn_suffix=persona_btn_suffix,
            input_placeholder=input_placeholder,
            new_chat_label=new_chat_label,
            send_button_label=send_button_label,
            ask_all_button_label=ask_all_button_label,
            ask_all_title=ask_all_title,
            ask_all_input_placeholder=ask_all_input_placeholder,
            self_talk_button_label=self_talk_button_label,
            self_talk_title=self_talk_title,
            self_talk_description=self_talk_description,
            self_talk_persona_a_label=self_talk_persona_a_label,
            self_talk_persona_b_label=self_talk_persona_b_label,
            self_talk_prompt_label=self_talk_prompt_label,
            self_talk_start_label=self_talk_start_label,
            self_talk_prompt_placeholder=self_talk_prompt_placeholder,
            load_label=load_label,
            save_button_label=save_button_label,
            advanced_label=advanced_label,
            model_dropdown_label=model_dropdown_label,
            model_hint=model_hint,
            model_choices=model_choices,
            model_value=default_model,
            mic_label=mic_label,
            briefing_label=briefing_label,
            read_aloud_label=read_aloud_label,
            stop_label=stop_label,
            regenerate_label=regenerate_label,
            sources_label=sources_label,
            theme_light_label=theme_light_label,
            theme_dark_label=theme_dark_label,
            guest_card_label=guest_card_label,
            guest_title=guest_title,
            guest_description=guest_description,
            guest_name_label=guest_name_label,
            guest_prompt_label=guest_prompt_label,
            guest_prompt_placeholder=guest_prompt_placeholder,
            guest_temperature_label=guest_temperature_label,
            guest_start_label=guest_start_label,
            history_card_label=history_card_label,
            history_title=history_title,
            history_description=history_description,
            history_pick_label=history_pick_label,
            history_open_label=history_open_label,
            history_export_label=history_export_label,
            history_delete_label=history_delete_label,
            history_confirm_label=history_confirm_label,
            file_exchange_enabled=self.file_exchange_enabled,
        )
        # Gradio 4.x requires events to be bound within a Blocks context.
        # Reopening the demo as a context lets us keep the existing structure
        # while still registering the events correctly.
        with demo:
            self._bind_events(
                components,
                persona_info,
                greeting_template,
                input_placeholder,
            )
        self._start_server(demo)
