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

        # --- Callback: Persona wurde gewählt ---
        def on_persona_selected(key: str):
            # Guard
            if not key or key not in persona_info:
                # Keine Änderung; nichts sichtbar machen
                return (
                    gr.update(),                               # selected_persona_state (unchanged)
                    gr.update(),                               # greeting_md
                    gr.update(),                               # chatbot
                    gr.update(),                               # txt
                    gr.update(),                               # clear
                )
            persona = persona_info[key]
            # self.bot wird auf den (rohen) Namen gesetzt, z.B. "LEAH" | "DORIS" | "PETER"
            self.bot = persona["name"]
            
            # Korrekten Streamer für Persona
            self.streamer = self.factory.get_streamer_for_persona(self.bot)

            # Fürs UI hübsch: Titel-Case als Label
            display_name = persona["name"].title()

            greeting = f"Hallo, ich bin {display_name} 👋"
            return (
                key,                                          # selected_persona_state
                gr.update(value=greeting, visible=True),      # greeting_md sichtbar + Text
                gr.update(label=display_name, visible=True),  # chatbot sichtbar + Label
                gr.update(visible=True, interactive=True),    # txt sichtbar & aktiv
                gr.update(visible=True),                      # clear sichtbar
            )

        # --- UI ---
        with gr.Blocks() as demo:
            # H1: Projektname
            gr.Markdown(f"# {project_name}")

            # Persona-Karten
            gr.Markdown("Wähle zuerst eine Persona:")
            with gr.Row():
                # Wir bauen Buttons und registrieren Callbacks mit stabilen Closures
                persona_buttons = []
                for key, p in persona_info.items():
                    with gr.Column():
                        gr.Image(
                            value=p["image_path"], show_label=False,
                            width=128, height=128, container=False
                        )
                        gr.Markdown(f"### {p['name']}\n{p['description']}")
                        btn = gr.Button(f"{p['name']} wählen", variant="secondary")
                        persona_buttons.append((key, btn))

            # Begrüßung + Chat + Eingabe, zunächst unsichtbar
            greeting_md = gr.Markdown("", visible=False)
            chatbot = gr.Chatbot(label="", visible=False)
            txt = gr.Textbox(show_label=False, placeholder="Schreibe…", visible=False, interactive=False)
            clear = gr.Button("🔄 Neue Unterhaltung", visible=False)

            # Persona-Buttons sauber verdrahten (Closure mit Default-Arg, um Late Binding zu vermeiden)
            for key, btn in persona_buttons:
                btn.click(
                    fn=lambda key=key: on_persona_selected(key),
                    inputs=[],
                    outputs=[selected_persona_state, greeting_md, chatbot, txt, clear],
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
