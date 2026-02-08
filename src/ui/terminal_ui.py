# terminal_ui.py
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style, init
from config.personas import get_all_persona_names, get_drink, _load_system_prompts
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty
from core.orchestrator import broadcast_to_ensemble

# Shared core utilities and streamer
from core.streaming_provider import (
    inject_wiki_context,
    lookup_wiki_snippet,
)
from core.utils import _greeting_text
from ui.conversation_io_terminal import load_conversation, save_conversation
from ui import self_talk


class TerminalUI:
    """
    Terminal chat—uses the same wiki logic as the WebUI:
    - Wiki hint (🕵️‍♀️ …) is shown only in the terminal (not sent to the LLM)
    - Wiki snippet (if available) is injected as system context
    - Token-by-token streaming of the LLM response stays unchanged
    """

    def __init__(
        self,
        factory,
        config,
        keyword_finder,
        wiki_snippet_limit,
        max_wiki_snippets,
        wiki_mode,
        proxy_base,
        wiki_timeout,
    ):
        self.factory = factory
        self.config = config
        self.keyword_finder = keyword_finder
        self.wiki_snippet_limit = wiki_snippet_limit
        self.max_wiki_snippets = max_wiki_snippets
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.wiki_timeout = wiki_timeout
        self.greeting = None  # set after selection
        self.bot = None  # set after selection
        self.streamer = None  # set after selection
        self.texts = config.texts
        self._t = config.t
        self.broadcast_enabled = self._is_broadcast_enabled(config)
        tts_cfg = getattr(config, "tts", {}) or {}
        self.tts_auto_wav_enabled = bool(tts_cfg.get("enabled")) and bool(
            tts_cfg.get("features", {}).get("terminal_auto_create_wav")
        )

        # Only real conversation turns (user/assistant) plus optional system contexts (wiki)
        self.history: list[dict[str, str]] = []
        self.meta: dict[str, str] = {}

    def choose_persona(self) -> None:
        """Asks the user for the desired persona and configures the streamer."""
        names = get_all_persona_names()
        print(self.texts["choose_persona"])
        for idx, name in enumerate(names, start=1):
            # Optional: show a brief description
            desc = next(p for p in _load_system_prompts() if p["name"] == name)["description"]
            persona_line = f"{idx}. {name} – {desc}"
            print(persona_line)
        while True:
            sel = input(f"{self.texts['terminal_persona_prompt']} ").strip()
            try:
                choice = int(sel) - 1
                if 0 <= choice < len(names):
                    persona_name = names[choice]
                    self._set_persona(persona_name)

                    selected_msg = self._t(
                        "terminal_persona_selected", persona_name=self.bot
                    )
                    print(selected_msg)
                    break
            except ValueError:
                pass
            print(self.texts["terminal_invalid_selection"])

    # ---------- Small UI helpers ----------
    def init_ui(self) -> None:
        init(autoreset=True)

    def print_welcome(self) -> None:
        print(self.greeting)
        print(f"{Fore.MAGENTA}{self.texts['terminal_exit_hint']}{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{self.texts['terminal_clear_hint']}{Style.RESET_ALL}")
        save_hint = self.texts.get(
            "terminal_save_hint", "('/save <pfad> zum Speichern)"
        )
        print(f"{Fore.MAGENTA}{save_hint}{Style.RESET_ALL}")

    def prompt_user(self) -> str:
        return input(
            f"{Fore.GREEN}{self.texts['terminal_user_prompt']}{Style.RESET_ALL} "
        ).strip()

    def print_bot_prefix(self, bot) -> None:
        bot_prefix = self._t("terminal_bot_prefix", persona_name=bot)
        print(f"{Fore.CYAN}{bot_prefix}{Style.RESET_ALL} ", end="", flush=True)

    def print_stream(self, text: str) -> None:
        print(text, end="", flush=True)

    def print_exit(self) -> None:
        print(self.texts["terminal_exit_message"])

    def _is_broadcast_enabled(self, config) -> bool:
        ui_cfg = getattr(config, "ui", {}) or {}

        try:
            experimental_cfg = ui_cfg.get("experimental") or {}
        except AttributeError:
            experimental_cfg = getattr(ui_cfg, "experimental", {}) or {}

        flag = experimental_cfg.get("broadcast_mode")
        return bool(flag)

    # ---------- Start menu ----------
    def _start_dialog_flow(self) -> bool:
        while True:
            print(self.texts["terminal_start_menu_title"])
            print(self.texts["terminal_start_menu_new_option"])
            print(self.texts["terminal_start_menu_load_option"])
            print(self.texts["terminal_start_menu_self_talk_option"])

            if self.broadcast_enabled:
                print(self.texts["terminal_start_menu_ask_all_option"])
                prompt = self.texts["terminal_start_menu_prompt_with_self_talk_and_ask_all"]
            else:
                prompt = self.texts["terminal_start_menu_prompt_with_self_talk"]

            choice = input(prompt + " ").strip().lower()

            if choice in {"1", "n", "new"}:
                self.history.clear()
                self.choose_persona()
                self._reset_meta()
                self.print_welcome()
                return True

            if choice in {"2", "l", "load"}:
                if self._load_conversation_from_prompt():
                    self.print_welcome()
                    return True
                continue

            if choice in {"3", "s", "self", "self-talk", "self talk"}:
                self_talk.run(self.factory, self.config)
                continue

            if self.broadcast_enabled and choice in {"4", "a", "ask", "askall", "ask-all", "ask all"}:
                self._run_ask_all_flow()
                continue
            
            if choice in {"exit", "quit"}:
                self.print_exit()
                return False

            print(f"{Fore.YELLOW}{self.texts['terminal_invalid_selection']}{Style.RESET_ALL}")

    def _set_persona(self, persona_name: str) -> None:
        # Build the streamer for the selected persona
        self.streamer = self.factory.get_streamer_for_persona(persona_name)
        self.bot = persona_name
        self.greeting = _greeting_text(self.config, self.bot)

    def _reset_meta(self) -> None:
        self.meta = {
            "created_at": datetime.now().isoformat(),
            "model": str(self.config.core.get("model_name")),
            "persona": self.bot,
            "app": "terminal",
        }

    def _load_conversation_from_prompt(self) -> bool:
        path = input(self.texts["terminal_load_path_prompt"] + " ").strip()
        if not path:
            hint = self.texts.get("terminal_load_path_required")
            if hint:
                print(f"{Fore.YELLOW}{hint}{Style.RESET_ALL}\n")
            return False

        try:
            meta, messages = load_conversation(path)
        except (OSError, ValueError) as exc:
            msg = self._t("terminal_load_failed", reason=str(exc))
            print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}\n")
            return False

        persona_name = meta.get("persona")
        if persona_name not in get_all_persona_names():
            msg = self._t(
                "terminal_load_invalid_persona", persona_name=persona_name or "<unbekannt>"
            )
            print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}\n")
            return False

        self._set_persona(persona_name)
        self.history = messages
        self.meta = meta

        success = self._t("terminal_load_success", persona_name=self.bot)
        print(f"{Fore.BLUE}{success}{Style.RESET_ALL}\n")
        self._print_loaded_history()
        return True

    def _handle_save_command(self, save_target: str) -> None:
        if not save_target:
            usage = self.texts.get("terminal_save_usage") or "/save <pfad>"
            print(f"{Fore.YELLOW}{usage}{Style.RESET_ALL}\n")
            return

        try:
            save_conversation(save_target, self.meta, self.history)
        except (OSError, ValueError) as exc:
            msg = self._t("terminal_save_failed", reason=str(exc))
            print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}\n")
            return

        success = self._t("terminal_save_success", path=save_target)
        print(f"{Fore.BLUE}{success}{Style.RESET_ALL}\n")

    def _run_ask_all_flow(self) -> None:
        if not self.broadcast_enabled:
            disabled_msg = self.texts.get("terminal_broadcast_disabled")
            print(f"{Fore.YELLOW}{disabled_msg}{Style.RESET_ALL}\n")
            return


        question = input(self.texts["terminal_askall_prompt"] + " ").strip()
        print()
        if not question:
            hint = self.texts.get("terminal_askall_missing_question")
            print(f"{Fore.YELLOW}{hint}{Style.RESET_ALL}\n")
            return

        print(f"{Fore.MAGENTA}{self.texts['terminal_askall_block_start']}{Style.RESET_ALL}")

        last_persona: str | None = None

        def _on_token(persona: str, token: str) -> None:
            nonlocal last_persona
            if persona != last_persona:
                if last_persona is not None:
                    print("\n")
                print(f"{Fore.CYAN}[{persona}]{Style.RESET_ALL} ", end="", flush=True)
                last_persona = persona
            print(token, end="", flush=True)

        broadcast_to_ensemble(self.factory, question, on_token=_on_token)

        if last_persona is not None:
            print("\n")
        print(f"{Fore.MAGENTA}{self.texts['terminal_askall_block_end']}{Style.RESET_ALL}\n")

    # ---------- Main loop ----------
    def launch(self) -> None:
        self.init_ui()
        logging.info("Launching TerminalUI")

        if not self._start_dialog_flow():
            return

        while True:
            user_input = self.prompt_user()
            logging.debug("[Terminal] User input received (%d chars)", len(user_input))
            print()  # add a small blank line after the input

            # Exit
            if user_input.lower() in ("exit", "quit"):
                self.print_exit()
                break

            # Save conversation
            if user_input.lower().startswith("/save"):
                save_target = user_input[len("/save") :].strip()
                self._handle_save_command(save_target)
                continue

            # Clear / start a new conversation
            if user_input.lower() == "clear":
                if not self._start_dialog_flow():
                    break
                continue

            # --- (1) Wiki lookup: fetch up to N matches, show hints, inject snippets if available ---
            if self.keyword_finder:
                wiki_hints, contexts = lookup_wiki_snippet(
                    user_input,
                    self.bot,
                    self.keyword_finder,
                    self.wiki_mode,
                    self.proxy_base,
                    self.wiki_snippet_limit,
                    self.wiki_timeout,
                    self.max_wiki_snippets,
                )

                # Show the hint (🕵️‍♀️ …) only to the user — do not send it to the LLM
                for wiki_hint in wiki_hints:
                    if wiki_hint:
                        print(f"{Fore.YELLOW}{wiki_hint}{Style.RESET_ALL}\n")

                # Insert the snippet as system context (guardrail plus context)
                if contexts:
                    inject_wiki_context(self.history, contexts)

            # --- (2) Append the user question to history ---
            self.history.append({"role": "user", "content": user_input})

            self._ensure_context_headroom()

            # --- (3) Stream the answer token by token ---
            self.print_bot_prefix(self.bot)
            reply = ""
            for token in self.streamer.stream(messages=self.history):
                reply += token
                self.print_stream(token)

            # --- (4) Add the answer to history with a clean finish ---
            logging.info(f"[Terminal] {self.bot}: {reply}")

            self.history.append({"role": "assistant", "content": reply})
            self._maybe_create_tts_wav(reply)
            # Always ensure two trailing blank lines after the answer:
            # (If streaming already emitted \n, add only the missing ones.)
            trailing_nl = len(reply) - len(reply.rstrip("\n"))
            for _ in range(max(0, 2 - trailing_nl)):
                print()

    def _maybe_create_tts_wav(self, reply: str) -> None:
        if not self.tts_auto_wav_enabled or not reply.strip() or not self.bot:
            return

        try:
            from tts.piper_tts import synthesize

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            persona = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in self.bot)
            out_wav = Path("out") / f"{timestamp}_{persona}.wav"
            synthesize(reply, self.bot, voices_dir=Path("voices"), out_wav=out_wav)
            logging.info("[Terminal] TTS wav created: %s", out_wav)
        except Exception as exc:
            logging.warning("[Terminal] Could not create TTS wav file: %s", exc)

    def _ensure_context_headroom(self) -> None:
        """Trims the history when the context limit is nearly reached."""

        if not self.streamer:
            return

        persona_options = getattr(self.streamer, "persona_options", {}) or {}

        if not context_near_limit(self.history, persona_options):
            return

        drink = get_drink(self.bot)
        wait_msg = self._t("context_wait_message", persona_name=self.bot, drink=drink)
        print(wait_msg)

        num_ctx = persona_options.get("num_ctx")
        if not num_ctx:
            logging.info("TerminalUI: Context limit reached, but 'num_ctx' is not set.")
            return

        try:
            ctx_limit = int(num_ctx)
        except (TypeError, ValueError):
            logging.warning(
                "TerminalUI: Invalid 'num_ctx' value (%r); conversation will not be trimmed.",
                num_ctx,
            )
            return

        original_length = len(self.history)
        trimmed_history = karl_prepare_quick_and_dirty(self.history, ctx_limit)
        removed = original_length - len(trimmed_history)
        self.history = trimmed_history

        if removed > 0:
            logging.info(
                "TerminalUI: Removed %s older messages to free up context.",
                removed,
            )
            notice = self.texts["terminal_context_trim_notice"]
            print(f"{Fore.YELLOW}{notice}{Style.RESET_ALL}")

    def _print_loaded_history(self) -> None:
        if not self.history:
            return

        header = self.texts.get("terminal_loaded_history_header")
        if header:
            print(f"{Fore.MAGENTA}{header}{Style.RESET_ALL}")

        role_labels = {
            "user": f"{Fore.GREEN}{self.texts['terminal_user_prompt']}{Style.RESET_ALL}",
            "assistant": f"{Fore.CYAN}{self._t('terminal_bot_prefix', persona_name=self.bot)}{Style.RESET_ALL}",
            "system": f"{Fore.MAGENTA}[system]{Style.RESET_ALL}",
        }

        for msg in self.history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            prefix = role_labels.get(role, f"{Fore.YELLOW}[{role}]{Style.RESET_ALL}")

            lines = content.splitlines() or [""]
            for idx, line in enumerate(lines):
                if idx == 0:
                    print(f"{prefix} {line}")
                else:
                    print(f"    {line}")

        print()
