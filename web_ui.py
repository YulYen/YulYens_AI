import gradio as gr
from streaming_core_ollama import OllamaStreamer
import requests, logging

class WebUI:
    def __init__(self, model_name, greeting, system_prompt, keyword_finder, ip, convers_log, wiki_snippet_limit, wiki_mode, proxy_base):
        self._last_wiki_title = None
        self.model_name = model_name
        self.greeting = greeting
        self.history = []
        self.system_prompt = system_prompt
        self.keyword_finder = keyword_finder
        self.streamer = OllamaStreamer(model_name, True, system_prompt, convers_log)
        self.local_ip = ip
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_mode = wiki_mode          # "offline" | "online" | "hybrid"
        self.proxy_base = proxy_base

    def _strip_wiki_hint(self, text: str) -> str:
    # Entfernt den UI-Hinweis "🕵️‍♀️ …" + genau die eine Leerzeile,
    # die du beim Streamen mit "\n\n" vor die eigentliche Antwort setzt.
        if text.startswith("🕵️‍♀️"):
            sep = "\n\n"
            i = text.find(sep)
            return text[i+len(sep):] if i != -1 else ""
        return text
    
    def _build_history(self, chat_history):
        hist = []
        for u, b in chat_history:
            cleaned = self._strip_wiki_hint(b)
            hist.append({"role": "user", "content": u})
            if cleaned:
                hist.append({"role": "assistant", "content": cleaned})
        return hist

    def _lookup_wiki(self, user_text: str):
        """Erzeugt UI-Hinweis + holt (max. 1) Snippet. Gibt (wiki_hint, title, snippet) zurück."""
        if not self.keyword_finder:
            return None, None, None

        kws = self.keyword_finder.find_keywords(user_text) or []
        if not kws:
            return None, None, None

        # Nur Top‑Treffer anzeigen/nutzen – hält UI & Kontext schlank
        topic = kws[0]

        # Link für UI (lokal, bleibt hübsch/konstant)
        local_link  = f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{topic}"
        
        # Modus in Proxy-Call abbilden
        # offline: ?json=1&limit=...
        # online:  ?json=1&limit=...&online=1
        online_flag = "1" if self.wiki_mode in ("online", "hybrid") else "0"
        url = f"{self.proxy_base}/{topic}?json=1&limit={self.wiki_snippet_limit}&online={online_flag}"

        wiki_hint_prefix = "🕵️‍♀️ *Leah wirft einen Blick in die "
        source_label = "echte Wikipedia" if self.wiki_mode in ("online") else "lokale Wikipedia"
        wiki_hint = f"{wiki_hint_prefix}{source_label}:*\n{local_link}"

        try:
            r = requests.get(url, timeout=(3.0, 8.0))
            if r.status_code == 200:
                data = r.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[: self.wiki_snippet_limit]
                return wiki_hint, topic, snippet
            elif r.status_code == 404:
                return f"🕵️‍♀️ *Kein Eintrag gefunden:*\n{local_link}", None, None
            else:
                return f"🕵️‍♀️ *Wikipedia nicht erreichbar.*\n{local_link}", None, None
        except Exception as e:
            logging.error(f"[WIKI EXC] topic='{topic}' err={e}")
            return f"🕵️‍♀️ *Fehler: Wikipedia nicht erreichbar.*\n{local_link}", None, None

    def _inject_wiki_context(self, message_history, title: str, snippet: str):
        """Snippet als System-Kontext anhängen (Guardrail + Inhalt)."""
        guardrail = (
            "Nutze ausschließlich den folgenden Kontext aus der lokalen Wikipedia. "
            "Wenn etwas dort nicht steht, sag knapp, dass du es nicht sicher weißt."
        )
        message_history.append({"role": "system", "content": guardrail})
        msg = (
            f"Kontext zum Thema {title.replace('_',' ')}:\n"
            f"[Quelle: Lokale Wikipedia]\n{snippet}"
        )
        message_history.append({"role": "system", "content": msg})

    def _stream_reply(self, message_history, original_user_input, chat_history, wiki_hint):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            if wiki_hint:
                combined = wiki_hint + "\n\n" + reply
                yield None, chat_history[:-1] + [(original_user_input, combined)]
            else:
                yield None, chat_history + [(original_user_input, reply)]
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

        # 1) History bauen (UI‑Hinweise aus Bot‑Text entfernen)
        message_history = self._build_history(chat_history)  # 

        # 2) Eingabefeld leeren
        yield "", chat_history

        # 3) Wiki-Hinweis/Snippet holen (nur Top‑Treffer)
        wiki_hint, title, snippet = self._lookup_wiki(original_user_input)  # 
        if wiki_hint:
            chat_history.append((original_user_input, wiki_hint))
            yield None, chat_history  # Hinweis anzeigen, aber nicht ans LLM

        # 4) Optional: Kontext injizieren (Titel behalten für Follow-ups)
        if snippet:
            self._last_wiki_snippet = None  # wir nutzen es sofort, kein späterer Verbrauch
            self._last_wiki_title = title   # Titel NICHT löschen – hilft bei Folgefragen
            self._inject_wiki_context(message_history, title, snippet)  # 

        # 5) Aktuelle User-Frage ans LLM
        message_history.append({"role": "user", "content": original_user_input})

        # 6) Streamen (UI live updaten)
        yield from self._stream_reply(message_history, original_user_input, chat_history, wiki_hint)  # 


    def launch(self):
        print(f"[DEBUG] Launching WebUI on 0.0.0.0:7860")
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
