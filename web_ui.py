import gradio as gr
import logging
from personas import system_prompts
from streaming_core_ollama import  lookup_wiki_snippet, inject_wiki_context  # Neue Imports der ausgelagerten Funktionen

class WebUI:
    def __init__(self, project_name, factory, keyword_finder, ip,
                 wiki_snippet_limit, wiki_mode, proxy_base,
                 web_host, web_port,
                 wiki_timeout):
        self.streamer = None # wird später gesetzt
        self.greeting = "greeting TODO"
        self.project_name = project_name
        self.keyword_finder = keyword_finder
        self.ip = ip
        self.factory = factory
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout

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

    # Die Methoden _lookup_wiki und _inject_wiki_context wurden entfernt, da ihre Funktionalität
    # jetzt von lookup_wiki_snippet und inject_wiki_context übernommen wird.

    def _stream_reply(self, message_history, original_user_input, chat_history, wiki_hint):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            if wiki_hint:
                combined = wiki_hint + "\n\n" + reply
                yield None, chat_history[:-1] + [(original_user_input, combined)]
            else:
                yield None, chat_history + [(original_user_input, reply)]
        # Abschluss des Streaming: Den finalen Reply in den Chat-Verlauf übernehmen
        if wiki_hint:
            chat_history[-1] = (original_user_input, wiki_hint + "\n\n" + reply)
        else:
            chat_history.append((original_user_input, reply))
        yield None, chat_history

    def respond_streaming(self, user_input, chat_history):
        if user_input.strip().lower() == "clear":
            yield "", []
            return

        original_user_input = user_input
        logging.info(f"User input: {user_input}")

        # 1) Verlauf für das LLM aufbereiten (UI-Hinweise aus vorherigen Bot-Antworten entfernen)
        message_history = self._build_history(chat_history)

        # 2) Eingabefeld in der UI leeren
        yield "", chat_history

        # 3) Wiki-Hinweis und Snippet holen (nur Top-Treffer aus Wikipedia)
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
            yield None, chat_history  # Hinweis für den Nutzer ausgeben

        # 4) Optional: Wiki-Kontext injizieren (falls ein Snippet gefunden wurde)
        if snippet:
            self._last_wiki_snippet = None       # Snippet wird sofort verbraucht, nicht für später gespeichert
            self._last_wiki_title = title        # Titel des Wiki-Artikels merken für Folgefragen
            inject_wiki_context(message_history, title, snippet)  # **Neuer Aufruf**: nutzt die ausgelagerte Funktion zum Kontext-Injektieren

        # 5) Nutzerfrage zur Nachrichtenhistorie fürs LLM hinzufügen
        message_history.append({"role": "user", "content": original_user_input})

        # 6) Antwort vom LLM streamen und in der UI anzeigen (Logik unverändert)
        yield from self._stream_reply(message_history, original_user_input, chat_history, wiki_hint)



    def launch(self):
        # Mapping: "leah" -> persona-dict
        persona_info = {p["name"].lower(): p for p in system_prompts}

        # Falls du projekt_name in __init__ gesetzt hast, sonst Fallback:
        project_name = getattr(self, "project_name", "Yul Yen’s AI Orchestra")

        # State: ausgewählte Persona (z. B. "leah"|"doris"|"peter"), initial None
        selected_persona_state = gr.State(None)

        def on_persona_selected(key: str):
            # Safety
            if not key or key not in persona_info:
                return (
                    gr.update(),  # selected_persona_state
                    gr.update(visible=True),   # grid_group: bleibt sichtbar
                    gr.update(visible=False),  # focus_group: bleibt verborgen
                    gr.update(),               # focus_img
                    gr.update(),               # focus_md
                    gr.update(),               # greeting_md
                    gr.update(),               # chatbot
                    gr.update(),               # txt
                    gr.update(),               # clear
                )

            p = persona_info[key]             # dict aus personas.py
            self.bot = p["name"]              # "LEAH"/"DORIS"/"PETER" o.ä.

            self.streamer = self.factory.get_streamer_for_persona(self.bot)

            display_name = p["name"].title()
            greeting = f"Hallo, ich bin {display_name} 👋"  # TODO: Auf normales Greeting aus Config umstellen
            focus_text = f"### {p['name']}\n{p['description']}"

            return (
                key,                             # selected_persona_state
                gr.update(visible=False),        # grid_group ausblenden
                gr.update(visible=True),         # focus_group einblenden
                gr.update(value=p["image_path"]),# focus_img → großes Bild der Persona
                gr.update(value=focus_text),     # focus_md → Titel + Beschreibung
                gr.update(value=greeting, visible=True),      # greeting sichtbar + Text
                gr.update(label=display_name, visible=True),  # chatbot sichtbar + Label
                gr.update(visible=True, interactive=True),    # txt sichtbar & aktiv
                gr.update(visible=True),                       # clear sichtbar
            )

        # --- UI ---
        with gr.Blocks() as demo:
            gr.Markdown(f"# {project_name}")

            # --- GRID MIT KARTEN (Startzustand) ---
            with gr.Group(visible=True) as grid_group:
                gr.Markdown("Wähle zuerst eine Persona:")
                with gr.Row():
                    persona_buttons = []
                    for key, p in persona_info.items():
                        with gr.Column():
                            gr.Image(p["image_path"], show_label=False, width=128, height=128, container=False)
                            gr.Markdown(f"### {p['name']}\n{p['description']}")
                            btn = gr.Button(f"{p['name']} wählen", variant="secondary")
                            persona_buttons.append((key, btn))

            # --- FOKUS-PANEL NUR FÜR GEWÄHLTE PERSONA ---
            with gr.Group(visible=False) as focus_group:
                with gr.Row():
                    with gr.Column(scale=1):
                        focus_img = gr.Image(show_label=False, container=False)  # großer Hero
                    with gr.Column(scale=3):
                        focus_md = gr.Markdown("")  # Name + Beschreibung
                gr.Markdown("---")

            # Chat-Teil wie gehabt, initial verborgen
            greeting_md = gr.Markdown("", visible=False)
            chatbot = gr.Chatbot(label="", visible=False)
            txt = gr.Textbox(show_label=False, placeholder="Schreibe…", visible=False, interactive=False)
            clear = gr.Button("🔄 Neue Unterhaltung", visible=False)

            # Buttons sauber verdrahten (Closure!)
            for key, btn in persona_buttons:
                btn.click(
                    fn=lambda key=key: on_persona_selected(key),
                    inputs=[],
                    outputs=[
                        selected_persona_state,
                        grid_group, focus_group,
                        focus_img, focus_md,
                        greeting_md, chatbot, txt, clear
                    ],
                    queue=False,
                )

            # Chat-Funktionalität (deine bestehende Streaming-Logik bleibt)
            txt.submit(
                fn=self.respond_streaming,
                inputs=[txt, chatbot],
                outputs=[txt, chatbot],
                queue=True,
            )

            # Reset: Chat löschen, Persona bleibt (du kannst hier auch Persona wieder nullen, wenn gewünscht)
            clear.click(lambda: ("", []), outputs=[txt, chatbot])

        demo.launch(server_name="0.0.0.0", server_port=7860)
