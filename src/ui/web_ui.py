import gradio as gr
import logging
from config.personas import system_prompts, get_drink
from core.streaming_provider import lookup_wiki_snippet, inject_wiki_context
from core import utils

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


    def _reset_conversation_state(self):
        return []


    # Streaming der Antwort (UI wird fortlaufend aktualisiert)
    def _stream_reply(self, message_history, original_user_input, chat_history, wiki_hint):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            if wiki_hint:
                combined = wiki_hint + "\n\n" + reply
                # zwei Outputs: (txt bleibt unverändert) + Chatverlauf
                yield None, chat_history[:-1] + [(original_user_input, combined)], message_history
            else:
                yield None, chat_history + [(original_user_input, reply)], message_history
        # Abschluss: finalen Reply in den Verlauf übernehmen
        if wiki_hint and chat_history:
            chat_history[-1] = (original_user_input, wiki_hint + "\n\n" + reply)
        else:
            chat_history.append((original_user_input, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history


    def respond_streaming(self, user_input, chat_history, history_state):

        # Schutz: Persona noch nicht gewählt → UI verhindert das, aber doppelt hält besser
        if not self.bot:
            yield "", chat_history, history_state
            return

        logging.info(f"User input: {user_input}")

        # 1) Eigener Verlauf für LLM ohne UI-Hinweise (und ggf. komprimiert, wenn nötig)
        llm_history = list(history_state or [])

        # 2) Eingabefeld leeren
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
            chat_history.append((user_input, wiki_hint))
            yield None, chat_history, llm_history

        # 4) Optional: Wiki-Kontext injizieren
        if snippet:
            inject_wiki_context(llm_history, title, snippet)

        # 5) Nutzerfrage ans LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Kontext-Komprimierung bei Bedarf
        if self.streamer and utils.context_near_limit(llm_history, self.streamer.persona_options):
            drink = get_drink(self.bot)
            warn = f"Einen Moment: {self.bot} holt sich {drink} ..."
            # UI-Hinweis anzeigen (nicht ins LLM-Kontextfenster einfügen)
            chat_history.append((user_input, warn))
            persona_options = getattr(self.streamer, "persona_options", {}) or {}
            num_ctx_value = None
            if hasattr(persona_options, "get"):
                num_ctx_value = persona_options.get("num_ctx")

            ctx_limit = None
            if num_ctx_value is not None:
                try:
                    ctx_limit = int(num_ctx_value)
                except (TypeError, ValueError):
                    logging.warning( "Ungültiger 'num_ctx'-Wert für Persona %r: %r", self.bot,num_ctx_value, )

            if ctx_limit and ctx_limit > 0:
                llm_history = utils.karl_prepare_quick_and_dirty(
                    llm_history, ctx_limit
                )
            else:
                logging.warning(
                    "Überspringe 'karl_prepare_quick_and_dirty' für Persona %r: num_ctx=%r",
                    self.bot,
                    num_ctx_value,
                )
            yield None, chat_history, llm_history

        # 7) Antwort streamen
        yield from self._stream_reply(llm_history, user_input, chat_history, wiki_hint)


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

        def on_persona_selected(key: str):
            if not key or key not in persona_info:
                return (
                    gr.update(value=""),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    self._reset_conversation_state(),
                )

            p = persona_info[key]
            self.bot = p["name"]
            self.streamer = self.factory.get_streamer_for_persona(self.bot)

            display_name = p["name"].title()
            greeting = greeting_template.format(
                persona_name=display_name, model_name=model_name
            )
            focus_text = f"### {p['name']}\n{p['description']}"

            return (
                gr.update(value=key),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(value=p["image_path"]),
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

        def on_reset_to_start():
            self.bot = None
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

        for key, btn in components["persona_buttons"]:
            btn.click(
                fn=lambda key=key: on_persona_selected(key),
                inputs=[],
                outputs=[
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
                ],
                queue=False,
            )

        txt.submit(
            fn=self.respond_streaming,
            inputs=[txt, chatbot, history_state],
            outputs=[txt, chatbot, history_state],
            queue=True,
        )

        clear.click(
            fn=on_reset_to_start,
            inputs=[],
            outputs=[
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
            ],
            queue=False,
        )

    def _start_server(self, demo):
        demo.launch(server_name=self.web_host, server_port=self.web_port, show_api=False)

    def launch(self):
        ui = self.cfg.texts
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
