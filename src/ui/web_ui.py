from __future__ import annotations

import importlib.util
import json
import logging
import os
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
from briefing.feeds import fetch_briefing_items, inject_briefing_context
from config.personas import _load_system_prompts, get_all_persona_names, get_drink
from core.context_utils import context_near_limit, shrink_history_for_context
from core.orchestrator import iter_broadcast_events, iter_broadcast_events_parallel
from core.system_checks import fetch_model_names
from core.utils import ensure_dir_exists, is_broadcast_enabled, is_broadcast_parallel
from stt.whisper_stt import is_stt_available, transcribe_wav
from ui.conversation_io_terminal import load_conversation
from ui.self_talk import SelfTalkRunner
from ui.webui_layout import build_ui
from wiki.lookup import (
    WikiSnippet,
    format_snippet_meta,
    inject_wiki_context,
    lookup_wiki_snippet,
)

if TYPE_CHECKING:
    from config.config_singleton import Config
    from core.factory import AppFactory
    from wiki.spacy_keyword_finder import SpacyKeywordFinder

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

# Single source of truth for the order of the "switch view" output components.
# Every handler bound to these outputs builds a dict keyed by these names and
# resolves it via WebUI._as_persona_outputs() — never by positional index.
PERSONA_OUTPUT_KEYS = (
    "selected_persona_state",
    "grid_group",
    "focus_group",
    "focus_img",
    "focus_md",
    "greeting_md",
    "chatbot",
    "input_box",
    "send_btn",
    "new_chat_btn",
    "download_btn",
    "download_file",
    "save_status",
    "history_state",
    "meta_state",
    "ask_all_group",
    "ask_all_results",
    "ask_all_question",
    "ask_all_submit",
    "ask_all_new_chat",
    "ask_all_status",
    "load_status",
    "self_talk_group",
    "self_talk_status",
    "self_talk_persona_a",
    "self_talk_persona_b",
    "self_talk_prompt",
    "self_talk_start_btn",
    "mic_audio",
    "briefing_btn",
    "read_aloud_btn",
    "tts_audio",
    "stop_btn",
    "regenerate_btn",
    "sources_accordion",
    "sources_md",
    "ask_all_sources_accordion",
    "ask_all_sources_md",
)

# Ausgaben jedes streamenden Handlers, in dieser Reihenfolge. Die Quellen (#32)
# reisen bewusst in denselben Yields mit statt als eigenes .then()-Event davor —
# das hätte den ersten Token um Sekunden verzögert (siehe _with_stream_controls).
STREAM_OUTPUT_KEYS = (
    "input_box",
    "chatbot",
    "history_state",
    "sources_accordion",
    "sources_md",
)

# Was _with_stream_controls hinter STREAM_OUTPUT_KEYS anhängt.
STREAM_CONTROL_KEYS = ("send_btn", "stop_btn", "regenerate_btn")

# Reihenfolge der Ask-All-Ausgaben — dieselbe, die _ask_all_state aufbaut.
ASK_ALL_OUTPUT_KEYS = (
    "ask_all_question",
    "ask_all_status",
    "ask_all_results",
    "ask_all_submit",
    "ask_all_new_chat",
    "ask_all_sources_accordion",
    "ask_all_sources_md",
)


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
        keyword_finder: SpacyKeywordFinder | None,
        wiki_snippet_limit: int,
        max_wiki_snippets: int,
        wiki_mode: str,
        proxy_port: int,
        web_host: str,
        web_port: int | str,
        wiki_timeout: tuple[float, float],
    ) -> None:
        self.streamer = None  # assigned later
        self.keyword_finder = keyword_finder
        self.cfg = config
        self.factory = factory
        self.wiki_snippet_limit = wiki_snippet_limit
        self.max_wiki_snippets = max_wiki_snippets
        self.wiki_mode = wiki_mode
        self.proxy_port = proxy_port
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout
        self.bot: str | None = None  # assigned later
        self.texts = getattr(config, "texts", {}) or {}
        self._t = getattr(config, "t", getattr(self.texts, "format", None))
        self.broadcast_enabled = is_broadcast_enabled(self.cfg)
        self.broadcast_parallel = is_broadcast_parallel(self.cfg)
        # Kill switch für den laufenden Ask-All-Broadcast: Gradio cancels
        # schließt den Handler-Generator nicht zuverlässig (bricht nur den
        # asyncio-Task ab), daher muss der Reset-Handler die Worker direkt
        # über dieses Event stoppen.
        self._ask_all_stop: threading.Event | None = None
        # Kill switch für Einzelchat/Briefing/Self-Talk (#35). Gleiche Begründung
        # wie bei _ask_all_stop: Gradios `cancels` bricht nur den asyncio-Task
        # ab, das finally eines laufenden Generators läuft nicht zuverlässig.
        # Der Stop-Button ist ein eigenes, verlässlich laufendes Event.
        self._stream_stop: threading.Event | None = None
        self.ask_all_placeholder = ""
        self.self_talk_runner = None
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
            and importlib.util.find_spec("piper") is not None
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

    def _build_meta(self, persona_name: str) -> dict:
        return {
            "created_at": datetime.now().isoformat(),
            "model": str(self.cfg.core.get("model_name")),
            "persona": persona_name,
            "app": "web",
        }

    def _messages_to_chat_history(
        self, messages: list[Message] | None
    ) -> list[ChatPair]:
        chat_history = []
        pending_user = None

        for item in messages or []:
            role = item.get("role")
            content = item.get("content")

            if role == "user":
                if pending_user is not None:
                    chat_history.append((pending_user, None))
                pending_user = content
            elif role == "assistant":
                if pending_user is not None:
                    chat_history.append((pending_user, content))
                    pending_user = None
                else:
                    chat_history.append((None, content))

        if pending_user is not None:
            chat_history.append((pending_user, None))

        return chat_history

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
        self, llm_history: list[Message], chat_history: list[ChatPair]
    ) -> bool:

        if not context_near_limit(llm_history, self.streamer.persona_options):
            return False

        drink = get_drink(self.bot)
        warn = self._t("context_wait_message", persona_name=self.bot, drink=drink)

        chat_history.append((None, warn))

        persona_options = getattr(self.streamer, "persona_options", {}) or {}
        llm_history[:] = shrink_history_for_context(
            llm_history,
            self.cfg,
            persona_options,
            llm_core=getattr(self.streamer, "_llm_core", None),
            chat_model_name=getattr(self.streamer, "model_name", ""),
            persona_name=self.bot,
        )
        return True

    # ---------- Wiki-Quellen (#32) ----------
    def _format_wiki_sources(self, snippets: list[WikiSnippet]) -> str:
        """Markdown für das Quellen-Accordion.

        Zeigt bewusst den *injizierten* Text und dessen Länge, nicht nur Titel
        und Link: nur so ist erkennbar, worauf eine Antwort beruht — und ob der
        Artikel an ``wiki.snippet_limit`` abgeschnitten wurde, das Modell den
        Rest also nie gesehen hat.
        """
        sections = []
        for idx, snip in enumerate(snippets or [], start=1):
            title = snip.topic or "?"
            heading = f"[{title}]({snip.link})" if snip.link else title
            meta = format_snippet_meta(snip, self._t)
            # Blockquote: hebt den fremden Text vom Rahmen ab und bleibt auch
            # bei 1200 Zeichen am Stück lesbar.
            quoted = "\n".join(
                f"> {line}" if line.strip() else ">"
                for line in snip.snippet.splitlines()
            )
            sections.append(f"### {idx}. {heading}\n*{meta}*\n\n{quoted}")
        return "\n\n---\n\n".join(sections)

    def _wiki_source_updates(self, snippets: list[WikiSnippet] | None) -> tuple:
        """Accordion + Markdown; ohne Treffer bleibt das Accordion unsichtbar."""
        markdown = self._format_wiki_sources(snippets or [])
        return gr.update(visible=bool(markdown)), gr.update(value=markdown)

    @staticmethod
    def _wiki_sources_unchanged() -> tuple:
        return gr.update(), gr.update()

    # Stream the response (UI updates continuously)
    def _arm_stream_stop(self) -> threading.Event:
        """Fresh kill switch for the stream that is about to start (#35)."""
        stop = threading.Event()
        self._stream_stop = stop
        return stop

    def _stop_requested(self, stop: threading.Event) -> bool:
        """True when *this* stream was asked to stop.

        Identity check on purpose: a newer stream replaces `_stream_stop`, and a
        stale generator must not react to the new stream's switch.
        """
        return self._stream_stop is stop and stop.is_set()

    def _stream_reply(
        self, message_history: list[Message], chat_history: list[ChatPair]
    ) -> Iterator[tuple]:
        # Die Quellen-Slots stehen vor dem Stream schon fest und bleiben hier
        # unangetastet — gr.update() ohne Wert ist ein No-op für die Anzeige.
        keep = self._wiki_sources_unchanged()
        # Gedrosselt wie in der Ask-All-Ansicht: nicht jedes Token einzeln über
        # den Socket schicken; last_flush=0.0 lässt den ersten Chunk sofort durch.
        reply = ""
        last_flush = 0.0
        stop = self._arm_stream_stop()
        stopped = False
        # Explizites Iterator-Handle, damit der Stream beim Stop deterministisch
        # geschlossen wird (close() löst das finally im Streaming-Provider aus und
        # beendet damit den Ollama-Stream) statt erst irgendwann per GC.
        tokens = self.streamer.stream(messages=message_history)
        try:
            for token in tokens:
                if self._stop_requested(stop):
                    stopped = True
                    break
                reply += token
                now = time.monotonic()
                if now - last_flush >= STREAM_FLUSH_INTERVAL_S:
                    last_flush = now
                    yield None, chat_history + [(None, reply)], message_history, *keep
        finally:
            close = getattr(tokens, "close", None)
            if close is not None:
                close()
            if self._stream_stop is stop:
                self._stream_stop = None

        if stopped:
            # Teilantwort behalten — sie ist der Grund, warum man abbricht.
            reply += self._t("web_stream_stopped_suffix")

        # Finalize: add the completed reply to the history
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history, *keep

    def respond_streaming(
        self,
        user_input: str,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:

        # Safety check: persona not selected yet → UI should prevent this, but we double-check
        if not self.bot:
            yield "", chat_history, history_state, *self._wiki_sources_unchanged()
            return

        # 1) Maintain a dedicated LLM history without UI hints (and compress if needed)
        llm_history = list(history_state or [])

        # 2) Clear the input field and show the user message in the chat window
        #    Die Quellen der vorigen Antwort gehören nicht zur neuen Frage und
        #    verschwinden deshalb sofort (#32).
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append((user_input, None))
        yield "", chat_history, llm_history, *self._wiki_source_updates([])

        # 3) Wiki hint and snippet (top hit)
        wiki_hints, contexts = lookup_wiki_snippet(
            user_input,
            self.bot,
            self.keyword_finder,
            self.wiki_mode,
            self.proxy_port,
            self.wiki_snippet_limit,
            self.wiki_timeout,
            self.max_wiki_snippets,
        )

        # Display the UI hints (do not add them to the LLM context window)
        for wiki_hint in wiki_hints:
            if wiki_hint:
                chat_history.append((None, wiki_hint))
        if wiki_hints or contexts:
            yield None, chat_history, llm_history, *self._wiki_source_updates(contexts)

        # 4) Optional: inject wiki context
        if contexts:
            inject_wiki_context(llm_history, contexts)

        # 5) Send the user question to the LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Compress the context if needed and record that in chat history
        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history, *self._wiki_sources_unchanged()

        # 7) Stream the answer
        yield from self._stream_reply(llm_history, chat_history)

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
        user_input: str,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self.respond_streaming(user_input, chat_history, history_state)
        )

    def respond_briefing_with_controls(
        self, chat_history: list[ChatPair], history_state: list[Message] | None
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self.respond_briefing(chat_history, history_state)
        )

    def regenerate_with_controls(
        self, chat_history: list[ChatPair], history_state: list[Message] | None
    ) -> Iterator[tuple]:
        yield from self._with_stream_controls(
            self._on_regenerate(chat_history, history_state)
        )

    def _on_stop_stream(self) -> tuple:
        """Stoppt den laufenden Stream (#35).

        Eigenes Gradio-Event statt `cancels`: nur so läuft der Handler
        garantiert und der Generator kommt geordnet zum Ende — mit Teilantwort
        im Verlauf, statt sie wegzuwerfen.
        """
        stop = self._stream_stop
        if stop is not None:
            stop.set()
        return self._streaming_button_updates(streaming=False)

    def _on_regenerate(
        self, chat_history: list[ChatPair], history_state: list[Message] | None
    ) -> Iterator[tuple]:
        """Letzte Antwort verwerfen und mit identischem Kontext neu streamen.

        Varianz kommt allein aus der Temperatur der Persona — es wird nichts am
        Prompt gedreht. Die Quellen bleiben aus demselben Grund stehen: gleicher
        Kontext, gleiche Snippets (#32).
        """
        chat_history = list(chat_history or [])
        llm_history = list(history_state or [])
        keep = self._wiki_sources_unchanged()

        if not self.bot or not self.streamer:
            yield gr.update(), chat_history, llm_history, *keep
            return

        if not llm_history or llm_history[-1].get("role") != "assistant":
            gr.Warning(self._t("web_regenerate_nothing"))
            yield gr.update(), chat_history, llm_history, *keep
            return

        llm_history.pop()
        # In der Anzeige ist die Antwort die letzte Bot-Zeile; Wiki-/Briefing-Hints
        # sind ebenfalls Bot-Zeilen, stehen aber davor und bleiben stehen.
        if chat_history and chat_history[-1][0] is None:
            chat_history.pop()
        yield gr.update(), chat_history, llm_history, *keep

        # gr.update() statt None: ein noch nicht abgeschickter Entwurf im
        # Eingabefeld soll durch das Neuerzeugen nicht verloren gehen.
        for _input_value, updated_chat, updated_state, *sources in self._stream_reply(
            llm_history, chat_history
        ):
            yield gr.update(), updated_chat, updated_state, *sources

    def respond_briefing(
        self, chat_history: list[ChatPair], history_state: list[Message] | None
    ) -> Iterator[tuple]:
        """Wie respond_streaming, nur mit RSS-Feeds statt Wiki als Kontext."""
        keep = self._wiki_sources_unchanged()
        if not self.bot or not self.briefing_enabled:
            yield gr.update(), chat_history, history_state, *keep
            return

        llm_history = list(history_state or [])
        briefing_prompt = self._t("briefing_user_prompt")
        chat_history.append((briefing_prompt, None))
        # Kein Wiki im Spiel — die Quellen der vorigen Antwort sind hier hinfällig.
        yield gr.update(), chat_history, llm_history, *self._wiki_source_updates([])

        timeout = (
            float(self.briefing_cfg.get("timeout_connect", 5.0)),
            float(self.briefing_cfg.get("timeout_read", 8.0)),
        )
        hints, items = fetch_briefing_items(self.briefing_cfg, self.bot, timeout)

        for hint in hints:
            if hint:
                chat_history.append((None, hint))
        if hints:
            yield None, chat_history, llm_history, *keep

        if not items:
            chat_history.append((None, self._t("briefing_empty")))
            yield None, chat_history, llm_history, *keep
            return

        # Reihenfolge wie beim Wiki-Kontext: erst System-Messages, dann User-Turn
        inject_briefing_context(llm_history, items)
        llm_history.append({"role": "user", "content": briefing_prompt})

        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history, *keep

        yield from self._stream_reply(llm_history, chat_history)

    def _as_persona_outputs(self, updates: dict) -> tuple:
        """Resolve a named update dict into the tuple order of PERSONA_OUTPUT_KEYS."""
        unknown = set(updates) - set(PERSONA_OUTPUT_KEYS)
        if unknown:
            raise KeyError(f"Unknown persona-output keys: {sorted(unknown)}")
        return tuple(updates[key] for key in PERSONA_OUTPUT_KEYS)

    def _reset_updates(self) -> dict:
        """Baseline 'back to start screen' state; handlers override what differs."""
        return {
            "selected_persona_state": gr.update(value=""),
            "grid_group": gr.update(visible=True),
            "focus_group": gr.update(visible=False),
            "focus_img": gr.update(value=None),
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
        }

    def _persona_selected_updates(
        self,
        persona_key: str,
        persona: dict[str, Any],
        greeting_template: str,
        input_placeholder: str,
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
            focus_img=gr.update(value=self._persona_full_image_path(persona["name"])),
            focus_md=gr.update(value=focus_text),
            greeting_md=gr.update(value=greeting, visible=True),
            chatbot=gr.update(value=[], label=display_name, visible=True),
            input_box=gr.update(
                value="", visible=True, interactive=True, placeholder=input_placeholder
            ),
            send_btn=gr.update(visible=True, interactive=True),
            new_chat_btn=gr.update(visible=True),
            download_btn=gr.update(visible=True),
            briefing_btn=gr.update(visible=self.briefing_enabled),
            read_aloud_btn=gr.update(visible=self.tts_web_enabled),
            meta_state=self._build_meta(persona["name"]),
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
        return self._as_persona_outputs(updates)

    def _reset_ui_updates(self) -> tuple:
        return self._as_persona_outputs(self._reset_updates())

    def _on_persona_selected(
        self,
        key: str,
        persona_info: dict[str, dict[str, Any]],
        greeting_template: str,
        input_placeholder: str,
    ) -> tuple:
        persona = persona_info.get(key)
        if not persona:
            self.bot = None
            self.streamer = None
            return self._reset_ui_updates()

        self.bot = persona["name"]
        self.streamer = self.factory.get_streamer_for_persona(self.bot)
        return self._persona_selected_updates(
            key, persona, greeting_template, input_placeholder
        )

    def _cancel_ask_all_broadcast(self) -> None:
        """Stops the workers of a running ask-all broadcast (if any)."""
        stop = self._ask_all_stop
        if stop is not None:
            stop.set()
            self._ask_all_stop = None

    def _on_reset_to_start(self) -> tuple:
        self._cancel_ask_all_broadcast()
        # Zusätzlich zum `cancels` am Reset-Button: das cancels bricht nur den
        # asyncio-Task ab, der Kill-Switch beendet die Arbeit im Backend (#35).
        stop = self._stream_stop
        if stop is not None:
            stop.set()
        self.bot = None
        self.streamer = None
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

    def _on_model_selected(self, choice: str | None):
        """Session-Override des Modells; config.yaml bleibt unangetastet."""
        choice = (choice or "").strip()
        if not choice:
            return gr.update(value="", visible=False)
        self.cfg.override("core", {"model_name": choice})
        if self.bot:
            # Laufendes Gespräch: Streamer neu bauen (History lebt im gr.State),
            # damit auch die Cutoff-Zeile im System-Prompt zum Modell passt.
            self.streamer = self.factory.get_streamer_for_persona(self.bot)
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

    def _on_read_aloud(self, history_state: list[Message] | None):
        """Liest die letzte Antwort mit der Piper-Stimme der Persona vor."""
        last_reply = next(
            (
                m.get("content", "")
                for m in reversed(history_state or [])
                if m.get("role") == "assistant"
            ),
            "",
        )
        if not self.bot or not last_reply.strip():
            gr.Warning(self._t("tts_no_reply"))
            return gr.update(value=None, visible=False)
        try:
            # Lazy wie im Terminal: piper_tts importiert piper auf Modulebene
            from tts.piper_tts import create_wav

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                out_wav = Path(tmp.name)
            create_wav(
                last_reply,
                self.bot,
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

    def _on_show_ask_all(self) -> tuple:
        self.bot = None
        self.streamer = None
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
        return self._as_persona_outputs(updates)

    def _on_show_self_talk(self) -> tuple:
        self.bot = None
        self.streamer = None
        self.self_talk_runner = None
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
        return self._as_persona_outputs(updates)

    def _on_start_self_talk(
        self, persona_a: str | None, persona_b: str | None, start_prompt: str | None
    ) -> tuple:
        persona_a = (persona_a or "").strip()
        persona_b = (persona_b or "").strip()
        start_prompt = (start_prompt or "").strip()
        self.self_talk_runner = None

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

        self.self_talk_runner = SelfTalkRunner(
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
        self, chat_history: list[ChatPair], history_state: list[Message]
    ) -> Iterator[tuple[list[ChatPair], list[Message]]]:
        if self.self_talk_runner is None:
            return

        chat_history = list(chat_history or [])
        history_state = list(history_state or [])
        # Stop wirkt hier zwischen den Turns, nicht mitten drin: run_turn() holt
        # die Antwort in einem Zug ab, es gibt keinen Token-Strom zum Abbrechen.
        stop = self._arm_stream_stop()
        try:
            while True:
                if self._stop_requested(stop):
                    break
                persona_name, reply, should_stop, _ = self.self_talk_runner.run_turn()
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
            if self._stream_stop is stop:
                self._stream_stop = None

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

    @staticmethod
    def _format_ask_all_results(replies: dict[str, str]) -> str:
        """One markdown section per persona, separated by horizontal rules."""
        return "\n\n---\n\n".join(
            f"### {persona}\n\n{reply}" for persona, reply in replies.items()
        )

    def _on_submit_ask_all(
        self, question: str | None, current_results: str | None = None
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
        yield self._ask_all_state(
            question, self._format_ask_all_results(replies), **running
        )

        # Wiki-Lookup einmal für alle Personas; Hints nur anzeigen, Snippets
        # als geteilter System-Kontext vor die Frage jedes Broadcasts legen.
        wiki_hints, contexts = lookup_wiki_snippet(
            question,
            "ask_all",
            self.keyword_finder,
            self.wiki_mode,
            self.proxy_port,
            self.wiki_snippet_limit,
            self.wiki_timeout,
            self.max_wiki_snippets,
        )
        context_messages: list[Message] = []
        if contexts:
            inject_wiki_context(context_messages, contexts)
        wiki_status = "\n\n".join(hint for hint in wiki_hints if hint)
        # Die Quellen stehen hier bereits fest und reisen ab jetzt in jedem
        # Yield mit — genau wie wiki_status (#32a).
        sources_md = self._format_wiki_sources(contexts)
        if wiki_status or sources_md:
            yield self._ask_all_state(
                question,
                self._format_ask_all_results(replies),
                status=wiki_status,
                sources_md=sources_md,
                **running,
            )

        # Parallel: alle Personas streamen gleichzeitig in ihre Sektionen;
        # sequenzieller Fallback per ui.experimental.broadcast_parallel: false.
        if self.broadcast_parallel:
            stop = threading.Event()
            self._ask_all_stop = stop
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
                    self._format_ask_all_results(replies),
                    status=wiki_status,
                    sources_md=sources_md,
                    **running,
                )

        self._ask_all_stop = None
        # Broadcast fertig: Eingabe und Senden wieder freigeben für Folgefragen
        yield self._ask_all_state(
            question,
            self._format_ask_all_results(replies),
            status=wiki_status,
            sources_md=sources_md,
            editable=True,
        )

    def _load_failure_updates(self, message: str) -> tuple:
        updates = self._reset_updates()
        updates["load_status"] = gr.update(value=message, visible=True)
        return self._as_persona_outputs(updates)

    def _conversation_loaded_updates(
        self,
        persona_key: str,
        persona: dict[str, Any],
        meta: dict,
        messages: list[Message],
        input_placeholder: str,
    ) -> tuple:
        display_name = persona["name"].title()
        focus_text = f"### {persona['name']}\n{persona['description']}"
        chat_history = self._messages_to_chat_history(messages)

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
            download_btn=gr.update(visible=True),
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
        )
        return self._as_persona_outputs(updates)

    def _on_load_conversation(
        self,
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
        persona = persona_info.get(persona_key)

        if not persona:
            msg = self._t(
                "web_load_invalid_persona", persona_name=persona_name or "<unknown>"
            )
            return self._load_failure_updates(msg)

        self.bot = persona["name"]
        self.streamer = self.factory.get_streamer_for_persona(self.bot)

        normalized_meta = dict(meta)
        normalized_meta.setdefault("app", "web")

        return self._conversation_loaded_updates(
            persona_key,
            persona,
            normalized_meta,
            messages,
            input_placeholder,
        )

    def _on_download_conversation(
        self, messages: list[Message] | None, meta: dict | None
    ) -> tuple:
        if not (meta and meta.get("persona")) and not self.bot:
            msg = self._t("no_selection_warning")
            return gr.update(value=None, visible=False), gr.update(
                value=msg, visible=True
            )

        try:
            payload = {
                "meta": meta or self._build_meta(self.bot or ""),
                "messages": messages or [],
            }

            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
                tmp.write(
                    json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                )
                file_path = tmp.name
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

    @staticmethod
    def _find_question_for_row(chat_history: list[ChatPair] | None, row: int) -> str:
        # Live chat appends (question, None) and (None, answer) as separate rows
        # (with optional (None, wiki_hint) rows in between), while loaded
        # conversations pair (question, answer) — walking backwards from the
        # liked row to the nearest user text covers both layouts.
        if not chat_history:
            return ""
        row = min(row, len(chat_history) - 1)
        for r in range(row, -1, -1):
            pair = chat_history[r]
            if pair and pair[0] is not None:
                return str(pair[0])
        return ""

    def _on_chat_like(
        self,
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
                "persona": meta.get("persona") or self.bot or "",
                "model": meta.get("model", ""),
                "vote": "up" if evt.liked else "down",
                "question": self._find_question_for_row(chat_history, row),
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

        for key, btn in components["persona_buttons"]:
            btn.click(
                fn=partial(
                    self._on_persona_selected,
                    key=key,
                    persona_info=persona_info,
                    greeting_template=greeting_template,
                    input_placeholder=input_placeholder,
                ),
                inputs=[],
                outputs=persona_outputs,
                queue=False,
            )

        load_input.upload(
            fn=partial(
                self._on_load_conversation,
                persona_info=persona_info,
                input_placeholder=input_placeholder,
            ),
            inputs=[load_input],
            outputs=persona_outputs,
            queue=False,
        )

        # Profi-Option: .change feuert nur bei Nutzer-Interaktion, nicht beim
        # Initialwert; bewusst außerhalb der PERSONA_OUTPUT_KEYS gehalten.
        model_dropdown.change(
            fn=self._on_model_selected,
            inputs=[model_dropdown],
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
            inputs=[input_box, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        send_click_evt = send_btn.click(
            fn=self.respond_streaming_with_controls,
            inputs=[input_box, chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        # Kein `cancels`: der Kill-Switch beendet den Generator geordnet, damit
        # die Teilantwort im Verlauf bleibt.
        stop_btn.click(fn=self._on_stop_stream, outputs=stream_buttons, queue=False)

        regenerate_evt = regenerate_btn.click(
            fn=self.regenerate_with_controls,
            inputs=[chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        download_btn.click(
            fn=self._on_download_conversation,
            inputs=[history_state, meta_state],
            outputs=[download_file, save_status],
            queue=False,
        )

        briefing_evt = briefing_btn.click(
            fn=self.respond_briefing_with_controls,
            inputs=[chatbot, history_state],
            outputs=stream_outputs,
            queue=True,
        )

        # queue=True: die Piper-Synthese längerer Antworten dauert Sekunden
        read_aloud_btn.click(
            fn=self._on_read_aloud,
            inputs=[history_state],
            outputs=[tts_audio],
            queue=True,
        )

        # Binding .like() auto-enables the thumb buttons on the chatbot (#40).
        chatbot.like(
            fn=self._on_chat_like,
            inputs=[chatbot, meta_state],
            outputs=[],
            queue=False,
        )

        if ask_all_card_btn is not None:
            ask_all_card_btn.click(
                fn=self._on_show_ask_all,
                inputs=[],
                outputs=persona_outputs,
                queue=False,
            )

        if self_talk_card_btn is not None:
            self_talk_card_btn.click(
                fn=self._on_show_self_talk,
                inputs=[],
                outputs=persona_outputs,
                queue=False,
            )

        self_talk_stream_evt = self_talk_start_btn.click(
            fn=self._on_start_self_talk,
            inputs=[self_talk_persona_a, self_talk_persona_b, self_talk_prompt],
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
            inputs=[chatbot, history_state],
            outputs=[chatbot, history_state],
            queue=True,
        )

        ask_all_submit_evt = ask_all_submit.click(
            fn=self._on_submit_ask_all,
            inputs=[ask_all_question, ask_all_results],
            outputs=ask_all_outputs,
            queue=True,
        )

        ask_all_question_evt = ask_all_question.submit(
            fn=self._on_submit_ask_all,
            inputs=[ask_all_question, ask_all_results],
            outputs=ask_all_outputs,
            queue=True,
        )

        # "New conversation" bricht laufende Streams aktiv ab (#2): das Schließen
        # des Generators löst über GeneratorExit das finally in
        # YulYenStreamingProvider.stream aus, das den LLM-Stream beendet.
        new_chat_btn.click(
            fn=self._on_reset_to_start,
            inputs=[],
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
            inputs=[],
            outputs=persona_outputs,
            queue=False,
            cancels=[ask_all_submit_evt, ask_all_question_evt],
        )

    def _start_server(self, demo: gr.Blocks) -> None:
        launch_kwargs = {
            "server_name": self.web_host,
            "server_port": self.web_port,
            "show_api": False,
        }

        ui_cfg = getattr(self.cfg, "ui", None)
        if ui_cfg is not None:
            if isinstance(ui_cfg, dict):
                web_cfg = ui_cfg.get("web") or {}
            else:
                web_cfg = getattr(ui_cfg, "web", {}) or {}

            if web_cfg.get("share"):
                auth_cfg = web_cfg.get("share_auth") or {}
                username = auth_cfg.get("username") or ""
                password = auth_cfg.get("password") or ""

                if username and password:
                    launch_kwargs.update(
                        {
                            "share": True,
                            "auth": (username, password),
                        }
                    )
                else:
                    logging.warning(
                        "Gradio share disabled: credentials missing despite 'ui.web.share: true'."
                    )

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
