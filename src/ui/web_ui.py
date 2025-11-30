import logging
from functools import partial

import gradio as gr
from config.personas import get_drink, _load_system_prompts
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty
from core.orchestrator import broadcast_to_ensemble
from core.streaming_provider import inject_wiki_context, lookup_wiki_snippet


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
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout
        self.bot = None  # assigned later
        self.texts = getattr(config, "texts", {}) or {}
        self._t = getattr(config, "t", getattr(self.texts, "format", None))
        if self._t is None:
            self._t = lambda key, **kwargs: key

    def _reset_conversation_state(self):
        return []

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
        self, user_input, chat_history, history_state, broadcast_mode=False
    ):

        # Safety check: persona not selected yet → UI should prevent this, but we double-check
        if not self.bot:
            yield "", chat_history, history_state, gr.update(visible=False, value=[])
            return

        if broadcast_mode:
            chat_history.append((user_input, None))
            yield "", chat_history, history_state, gr.update(visible=True, value=[])

            results = broadcast_to_ensemble(self.factory, user_input)
            table_rows = [[item["persona"], item["reply"]] for item in results]

            assistant_reply = "\n\n".join(
                f"**{item['persona']}**: {item['reply']}" for item in results
            )
            chat_history[-1] = (user_input, assistant_reply)

            yield "", chat_history, history_state, gr.update(
                visible=True, value=table_rows
            )
            return

        # 1) Maintain a dedicated LLM history without UI hints (and compress if needed)
        llm_history = list(history_state or [])

        # 2) Clear the input field and show the user message in the chat window
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append((user_input, None))
        yield "", chat_history, llm_history, gr.update(visible=False, value=[])

        # 3) Wiki hint and snippet (top hit)
        wiki_hint, title, snippet = lookup_wiki_snippet(
            user_input,
            self.bot,
            self.keyword_finder,
            self.wiki_mode,
            self.proxy_base,
            self.wiki_snippet_limit,
            self.wiki_timeout,
        )

        if wiki_hint:
            # Display the UI hint (do not add it to the LLM context window)
            chat_history.append((None, wiki_hint))
            yield None, chat_history, llm_history, gr.update(visible=False, value=[])

        # 4) Optional: inject wiki context
        if snippet:
            inject_wiki_context(llm_history, title, snippet)

        # 5) Send the user question to the LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Compress the context if needed and record that in chat history
        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history, gr.update(visible=False, value=[])

        # 7) Stream the answer
        yield from (
            (txt, cb, state, gr.update(visible=False, value=[]))
            for (txt, cb, state) in self._stream_reply(llm_history, chat_history)
        )

    def _build_ui(
        self,
        project_title,
        choose_persona_txt,
        persona_info,
        persona_btn_suffix,
        input_placeholder,
        new_chat_label,
        broadcast_toggle_label,
        broadcast_table_persona_label,
        broadcast_table_answer_label,
    ):
        with gr.Blocks() as demo:
            selected_persona_state = gr.Textbox(value="", visible=False)

            gr.HTML(
                """
                <style>
                .persona-row { gap:24px; }
                .persona-card {
                    border:1px solid #e3e7ed;
                    border-radius:10px;
                    padding:12px;
                    text-align:center;
                }
                .persona-card img {
                    max-width: 100%;
                    height: auto;
                    display:inline-block;
                }
                .persona-card .name { font-weight:600; margin:6px 0 4px; font-size:1.1rem; }
                .persona-card .desc { font-size:0.9rem; margin-bottom:8px; }
                </style>
            """
            )
            gr.Markdown(f"# {project_title}")

            with gr.Group(visible=True) as grid_group:
                gr.Markdown(choose_persona_txt)
                with gr.Row(elem_classes="persona-row", equal_height=True):
                    persona_buttons = []
                    for key, p in persona_info.items():
                        with gr.Column(scale=1, min_width=220):
                            with gr.Group(elem_classes="persona-card"):
                                gr.Image(
                                    self._persona_thumbnail_path(p["name"]),
                                    show_label=False,
                                    container=False,
                                    elem_classes="persona-img",
                                )
                                gr.Markdown(
                                    f"<div class='name'>{p['name']}</div>"
                                    f"<div class='desc'>{p['description']}</div>"
                                )
                                btn = gr.Button(
                                    f"{p['name']}{persona_btn_suffix}",
                                    variant="secondary",
                                )
                                persona_buttons.append((key, btn))

            with gr.Group(visible=False) as focus_group:
                with gr.Row():
                    with gr.Column(scale=1):
                        focus_img = gr.Image(show_label=False, container=False)
                    with gr.Column(scale=3):
                        focus_md = gr.Markdown("")
                gr.Markdown("---")

            greeting_md = gr.Markdown("", visible=False)
            chatbot = gr.Chatbot(label="", visible=False)
            broadcast_toggle = gr.Checkbox(
                label=broadcast_toggle_label, visible=False, value=False
            )
            broadcast_table = gr.Dataframe(
                headers=[broadcast_table_persona_label, broadcast_table_answer_label],
                visible=False,
                datatype=["str", "str"],
                wrap=True,
            )
            txt = gr.Textbox(
                show_label=False,
                placeholder=input_placeholder,
                visible=False,
                interactive=False,
            )
            clear = gr.Button(new_chat_label, visible=False)
            history_state = gr.State(self._reset_conversation_state())

        components = {
            "demo": demo,
            "selected_persona_state": selected_persona_state,
            "grid_group": grid_group,
            "focus_group": focus_group,
            "focus_img": focus_img,
            "focus_md": focus_md,
            "greeting_md": greeting_md,
            "chatbot": chatbot,
            "broadcast_toggle": broadcast_toggle,
            "broadcast_table": broadcast_table,
            "txt": txt,
            "clear": clear,
            "persona_buttons": persona_buttons,
            "history_state": history_state,
        }
        return demo, components

    def _persona_selected_updates(
        self, persona_key, persona, greeting_template, model_name, input_placeholder
    ):
        display_name = persona["name"].title()
        greeting = greeting_template.format(
            persona_name=display_name, model_name=model_name
        )
        focus_text = f"### {persona['name']}\n{persona['description']}"

        return (
            gr.update(value=persona_key),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=self._persona_full_image_path(persona["name"])),
            gr.update(value=focus_text),
            gr.update(value=greeting, visible=True),
            gr.update(value=[], label=display_name, visible=True),
            gr.update(value=False, visible=True),
            gr.update(value=[], visible=False),
            gr.update(
                value="", visible=True, interactive=True, placeholder=input_placeholder
            ),
            gr.update(visible=True),
            self._reset_conversation_state(),
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
            gr.update(value=False, visible=False),
            gr.update(value=[], visible=False),
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False),
            self._reset_conversation_state(),
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
        broadcast_toggle = components["broadcast_toggle"]
        broadcast_table = components["broadcast_table"]
        txt = components["txt"]
        clear = components["clear"]
        history_state = components["history_state"]

        persona_outputs = [
            selected_persona_state,
            grid_group,
            focus_group,
            focus_img,
            focus_md,
            greeting_md,
            chatbot,
            broadcast_toggle,
            broadcast_table,
            txt,
            clear,
            history_state,
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

        txt.submit(
            fn=self.respond_streaming,
            inputs=[txt, chatbot, history_state, broadcast_toggle],
            outputs=[txt, chatbot, history_state, broadcast_table],
            queue=True,
        )

        clear.click(
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
        input_placeholder = ui.get("input_placeholder")
        greeting_template = ui.get("greeting")
        persona_btn_suffix = ui.get("persona_button_suffix")

        persona_info = {p["name"].lower(): p for p in _load_system_prompts()}

        demo, components = self._build_ui(
            project_title,
            choose_persona_txt,
            persona_info,
            persona_btn_suffix,
            input_placeholder,
            new_chat_label,
            ui.get(
                "broadcast_toggle_label", "Broadcast mode (all personas)"
            ),
            ui.get("broadcast_table_persona_header", "Persona"),
            ui.get("broadcast_table_answer_header", "Answer"),
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
