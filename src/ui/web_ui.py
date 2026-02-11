import json
import logging
import tempfile
from datetime import datetime
from functools import partial

import gradio as gr
from config.personas import get_all_persona_names, get_drink, _load_system_prompts
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty
from core.streaming_provider import inject_wiki_context, lookup_wiki_snippet
from ui.conversation_io_terminal import load_conversation
from ui.self_talk import SelfTalkRunner
from ui.webui_layout import build_ui


class WebUI:
    """
    Web chat interface built with Gradio.
    Provides a graphical persona selector (with avatar) and a live chat history in the browser.
    Wiki hints and snippets are handled like the terminal UI (hint only visible, snippet as context).
    Responses from the AI model are streamed token by token and updated directly in the UI.
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
        web_host,
        web_port,
        wiki_timeout,
    ):
        self.streamer = None  # assigned later
        self.keyword_finder = keyword_finder
        self.cfg = config
        self.factory = factory
        self.wiki_snippet_limit = wiki_snippet_limit
        self.max_wiki_snippets = max_wiki_snippets
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout
        self.bot = None  # assigned later
        self.texts = getattr(config, "texts", {}) or {}
        self._t = getattr(config, "t", getattr(self.texts, "format", None))
        self.broadcast_enabled = self._is_broadcast_enabled()
        self.ask_all_placeholder = ""
        self.self_talk_runner = None
        self.self_talk_prompt_placeholder = ""
        if self._t is None:
            self._t = lambda key, **kwargs: key

    def _is_broadcast_enabled(self) -> bool:
        ui_cfg = getattr(self.cfg, "ui", {}) or {}

        try:
            experimental_cfg = ui_cfg.get("experimental") or {}
        except AttributeError:
            experimental_cfg = getattr(ui_cfg, "experimental", {}) or {}

        flag = experimental_cfg.get("broadcast_mode")
        return bool(flag)

    def _reset_conversation_state(self):
        return []

    def _reset_meta_state(self):
        return {}

    def _build_meta(self, persona_name: str) -> dict:
        return {
            "created_at": datetime.now().isoformat(),
            "model": str(self.cfg.core.get("model_name")),
            "persona": persona_name,
            "app": "web",
        }

    def _messages_to_chat_history(self, messages):
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

    def _persona_thumbnail_path(self, persona_name):
        ensemble = getattr(self.cfg, "ensemble", None)
        if not ensemble:
            raise RuntimeError("No persona ensemble configured for the web UI.")
        return f"ensembles/{ensemble}/static/personas/{persona_name}/thumb.webp"

    def _persona_full_image_path(self, persona_name):
        ensemble = getattr(self.cfg, "ensemble", None)
        if not ensemble:
            raise RuntimeError("No persona ensemble configured for the web UI.")
        return f"ensembles/{ensemble}/static/personas/{persona_name}/full.webp"

    def _handle_context_warning(self, llm_history, chat_history):

        if not context_near_limit(llm_history, self.streamer.persona_options):
            return False

        drink = get_drink(self.bot)
        warn = self._t("context_wait_message", persona_name=self.bot, drink=drink)

        chat_history.append((None, warn))

        persona_options = getattr(self.streamer, "persona_options", {}) or {}

        num_ctx_value = persona_options.get("num_ctx")

        ctx_limit = None
        if num_ctx_value is not None:
            try:
                ctx_limit = int(num_ctx_value)
            except (TypeError, ValueError):
                logging.warning(
                    "Invalid 'num_ctx' value for persona %r: %r",
                    self.bot,
                    num_ctx_value,
                )

        if ctx_limit and ctx_limit > 0:
            llm_history[:] = karl_prepare_quick_and_dirty(llm_history, ctx_limit)
        else:
            logging.warning(
                "Skipping 'karl_prepare_quick_and_dirty' for persona %r: num_ctx=%r",
                self.bot,
                num_ctx_value,
            )

        return True

    # Stream the response (UI updates continuously)
    def _stream_reply(self, message_history, chat_history):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            yield None, chat_history + [(None, reply)], message_history

        # Finalize: add the completed reply to the history
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history

    def respond_streaming(
        self, user_input, chat_history, history_state
    ):

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
            self.proxy_base,
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
            (txt, cb, state) for (txt, cb, state) in self._stream_reply(llm_history, chat_history)
        )

    def _persona_selected_updates(
        self,
        persona_key,
        persona,
        greeting_template,
        model_name,
        input_placeholder,
    ):
        display_name = persona["name"].title()
        greeting = greeting_template.format(
            persona_name=display_name, model_name=model_name
        )
        focus_text = f"### {persona['name']}\n{persona['description']}"
        meta = self._build_meta(persona["name"])

        return (
            gr.update(value=persona_key),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=self._persona_full_image_path(persona["name"])),
            gr.update(value=focus_text),
            gr.update(value=greeting, visible=True),
            gr.update(value=[], label=display_name, visible=True),
            gr.update(value="", visible=True, interactive=True, placeholder=input_placeholder),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(value=None, visible=False),
            gr.update(value="", visible=False),
            self._reset_conversation_state(),
            meta,
            gr.update(visible=False),
            gr.update(value=[], visible=False),
            gr.update(value="", visible=False, interactive=True, placeholder=self.ask_all_placeholder),
            gr.update(visible=False, interactive=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True),
            gr.update(value="", visible=False, interactive=True, placeholder=self.self_talk_prompt_placeholder),
            gr.update(visible=False, interactive=True),
        )

    def _reset_ui_updates(self):
        return (
            gr.update(value=""),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(value=None),
            gr.update(value=""),
            gr.update(value="", visible=False),
            gr.update(value=[], label="", visible=False),
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False, interactive=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=None, visible=False),
            gr.update(value="", visible=False),
            self._reset_conversation_state(),
            self._reset_meta_state(),
            gr.update(visible=False),
            gr.update(value=[], visible=False),
            gr.update(value=self.ask_all_placeholder, visible=False, interactive=True),
            gr.update(visible=False, interactive=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True),
            gr.update(value="", visible=False, interactive=True, placeholder=self.self_talk_prompt_placeholder),
            gr.update(visible=False, interactive=True),
        )

    def _on_persona_selected(
        self, key, persona_info, greeting_template, model_name, input_placeholder
    ):
        persona = persona_info.get(key)
        if not persona:
            self.bot = None
            self.streamer = None
            return self._reset_ui_updates()

        self.bot = persona["name"]
        self.streamer = self.factory.get_streamer_for_persona(self.bot)
        return self._persona_selected_updates(
            key, persona, greeting_template, model_name, input_placeholder
        )

    def _on_reset_to_start(self):
        self.bot = None
        self.streamer = None
        return self._reset_ui_updates()

    def _on_show_ask_all(self):
        self.bot = None
        self.streamer = None
        return (
            gr.update(value=""),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=None),
            gr.update(value=""),
            gr.update(value="", visible=False),
            gr.update(value=[], label="", visible=False),
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False, interactive=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=None, visible=False),
            gr.update(value="", visible=False),
            self._reset_conversation_state(),
            self._reset_meta_state(),
            gr.update(visible=True),
            gr.update(value=[], visible=False),
            gr.update(value="", visible=True, interactive=True, placeholder=self.ask_all_placeholder),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True),
            gr.update(value="", visible=False, interactive=True, placeholder=self.self_talk_prompt_placeholder),
            gr.update(visible=False, interactive=True),
        )

    def _on_show_self_talk(self):
        self.bot = None
        self.streamer = None
        self.self_talk_runner = None
        base = list(self._reset_ui_updates())
        base[15] = gr.update(visible=False)  # ask_all_group
        base[21] = gr.update(value="", visible=False)  # load_status
        base[22] = gr.update(visible=True)  # self_talk_group
        base[23] = gr.update(value="", visible=False)  # self_talk_status
        base[24] = gr.update(value=None, interactive=True)  # persona_a
        base[25] = gr.update(value=None, interactive=True)  # persona_b
        base[26] = gr.update(value="", visible=True, interactive=True, placeholder=self.self_talk_prompt_placeholder)
        base[27] = gr.update(visible=True, interactive=True)
        return tuple(base)

    def _on_start_self_talk(self, persona_a, persona_b, start_prompt):
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
        title = self._t("self_talk_chat_label", persona_a=persona_a, persona_b=persona_b)
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

    def _run_self_talk_stream(self, chat_history, history_state):
        if self.self_talk_runner is None:
            return

        chat_history = list(chat_history or [])
        history_state = list(history_state or [])
        while True:
            persona_name, reply, should_stop, _ = self.self_talk_runner.run_turn()
            shown_reply = f"{persona_name}: {reply}"
            progressive = ""
            for token in shown_reply:
                progressive += token
                yield chat_history + [(None, progressive)], history_state
            chat_history.append((None, shown_reply))
            history_state.append({"role": "assistant", "content": shown_reply})
            yield chat_history, history_state
            if should_stop:
                break

    def _on_submit_ask_all(self, question, current_rows=None):
        question = (question or "").strip()
        existing_rows = self._normalize_ask_all_rows(current_rows)

        if not self.broadcast_enabled:
            warning = self._t("ask_all_disabled")
            yield (
                gr.update(value=question, visible=True, interactive=True),
                gr.update(value=warning, visible=True),
                gr.update(value=existing_rows, visible=bool(existing_rows)),
                gr.update(visible=True, interactive=False),
                gr.update(visible=True),
            )
            return

        if not question:
            warn = self._t("empty_question")
            yield (
                gr.update(value="", visible=True, interactive=True, placeholder=self.ask_all_placeholder),
                gr.update(value=warn, visible=True),
                gr.update(value=existing_rows, visible=bool(existing_rows)),
                gr.update(visible=True, interactive=True),
                gr.update(visible=True),
            )
            return

        table_rows: list[list[str]] = []
        yield (
            gr.update(value=question, interactive=False, visible=True),
            gr.update(value="", visible=False),
            gr.update(value=table_rows, visible=True),
            gr.update(visible=False, interactive=False),
            gr.update(visible=True),
        )

        for persona in get_all_persona_names():
            streamer = self.factory.get_streamer_for_persona(persona)
            reply_parts: list[str] = []
            for token in streamer.stream(messages=[{"role": "user", "content": question}]):
                reply_parts.append(token)
            table_rows.append([persona, "".join(reply_parts).strip()])
            yield (
                gr.update(value=question, interactive=False, visible=True),
                gr.update(value="", visible=False),
                gr.update(value=table_rows, visible=True),
                gr.update(visible=False, interactive=False),
                gr.update(visible=True),
            )

    @staticmethod
    def _normalize_ask_all_rows(current_rows):
        if current_rows is None:
            return []
        if isinstance(current_rows, list):
            return current_rows
        if hasattr(current_rows, "values"):
            try:
                return current_rows.values.tolist()
            except Exception:
                return list(current_rows)
        return list(current_rows)

    def _load_failure_updates(self, message):
        base = list(self._reset_ui_updates())
        base[21] = gr.update(value=message, visible=True)
        return tuple(base)

    def _conversation_loaded_updates(
        self,
        persona_key,
        persona,
        meta,
        messages,
        input_placeholder,
    ):
        display_name = persona["name"].title()
        focus_text = f"### {persona['name']}\n{persona['description']}"
        chat_history = self._messages_to_chat_history(messages)

        greeting = self._t("web_load_status_success", persona_name=display_name)

        return (
            gr.update(value=persona_key),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=self._persona_full_image_path(persona["name"])),
            gr.update(value=focus_text),
            gr.update(value=greeting, visible=True),
            gr.update(value=chat_history, label=display_name, visible=True),
            gr.update(value="", visible=True, interactive=True, placeholder=input_placeholder),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(value=None, visible=False),
            gr.update(value="", visible=False),
            messages,
            meta,
            gr.update(visible=False),
            gr.update(value=[], visible=False),
            gr.update(value="", visible=False, interactive=True, placeholder=self.ask_all_placeholder),
            gr.update(visible=False, interactive=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value=greeting, visible=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True),
            gr.update(value="", visible=False, interactive=True, placeholder=self.self_talk_prompt_placeholder),
            gr.update(visible=False, interactive=True),
        )

    def _on_load_conversation(self, upload_path, persona_info, input_placeholder):
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
            msg = self._t("web_load_invalid_persona", persona_name=persona_name or "<unknown>")
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

    def _on_download_conversation(self, messages, meta):
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
                tmp.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
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
        self, components, persona_info, model_name, greeting_template, input_placeholder
    ):
        selected_persona_state = components["selected_persona_state"]
        grid_group = components["grid_group"]
        focus_group = components["focus_group"]
        focus_img = components["focus_img"]
        focus_md = components["focus_md"]
        greeting_md = components["greeting_md"]
        chatbot = components["chatbot"]
        input_box = components["input_box"]
        send_btn = components["send_btn"]
        new_chat_btn = components["new_chat_btn"]
        download_btn = components["download_btn"]
        download_file = components["download_file"]
        save_status = components["save_status"]
        history_state = components["history_state"]
        meta_state = components["meta_state"]
        ask_all_btn = components["ask_all_btn"]
        ask_all_group = components["ask_all_group"]
        ask_all_results = components["ask_all_results"]
        ask_all_question = components["ask_all_question"]
        ask_all_submit = components["ask_all_submit"]
        ask_all_new_chat = components["ask_all_new_chat"]
        ask_all_status = components["ask_all_status"]
        ask_all_card_btn = components["ask_all_card_btn"]
        self_talk_card_btn = components["self_talk_card_btn"]
        self_talk_group = components["self_talk_group"]
        self_talk_status = components["self_talk_status"]
        self_talk_persona_a = components["self_talk_persona_a"]
        self_talk_persona_b = components["self_talk_persona_b"]
        self_talk_prompt = components["self_talk_prompt"]
        self_talk_start_btn = components["self_talk_start_btn"]
        load_input = components["load_input"]
        load_status = components["load_status"]

        persona_outputs = [
            selected_persona_state,
            grid_group,
            focus_group,
            focus_img,
            focus_md,
            greeting_md,
            chatbot,
            input_box,
            send_btn,
            new_chat_btn,
            download_btn,
            download_file,
            save_status,
            history_state,
            meta_state,
            ask_all_group,
            ask_all_results,
            ask_all_question,
            ask_all_submit,
            ask_all_new_chat,
            ask_all_status,
            load_status,
            self_talk_group,
            self_talk_status,
            self_talk_persona_a,
            self_talk_persona_b,
            self_talk_prompt,
            self_talk_start_btn,
        ]

        for key, btn in components["persona_buttons"]:
            btn.click(
                fn=partial(
                    self._on_persona_selected,
                    key=key,
                    persona_info=persona_info,
                    greeting_template=greeting_template,
                    model_name=model_name,
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

        input_box.submit(
            fn=self.respond_streaming,
            inputs=[input_box, chatbot, history_state],
            outputs=[input_box, chatbot, history_state],
            queue=True,
        )

        send_btn.click(
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

        new_chat_btn.click(
            fn=self._on_reset_to_start,
            inputs=[],
            outputs=persona_outputs,
            queue=False,
        )

        if ask_all_btn is not None:
            ask_all_btn.click(
                fn=self._on_show_ask_all,
                inputs=[],
                outputs=persona_outputs,
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

        self_talk_start_btn.click(
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

        ask_all_submit.click(
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

        ask_all_question.submit(
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

        ask_all_new_chat.click(
            fn=self._on_reset_to_start,
            inputs=[],
            outputs=persona_outputs,
            queue=False,
        )

    def _start_server(self, demo):
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

    def launch(self):
        ui = self.texts
        model_name = self.cfg.core.get("model_name")
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
        self_talk_description = ui.get("self_talk_description", "Zwei Personas sprechen automatisch.")
        self_talk_persona_a_label = ui.get("self_talk_persona_a_label", "Persona A")
        self_talk_persona_b_label = ui.get("self_talk_persona_b_label", "Persona B")
        self_talk_prompt_label = ui.get("self_talk_prompt_label", "Start-Prompt")
        self_talk_start_label = ui.get("self_talk_start_label", "AI Dialog starten")
        self_talk_prompt_placeholder = ui.get("self_talk_prompt_placeholder", "Gib den Start-Prompt ein …")
        save_button_label = ui.get(
            "web_save_button", "Gespräch herunterladen (JSON)"
        )

        self.ask_all_placeholder = ask_all_input_placeholder
        self.self_talk_prompt_placeholder = self_talk_prompt_placeholder

        persona_info = {p["name"].lower(): p for p in _load_system_prompts()}

        demo, components =  build_ui(
            persona_thumbnail_path_fn=self._persona_thumbnail_path,
            persona_info=persona_info,
            broadcast_enabled=self.broadcast_enabled,
            project_title=project_title,
            choose_persona_txt=choose_persona_txt,
            persona_btn_suffix=persona_btn_suffix,
            input_placeholder=input_placeholder,
            new_chat_label=new_chat_label,
            broadcast_table_persona_label=ui.get("broadcast_table_persona_header", "Persona"),
            broadcast_table_answer_label= ui.get("broadcast_table_answer_header", "Answer"),
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
        )
        # Gradio 4.x requires events to be bound within a Blocks context.
        # Reopening the demo as a context lets us keep the existing structure
        # while still registering the events correctly.
        with demo:
            self._bind_events(
                components,
                persona_info,
                model_name,
                greeting_template,
                input_placeholder,
            )
        self._start_server(demo)
