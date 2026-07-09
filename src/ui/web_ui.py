from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

import gradio as gr
import requests
from briefing.feeds import fetch_briefing_items, inject_briefing_context
from config.personas import _load_system_prompts, get_all_persona_names, get_drink
from core.context_utils import context_near_limit, shrink_history_for_context
from core.orchestrator import iter_broadcast_events, iter_broadcast_events_parallel
from core.system_checks import fetch_model_names
from core.utils import is_broadcast_enabled, is_broadcast_parallel
from stt.whisper_stt import is_stt_available, transcribe_wav
from ui.conversation_io_terminal import load_conversation
from ui.self_talk import SelfTalkRunner
from ui.webui_layout import build_ui
from wiki.lookup import inject_wiki_context, lookup_wiki_snippet

if TYPE_CHECKING:
    from config.config_singleton import Config
    from core.factory import AppFactory
    from wiki.spacy_keyword_finder import SpacyKeywordFinder

# One chatbot entry: (user_text, bot_text) — either side may be None.
ChatPair = tuple[str | None, str | None]
Message = dict[str, str]

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
        if self.stt_cfg.get("enabled") and not self.stt_available:
            logging.info(
                "STT aktiviert, aber faster-whisper ist nicht installiert — "
                "Mikrofon bleibt ausgeblendet (pip install faster-whisper)."
            )
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

    # Stream the response (UI updates continuously)
    def _stream_reply(
        self, message_history: list[Message], chat_history: list[ChatPair]
    ) -> Iterator[tuple[None, list[ChatPair], list[Message]]]:
        # Gedrosselt wie in der Ask-All-Ansicht: nicht jedes Token einzeln über
        # den Socket schicken; last_flush=0.0 lässt den ersten Chunk sofort durch.
        reply = ""
        last_flush = 0.0
        for token in self.streamer.stream(messages=message_history):
            reply += token
            now = time.monotonic()
            if now - last_flush >= 0.1:
                last_flush = now
                yield None, chat_history + [(None, reply)], message_history

        # Finalize: add the completed reply to the history
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history

    def respond_streaming(
        self,
        user_input: str,
        chat_history: list[ChatPair],
        history_state: list[Message] | None,
    ) -> Iterator[tuple[str | None, list[ChatPair], list[Message]]]:

        # Safety check: persona not selected yet → UI should prevent this, but we double-check
        if not self.bot:
            yield "", chat_history, history_state
            return

        # 1) Maintain a dedicated LLM history without UI hints (and compress if needed)
        llm_history = list(history_state or [])

        # 2) Clear the input field and show the user message in the chat window
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append((user_input, None))
        yield "", chat_history, llm_history

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

        if wiki_hints:
            # Display the UI hints (do not add them to the LLM context window)
            for wiki_hint in wiki_hints:
                if wiki_hint:
                    chat_history.append((None, wiki_hint))
            yield None, chat_history, llm_history

        # 4) Optional: inject wiki context
        if contexts:
            inject_wiki_context(llm_history, contexts)

        # 5) Send the user question to the LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Compress the context if needed and record that in chat history
        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history

        # 7) Stream the answer
        yield from (
            (txt, cb, state)
            for (txt, cb, state) in self._stream_reply(llm_history, chat_history)
        )

    def respond_briefing(
        self, chat_history: list[ChatPair], history_state: list[Message] | None
    ) -> Iterator[tuple[Any, list[ChatPair], list[Message]]]:
        """Wie respond_streaming, nur mit RSS-Feeds statt Wiki als Kontext."""
        if not self.bot or not self.briefing_enabled:
            yield gr.update(), chat_history, history_state
            return

        llm_history = list(history_state or [])
        briefing_prompt = self._t("briefing_user_prompt")
        chat_history.append((briefing_prompt, None))
        yield gr.update(), chat_history, llm_history

        timeout = (
            float(self.briefing_cfg.get("timeout_connect", 5.0)),
            float(self.briefing_cfg.get("timeout_read", 8.0)),
        )
        hints, items = fetch_briefing_items(self.briefing_cfg, self.bot, timeout)

        for hint in hints:
            if hint:
                chat_history.append((None, hint))
        if hints:
            yield None, chat_history, llm_history

        if not items:
            chat_history.append((None, self._t("briefing_empty")))
            yield None, chat_history, llm_history
            return

        # Reihenfolge wie beim Wiki-Kontext: erst System-Messages, dann User-Turn
        inject_briefing_context(llm_history, items)
        llm_history.append({"role": "user", "content": briefing_prompt})

        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history

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
            meta_state=self._build_meta(persona["name"]),
            ask_all_question=gr.update(
                value="",
                visible=False,
                interactive=True,
                placeholder=self.ask_all_placeholder,
            ),
            mic_audio=gr.update(value=None, visible=self.stt_available),
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
        while True:
            persona_name, reply, should_stop, _ = self.self_talk_runner.run_turn()
            shown_reply = f"{persona_name}: {reply}"
            # run_turn() liefert die Antwort bereits komplett; die Zeichen-Schleife
            # war reine Schreibmaschinen-Animation (ein Websocket-Frame pro
            # Zeichen). Mit der 0.1-s-Drossel erscheint die Nachricht in wenigen
            # großen Updates statt in len(reply) Frames.
            progressive = ""
            last_flush = 0.0
            for token in shown_reply:
                progressive += token
                now = time.monotonic()
                if now - last_flush >= 0.1:
                    last_flush = now
                    yield chat_history + [(None, progressive)], history_state
            chat_history.append((None, shown_reply))
            history_state.append({"role": "assistant", "content": shown_reply})
            yield chat_history, history_state
            if should_stop:
                break

    def _ask_all_state(
        self,
        question: str,
        results_md: str,
        *,
        editable: bool,
        submit_visible: bool = True,
        submit_interactive: bool = True,
        status: str = "",
    ) -> tuple:
        """Builds the 5-tuple of updates every Ask-All yield consists of."""
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
        if wiki_status:
            yield self._ask_all_state(
                question,
                self._format_ask_all_results(replies),
                status=wiki_status,
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
            if event["type"] == "done" or now - last_flush >= 0.1:
                last_flush = now
                yield self._ask_all_state(
                    question,
                    self._format_ask_all_results(replies),
                    status=wiki_status,
                    **running,
                )

        self._ask_all_stop = None
        # Broadcast fertig: Eingabe und Senden wieder freigeben für Folgefragen
        yield self._ask_all_state(
            question,
            self._format_ask_all_results(replies),
            status=wiki_status,
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
        ask_all_status = components["ask_all_status"]
        ask_all_card_btn = components["ask_all_card_btn"]
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

        input_submit_evt = input_box.submit(
            fn=self.respond_streaming,
            inputs=[input_box, chatbot, history_state],
            outputs=[input_box, chatbot, history_state],
            queue=True,
        )

        send_click_evt = send_btn.click(
            fn=self.respond_streaming,
            inputs=[input_box, chatbot, history_state],
            outputs=[input_box, chatbot, history_state],
            queue=True,
        )

        download_btn.click(
            fn=self._on_download_conversation,
            inputs=[history_state, meta_state],
            outputs=[download_file, save_status],
            queue=False,
        )

        briefing_evt = briefing_btn.click(
            fn=self.respond_briefing,
            inputs=[chatbot, history_state],
            outputs=[input_box, chatbot, history_state],
            queue=True,
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
            outputs=[
                ask_all_question,
                ask_all_status,
                ask_all_results,
                ask_all_submit,
                ask_all_new_chat,
            ],
            queue=True,
        )

        ask_all_question_evt = ask_all_question.submit(
            fn=self._on_submit_ask_all,
            inputs=[ask_all_question, ask_all_results],
            outputs=[
                ask_all_question,
                ask_all_status,
                ask_all_results,
                ask_all_submit,
                ask_all_new_chat,
            ],
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
