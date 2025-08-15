import gradio as gr
import requests, logging
from streaming_core_ollama import OllamaStreamer, lookup_wiki_snippet, inject_wiki_context  # Neue Imports der ausgelagerten Funktionen

class WebUI:
    def __init__(self, streamer, greeting, keyword_finder, ip,
                 wiki_snippet_limit, wiki_mode, proxy_base,
                 web_host, web_port,
                 wiki_timeout):
        self.streamer = streamer
        self.greeting = greeting
        self.keyword_finder = keyword_finder
        self.ip = ip
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
        logging.info(f"Launching WebUI on 0.0.0.0:7860")
        with gr.Blocks() as demo:
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Image("static/leah.png", elem_id="leah-img", show_label=False, container=False)
                with gr.Column(scale=3):
                    gr.Markdown("""
                    ## Hallo, ich bin Leah, die freundliche KI 👋  
                    Willkommen unserem kleinen Chat.  
                    Frag mich, was du willst – ich höre zu, denke mit, und helfe dir weiter.  
                """)

            gr.Markdown(self.greeting)
            chatbot = gr.Chatbot(label="Leah")
            txt     = gr.Textbox(show_label=False, placeholder="Schreibe…")
            clear   = gr.Button("🔄 Neue Unterhaltung")

            txt.submit(
                fn=self.respond_streaming,
                inputs=[txt, chatbot],
                outputs=[txt, chatbot],
                queue=True,
            )

            clear.click(lambda: ("", []), outputs=[txt, chatbot])

        demo.launch(server_name="0.0.0.0", server_port=7860)
