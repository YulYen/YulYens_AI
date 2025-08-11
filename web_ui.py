import gradio as gr
from streaming_core_ollama import OllamaStreamer
import requests, logging

PROXY_BASE = "http://localhost:8042"

class WebUI:
    def __init__(self, model_name, greeting, system_prompt, keyword_finder, ip, convers_log, wiki_snippet_limit):
        self._last_wiki_snippet = None
        self._last_wiki_title = None
        self.model_name = model_name
        self.greeting = greeting
        self.history = []
        self.system_prompt = system_prompt
        self.keyword_finder = keyword_finder
        self.streamer = OllamaStreamer(model_name, True, system_prompt, convers_log)
        self.local_ip = ip
        self.wiki_snippet_limit = wiki_snippet_limit

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
        link = f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{topic}"
        wiki_hint = f"🕵️‍♀️ *Leah wirft einen Blick in die lokale Wikipedia:*\n{link}"

        try:
            r = requests.get(f"{PROXY_BASE}/{topic}?json=1&limit={self.wiki_snippet_limit}", timeout=(3.0, 8.0))
            if r.status_code == 200:
                data = r.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[: self.wiki_snippet_limit]
                return wiki_hint, topic, snippet
            elif r.status_code == 404:
                return f"🕵️‍♀️ *Kein Eintrag gefunden:*\n{link}", None, None
            else:
                return f"🕵️‍♀️ *Lokale Wikipedia nicht erreichbar.*\n{link}", None, None
        except Exception as e:
            logging.error(f"[WIKI EXC] topic='{topic}' err={e}")
            return f"🕵️‍♀️ *Lokale Wikipedia nicht erreichbar.*\n{link}", None, None

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


    def respond_streaming_OLD(self, user_input, chat_history):
        # Spezialfall: "clear" leitet neue Unterhaltung ein
        if user_input.strip().lower() == "clear":
            yield "", []
            return

        # Merke Originaleingabe, um sie ggf. korrekt anzeigen zu können
        original_user_input = user_input

        logging.info(f"User input: {user_input}")
        wiki_hint = None  # trackt, ob wir gleich eine Hinweis-Zeile angezeigt haben


        # 1. LLM-History vorbereiten – aber ohne UI-Hinweis im Bot-Text
        message_history = []
        for u, b in chat_history:
            cleaned = self._strip_wiki_hint(b)
            message_history.append({"role": "user", "content": u})
            if cleaned:  # nur anhängen, wenn schon eine echte Antwort existiert
                message_history.append({"role": "assistant", "content": cleaned})

        # 2. Eingabefeld leeren (Textfeld zurücksetzen)
        yield "", chat_history

        # 3. Wikipedia-Hinweis erzeugen (aber **nicht ins Prompt geben**)
        if self.keyword_finder is not None:
            keyword = self.keyword_finder.find_top_keyword(original_user_input)
            wiki_hint = None
            if keyword:
                link = f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{keyword} \n\n"
                try:
                    r = requests.get(f"{PROXY_BASE}/{keyword}?json=1&limit={self.wiki_snippet_limit}", timeout=(3.0, 8.0))

                    if r.status_code == 200:
                        wiki_hint = "🕵️‍♀️ *Leah wirft einen Blick in die lokale Wikipedia:*\n" + link
                        data = r.json()
                        text = data.get("text", "")
                        text_snippet = text[:255].replace('\n',' ')
                        logging.info(f"[WIKI 200] topic='{keyword}' len={len(text)}")
                        logging.info(f"[WIKI 200 PREVIEW] {text_snippet}")

                        # 1) Snippet merken (nur für den nächsten Prompt)
                        self._last_wiki_title = keyword
                        self._last_wiki_snippet = (text or "")[:self.wiki_snippet_limit].replace("\r", " ").strip()

                        # 2) zur Nachvollziehbarkeit
                        logging.debug(f"[WIKI INJECT READY] topic='{keyword}' use_len={len(self._last_wiki_snippet)}")


                    elif r.status_code == 404:
                        if wiki_hint is None:
                            wiki_hint = "🕵️‍♀️ *Leah findet nichts in der lokalen lokale Wikipedia zu:*\n"  + link
                        logging.info(f"[WIKI 404] topic='{keyword}'")
                        logging.info(f"[WIKI 404 PATH] {PROXY_BASE}/{keyword}?json=1&limit=800")
                    else:
                        logging.warning(f"[WIKI other] topic='{keyword}' status={r.status_code}")
                            # NEU: Kiwix/Proxy nicht erreichbar
                        if wiki_hint is None:
                            wiki_hint = "🕵️‍♀️ *Leah erreicht die lokale Wikipedia nicht.*\n" + link
                except Exception as e:
                        logging.error(f"[WIKI EXC] topic='{keyword}' err={e}")

                if wiki_hint:
                # Hinweis nur anzeigen – nicht ins LLM!
                    chat_history.append((original_user_input, wiki_hint))
                    yield None, chat_history

        # Optionaler Wiki-Spickzettel als System-Kontext (nicht zitieren/erwähnen)
        if getattr(self, "_last_wiki_snippet", None):
            msg = (
                f"Kontext zum Thema {getattr(self, '_last_wiki_title','').replace('_',' ')}:\n "
                f"[Quelle: Lokale Wikipedia]\n"
                f"{self._last_wiki_snippet}"
            )
            message_history.append({"role": "system", "content": msg})
            logging.info(f"[WIKI INJECTED] title='{getattr(self, '_last_wiki_title','')}' len={len(self._last_wiki_snippet)}")
            # nur einmal verwenden
            self._last_wiki_snippet = None
            self._last_wiki_title = None

        message_history.append({"role": "user", "content": original_user_input})


        # 4. LLM-Antwort streamen
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            if wiki_hint:
                combined = wiki_hint + "\n\n" + reply
                # letzte (user, bot)-Zeile live aktualisieren statt neues Paar anzuhängen
                yield None, chat_history[:-1] + [(original_user_input, combined)]
            else:
                yield None, chat_history + [(original_user_input, reply)]

        # Final-Update
        if wiki_hint:
            chat_history[-1] = (original_user_input, wiki_hint + "\n\n" + reply)
        else:
            chat_history.append((original_user_input, reply))
        yield None, chat_history



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
