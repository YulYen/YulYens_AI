import gradio as gr
from streaming_core_ollama import OllamaStreamer
import requests, logging

PROXY_BASE = "http://localhost:8042"

class WebUI:
    def __init__(self, model_name, greeting, system_prompt, keyword_finder, ip, convers_log):
        self._last_wiki_snippet = None
        self._last_wiki_title = None
        self.model_name = model_name
        self.greeting = greeting
        self.history = []
        self.system_prompt = system_prompt
        self.keyword_finder = keyword_finder
        self.streamer = OllamaStreamer(model_name, True, system_prompt, convers_log)
        self.local_ip = ip

    def respond_streaming(self, user_input, chat_history):
        # Spezialfall: "clear" leitet neue Unterhaltung ein
        if user_input.strip().lower() == "clear":
            yield "", []
            return

        # Merke Originaleingabe, um sie ggf. korrekt anzeigen zu können
        original_user_input = user_input

        logging.info(f"User input: {user_input}")
        wiki_hint = None  # trackt, ob wir gleich eine Hinweis-Zeile angezeigt haben


        # 1. LLM-History vorbereiten – aber ohne Wiki-Hinweise!
        message_history = []
        for u, b in chat_history:
            if b.startswith("🕵️‍♀️"):  # Skip Anzeige-Hinweise
                continue
            message_history.append({"role": "user", "content": u})
            message_history.append({"role": "assistant", "content": b})
        #TODO weg: message_history.append({"role": "user", "content": original_user_input})

        # 2. Eingabefeld leeren (Textfeld zurücksetzen)
        yield "", chat_history

        # 3. Wikipedia-Hinweis erzeugen (aber **nicht ins Prompt geben**)
        if self.keyword_finder is not None:
            keywords = self.keyword_finder.find_keywords(original_user_input)
            wiki_hint = None
            if keywords:
                links = [
                    f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{kw}"
                    for kw in keywords
                ]
                wiki_hint = "🕵️‍♀️ *Leah wirft einen Blick in die lokale Wikipedia:*\n" + "\n".join(links)

            if wiki_hint:
                # Hinweis nur anzeigen – nicht ins LLM!
                chat_history.append((original_user_input, wiki_hint))
                yield None, chat_history
                #TODO Weg:  LLM-Antwort erfolgt auf leere User-Zeile
                #user_input = None
                #message_history.append({"role": "user", "content": ""})

            for topic in keywords:
                try:
                    r = requests.get(f"{PROXY_BASE}/{topic}?json=1&limit=800", timeout=(3.0, 8.0))

                    if r.status_code == 200:
                        data = r.json()
                        text = data.get("text", "")
                        text_snippet = text[:255].replace('\n',' ')
                        logging.info(f"[WIKI 200] topic='{topic}' len={len(text)}")
                        logging.info(f"[WIKI 200 PREVIEW] {text_snippet}")

                        # 1) Snippet merken (nur für den nächsten Prompt)
                        self._last_wiki_title = topic
                        self._last_wiki_snippet = (text or "")[:800].replace("\r", " ").strip()

                        # 2) zur Nachvollziehbarkeit
                        logging.debug(f"[WIKI INJECT READY] topic='{topic}' use_len={len(self._last_wiki_snippet)}")


                    elif r.status_code == 404:
                        logging.info(f"[WIKI 404] topic='{topic}'")
                        logging.info(f"[WIKI 404 PATH] {PROXY_BASE}/{topic}?json=1&limit=800")
                    else:
                        logging.warning(f"[WIKI other] topic='{topic}' status={r.status_code}")
                except Exception as e:
                        logging.error(f"[WIKI EXC] topic='{topic}' err={e}")

        # Optionaler Wiki-Spickzettel als System-Kontext (nicht zitieren/erwähnen)
        if getattr(self, "_last_wiki_snippet", None):
            msg = (
                "Kontext für diese eine Antwort (nicht zitieren, nicht erwähnen; "
                "nur zum besseren Verständnis nutzen):\n"
                f"[Quelle: Lokale Wikipedia – {getattr(self, '_last_wiki_title','').replace('_',' ')}]\n"
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
