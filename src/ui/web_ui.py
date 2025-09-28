import gradio as gr
import logging
from functools import partial
from config.personas import system_prompts, get_drink
from core.streaming_provider import lookup_wiki_snippet, inject_wiki_context
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty

class WebUI:
    """
    Web-Chat-Oberfläche mit Gradio.
    Bietet grafische Persona-Auswahl (mit Avatar) und einen laufenden Chatverlauf im Browser.
    Wiki-Hinweise und -Snippets werden analog zur Terminal-UI verarbeitet (Hinweis nur sichtbar, Snippet als Kontext).
    Antworten des KI-Modells werden tokenweise gestreamt und direkt im UI aktualisiert.
    """
    def __init__(self, factory, config, keyword_finder, ip,
                 wiki_snippet_limit, wiki_mode, proxy_base,
                 web_host, web_port,
                 wiki_timeout):
        self.streamer = None  # wird später gesetzt
        self.keyword_finder = keyword_finder
        self.ip = ip
        self.cfg = config
        self.factory = factory
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout
        self.bot = None  # wird später gesetzt
        self.texts = config.texts
        self._t = config.t

    def _reset_conversation_state(self):
        return []
    
    def _handle_context_warning(self, llm_history, chat_history):

        if not context_near_limit(llm_history, self.streamer.persona_options):
            return False

        drink = get_drink(self.bot)
        warn = self._t(
            "context_wait_message", persona_name=self.bot, drink=drink
        )

        chat_history.append((None, warn))

        persona_options = getattr(self.streamer, "persona_options", {}) or {}

        num_ctx_value = persona_options.get("num_ctx")

        ctx_limit = None
        if num_ctx_value is not None:
            try:
                ctx_limit = int(num_ctx_value)
            except (TypeError, ValueError):
                logging.warning(
                    "Ungültiger 'num_ctx'-Wert für Persona %r: %r",
                    self.bot,
                    num_ctx_value,
                )

        if ctx_limit and ctx_limit > 0:
            llm_history[:] = karl_prepare_quick_and_dirty(
                llm_history, ctx_limit
            )
        else:
            logging.warning(
                "Überspringe 'karl_prepare_quick_and_dirty' für Persona %r: num_ctx=%r",
                self.bot,
                num_ctx_value,
            )

        return True


    # Streaming der Antwort (UI wird fortlaufend aktualisiert)
    def _stream_reply(self, message_history, chat_history):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            yield None, chat_history + [(None, reply)], message_history

        # Abschluss: finalen Reply in den Verlauf übernehmen
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history


    def respond_streaming(self, user_input, chat_history, history_state):

        # Schutz: Persona noch nicht gewählt → UI verhindert das, aber doppelt hält besser
        if not self.bot:
            yield "", chat_history, history_state
            return


        # 1) Eigener Verlauf für LLM ohne UI-Hinweise (und ggf. komprimiert, wenn nötig)
        llm_history = list(history_state or [])

        # 2) Eingabefeld leeren und User-Input zeigen im Chatfenster
        logging.info(f"User input: {user_input}")
        chat_history.append((user_input, None ))
        yield "", chat_history, llm_history


        # 3) Wiki-Hinweis + Snippet (Top-Treffer)
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
            # UI-Hinweis anzeigen (nicht ins LLM-Kontextfenster einfügen)
            chat_history.append((None, wiki_hint))
            yield None, chat_history, llm_history

        # 4) Optional: Wiki-Kontext injizieren
        if snippet:
            inject_wiki_context(llm_history, title, snippet)

        # 5) Nutzerfrage ans LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Kontext-Komprimierung bei Bedarf inkl. Info in Chat-History
        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history

        # 7) Antwort streamen
        yield from self._stream_reply(llm_history, chat_history)


    def _build_ui(self, project_title, choose_persona_txt, persona_info,
                  persona_btn_suffix, input_placeholder, new_chat_label):
        with gr.Blocks() as demo:
            selected_persona_state = gr.Textbox(value="", visible=False)

            gr.HTML("""
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
            """)
            gr.Markdown(f"# {project_title}")

            with gr.Group(visible=True) as grid_group:
                gr.Markdown(choose_persona_txt)
                with gr.Row(elem_classes="persona-row", equal_height=True):
                    persona_buttons = []
                    for key, p in persona_info.items():
                        with gr.Column(scale=1, min_width=220):
                            with gr.Group(elem_classes="persona-card"):
                                gr.Image(
                                    p["image_path"],
                                    show_label=False,
                                    height=350,
                                    container=False,
                                    elem_classes="persona-img"
                                )
                                gr.Markdown(
                                    f"<div class='name'>{p['name']}</div>"
                                    f"<div class='desc'>{p['description']}</div>")
                                btn = gr.Button(f"{p['name']}{persona_btn_suffix}", variant="secondary")
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
            txt = gr.Textbox(show_label=False, placeholder=input_placeholder,
                             visible=False, interactive=False)
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
            "txt": txt,
            "clear": clear,
            "persona_buttons": persona_buttons,
            "history_state": history_state,
        }
        return demo, components

    def _persona_selected_updates(self, persona_key, persona, greeting_template, model_name, input_placeholder):
        display_name = persona["name"].title()
        greeting = greeting_template.format(
            persona_name=display_name, model_name=model_name
        )
        focus_text = f"### {persona['name']}\n{persona['description']}"

        return (
            gr.update(value=persona_key),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=persona["image_path"]),
            gr.update(value=focus_text),
            gr.update(value=greeting, visible=True),
            gr.update(value=[], label=display_name, visible=True),
            gr.update(
                value="", visible=True, interactive=True,
                placeholder=input_placeholder
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
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False),
            self._reset_conversation_state(),
        )

    def _on_persona_selected(self, key, persona_info, greeting_template, model_name, input_placeholder):
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

    def _bind_events(self, components, persona_info, model_name,
                     greeting_template, input_placeholder):
        selected_persona_state = components["selected_persona_state"]
        grid_group = components["grid_group"]
        focus_group = components["focus_group"]
        focus_img = components["focus_img"]
        focus_md = components["focus_md"]
        greeting_md = components["greeting_md"]
        chatbot = components["chatbot"]
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
            inputs=[txt, chatbot, history_state],
            outputs=[txt, chatbot, history_state],
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

        ui_cfg = getattr(self.cfg, "ui", None) or {}
        if not isinstance(ui_cfg, dict) and hasattr(ui_cfg, "__dict__"):
            ui_cfg = ui_cfg.__dict__
        web_cfg = {}
        if isinstance(ui_cfg, dict):
            web_cfg = ui_cfg.get("web") or {}

        share_enabled = bool(web_cfg.get("share"))
        if share_enabled:
            auth_cfg = web_cfg.get("share_auth") or {}
            username = auth_cfg.get("username")
            password = auth_cfg.get("password")

            if not username or not password:
                raise ValueError(
                    "'ui.web.share_auth.username' und 'password' müssen gesetzt sein, wenn 'ui.web.share' aktiviert ist."
                )

            launch_kwargs.update({
                "share": True,
                "auth": (username, password),
            })

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

        persona_info = {p["name"].lower(): p for p in system_prompts}

        demo, components = self._build_ui(
            project_title,
            choose_persona_txt,
            persona_info,
            persona_btn_suffix,
            input_placeholder,
            new_chat_label,
        )
        # Gradio 4.x verlangt, dass Events innerhalb eines Blocks-Kontexts
        # gebunden werden. Durch das erneute Öffnen des Demos als Kontext
        # können wir die bestehende Struktur beibehalten und trotzdem die
        # Events korrekt registrieren.
        with demo:
            self._bind_events(
                components,
                persona_info,
                model_name,
                greeting_template,
                input_placeholder,
            )
        self._start_server(demo)
