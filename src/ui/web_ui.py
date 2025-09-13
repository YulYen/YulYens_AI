import gradio as gr
import logging
from config.personas import system_prompts, get_drink
from core.streaming_provider import lookup_wiki_snippet, inject_wiki_context  # ausgelagerte Funktionen
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
        self.bot = None  # FIX: explizit initialisieren
        self._last_wiki_snippet = None
        self._last_wiki_title = None

    def _strip_wiki_hint(self, text: str) -> str:
        # Entfernt den UI-Hinweis "🕵️‍♀️ …" samt der Leerzeile vor der eigentlichen Antwort.
        if text.startswith("🕵️‍♀️"):
            sep = "\n\n"
            i = text.find(sep)
            return text[i+len(sep):] if i != -1 else ""
        return text

    def _build_history(self, chat_history):
        hist = []
        for user_msg, bot_msg in chat_history:
            cleaned = self._strip_wiki_hint(bot_msg)
            hist.append({"role": "user", "content": user_msg})
            if cleaned:
                hist.append({"role": "assistant", "content": cleaned})
        return hist

    # Streaming der Antwort (UI wird fortlaufend aktualisiert)
    def _stream_reply(self, message_history, original_user_input, chat_history, wiki_hint):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            if wiki_hint:
                combined = wiki_hint + "\n\n" + reply
                # zwei Outputs: (txt bleibt unverändert) + Chatverlauf
                yield None, chat_history[:-1] + [(original_user_input, combined)]
            else:
                yield None, chat_history + [(original_user_input, reply)]
        # Abschluss: finalen Reply in den Verlauf übernehmen
        if wiki_hint and chat_history:
            chat_history[-1] = (original_user_input, wiki_hint + "\n\n" + reply)
        else:
            chat_history.append((original_user_input, reply))
        yield None, chat_history

    def respond_streaming(self, user_input, chat_history):
        # Schutz: Kein Text / Reset-Kommando
        if not user_input or user_input.strip().lower() == "clear":
            yield "", []
            return

        # Schutz: Persona noch nicht gewählt → UI verhindert das, aber doppelt hält besser
        if not self.bot:
            yield "", chat_history
            return

        original_user_input = user_input
        logging.info(f"User input: {user_input}")

        # 1) Verlauf für LLM ohne UI-Hinweise
        message_history = self._build_history(chat_history)

        # 2) Eingabefeld leeren
        yield "", chat_history

        # 3) Wiki-Hinweis + Snippet (Top-Treffer)
        wiki_hint, title, snippet = lookup_wiki_snippet(
            original_user_input,
            self.bot,
            self.keyword_finder,
            self.wiki_mode,
            self.proxy_base,
            self.wiki_snippet_limit,
            self.wiki_timeout,
        )

        if wiki_hint:
            # UI-Hinweis anzeigen (nicht ins LLM-Kontextfenster einfügen)
            chat_history.append((original_user_input, wiki_hint))
            yield None, chat_history

        # 4) Optional: Wiki-Kontext injizieren
        if snippet:
            self._last_wiki_snippet = None   # wird sofort verbraucht
            self._last_wiki_title = title
            inject_wiki_context(message_history, title, snippet)

        # 5) Nutzerfrage ans LLM
        message_history.append({"role": "user", "content": original_user_input})

        if self.streamer and utils.context_near_limit(
            message_history, self.streamer.persona_options
        ):
            drink = get_drink(self.bot)
            warn = f"Einen Moment: {self.bot} holt sich {drink} ..."
            yield None, chat_history + [(original_user_input, warn)]

        # 6) Antwort streamen
        yield from self._stream_reply(message_history, original_user_input, chat_history, wiki_hint)

    def launch(self, cli_args=None):
        # cli_args wird derzeit ignoriert (z. B. persona)
        # --- UI-Texte aus zentraler Config ---
        ui = self.cfg.texts
        model_name           = self.cfg.core.get("model_name")
        project_title        = ui.get("project_name")
        choose_persona_txt   = ui.get("choose_persona")
        new_chat_label       = ui.get("new_chat")
        input_placeholder    = ui.get("input_placeholder")
        greeting_template    = ui.get("greeting")
        persona_btn_suffix   = ui.get("persona_button_suffix")

        # Personas
        persona_info = {p["name"].lower(): p for p in system_prompts}

        # --- Event-Handler ---
        def on_persona_selected(key: str):
            if not key or key not in persona_info:
                # Startzustand
                return (
                    gr.update(value=""),                 # selected_persona_state
                    gr.update(visible=True),             # grid_group
                    gr.update(visible=False),            # focus_group
                    gr.update(),                         # focus_img
                    gr.update(),                         # focus_md
                    gr.update(),                         # greeting_md
                    gr.update(),                         # chatbot
                    gr.update(),                         # txt
                    gr.update(),                         # clear
                )

            p = persona_info[key]
            self.bot = p["name"]  # "LEAH"/"DORIS"/"PETER" etc.
            self.streamer = self.factory.get_streamer_for_persona(self.bot)

            display_name = p["name"].title()
            greeting = greeting_template.format(persona_name=display_name, model_name=model_name)
            focus_text = f"### {p['name']}\n{p['description']}"

            return (
                gr.update(value=key),                              # selected_persona_state
                gr.update(visible=False),                          # grid_group aus
                gr.update(visible=True),                           # focus_group an
                gr.update(value=p["image_path"]),                  # focus_img
                gr.update(value=focus_text),                       # focus_md
                gr.update(value=greeting, visible=True),           # greeting_md
                gr.update(value=[], label=display_name, visible=True),  # chatbot
                gr.update(value="", visible=True, interactive=True, placeholder=input_placeholder),  # txt
                gr.update(visible=True),                           # clear
            )

        def on_reset_to_start():
            self.bot = None
            return (
                gr.update(value=""),               # persona_state zurücksetzen
                gr.update(visible=True),           # grid_group sichtbar
                gr.update(visible=False),          # focus_group verstecken
                gr.update(value=None),             # focus_img leeren
                gr.update(value=""),               # focus_md leeren
                gr.update(value="", visible=False),# greeting_md verstecken
                gr.update(value=[], label="", visible=False),  # chatbot leeren
                gr.update(value="", visible=False, interactive=False),  # txt leeren
                gr.update(visible=False),          # clear verstecken
            )

        # --- UI ---
        with gr.Blocks() as demo:
            # FIX: selected_persona_state MUSS im selben Blocks-Kontext erzeugt werden!
            # Du kannst Textbox als Hidden-State nutzen oder gr.State. Wir lassen deine Variante.
            selected_persona_state = gr.Textbox(value="", visible=False)

            gr.HTML("""
                <style>
                .persona-row { gap:24px; }  /* etwas mehr Abstand */
                .persona-card { 
                    border:1px solid #e3e7ed; 
                    border-radius:10px; 
                    padding:12px; 
                    text-align:center;     /* alle Inhalte inkl. Bild mittig */
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

            # Auswahl-Grid (Startzustand)
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
                                    elem_classes="persona-img"  # <- für gezieltes CSS
                                )
                                # Name + Beschreibung getrennt, klarer
                                gr.Markdown(
                                    f"<div class='name'>{p['name']}</div>"
                                    f"<div class='desc'>{p['description']}</div>")
                                btn = gr.Button(f"{p['name']}{persona_btn_suffix}", variant="secondary")
                                persona_buttons.append((key, btn))

            # Fokus-Panel
            with gr.Group(visible=False) as focus_group:
                with gr.Row():
                    with gr.Column(scale=1):
                        focus_img = gr.Image(show_label=False, container=False)
                    with gr.Column(scale=3):
                        focus_md = gr.Markdown("")
                gr.Markdown("---")

            # Chat (initial versteckt)
            greeting_md = gr.Markdown("", visible=False)
            chatbot = gr.Chatbot(label="", visible=False)
            txt = gr.Textbox(show_label=False, placeholder=input_placeholder, visible=False, interactive=False)
            clear = gr.Button(new_chat_label, visible=False)

            # Persona-Buttons binden
            for key, btn in persona_buttons:
                btn.click(
                    fn=lambda key=key: on_persona_selected(key),
                    inputs=[],
                    outputs=[
                        selected_persona_state,
                        grid_group, focus_group,
                        focus_img, focus_md,
                        greeting_md, chatbot, txt, clear,
                    ],
                    queue=False,
                )

            # Streaming
            txt.submit(
                fn=self.respond_streaming,
                inputs=[txt, chatbot],
                outputs=[txt, chatbot],
                queue=True,
            )

            # Reset
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
                ],
                queue=False,
            )

        demo.launch(server_name="127.0.0.1", server_port=7860, show_api=False)
