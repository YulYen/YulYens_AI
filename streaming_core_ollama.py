# streaming_core_ollama.py
import traceback
import datetime, json, os
from ollama import chat
from streaming_helper import clean_token
import requests, logging


class OllamaStreamer:
    def __init__(self, model_name="plain", warm_up=True, system_prompt=None, log_file="conversation.json"):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self._logs_dir = "logs"
        os.makedirs(self._logs_dir, exist_ok=True)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
       
        if warm_up:
            logging.info("Starte aufwärmen des Models:" + model_name)
            self._warm_up()

    def _warm_up(self):
        logging.info(f"Sende Dummy zur Modellaktivierung: {self.model_name}")
        try:
            chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "..."}]
            )
            logging.info("Modell erfolgreich vorgewärmt.")
        except Exception:
            logging.error(f"Fehler beim Aufwärmen des Modells:\n{traceback.format_exc()}")

    def _append_conversation_log(self, role, content):
        try:
            entry = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "model": self.model_name,
                "role": role,
                "content": content
            }
            with open(self.conversation_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.error(f"Fehler beim Schreiben des Conversation_log : {e}")

    def stream(self, messages):
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
            logging.info(messages)

        # Letzte User-Nachricht ins zentrale Log schreiben
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_conversation_log("user", m["content"])
                break

        full_reply_parts = []
        try:

            # Eigentliches Streaming
            stream = chat(
                model=self.model_name,
                messages=messages,
                stream=True
            )
            buffer = ""
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    cleaned = clean_token(token)
                    if not cleaned:
                        continue
                    buffer += cleaned
                    full_reply_parts.append(cleaned)

                    seps = [" ", "\n", "\t", ".", "?"]
                    count = sum(buffer.count(sep) for sep in seps)
                    logging.debug(f"Buffer:" + buffer + "###" + str(count))
                    if count >= 1:
                        yield buffer
                        buffer = ""

            if buffer:
                yield buffer

            # Finale Assistant-Antwort loggen
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)

        except Exception as e:
            logging.error(f"Fehler bei stream():\n{traceback.format_exc()}")
            err = f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"
            self._append_conversation_log("assistant", err)
            yield err



    def respond_one_shot(self, user_input: str, keyword_finder, wiki_mode, wiki_proxy_base, wiki_snippet_limit) -> str:
        if user_input.strip().lower() == "clear":
            return ""
        logging.info(f"User input: {user_input}")
        messages = []
        snippet = None
        wiki_hint = None
        title = None
        # Wiki-Hinweis und Snippet holen (nur Top-Treffer)
        if keyword_finder:
            topic = keyword_finder.find_top_keyword(user_input)
            if topic:
                online_flag = "1" if wiki_mode == "online" else "0"
                url = f"{wiki_proxy_base.rstrip('/')}/{topic}?json=1&limit={wiki_snippet_limit}&online={online_flag}"
                try:
                    r = requests.get(url, timeout=(3.0, 8.0))
                    if r.status_code == 200:
                        data = r.json()
                        text = (data.get("text") or "").replace("\r", " ").strip()
                        snippet = text[: wiki_snippet_limit]
                        wiki_hint = data.get("wiki_hint")
                        title = topic
                    elif r.status_code == 404:
                        wiki_hint = f"🕵️‍♀️ *Kein Eintrag gefunden:*{topic}"
                    else:
                        wiki_hint = f"🕵️‍♀️ *Wikipedia nicht erreichbar.*{topic}"
                except Exception as e:
                    logging.error(f"[WIKI EXC] topic='{topic}' err={e}")
                    wiki_hint = f"🕵️‍♀️ *Fehler: Wikipedia nicht erreichbar.*{topic}"
        # Kontext aus Wikipedia (falls verfügbar) als System-Nachrichten anhängen
        if snippet:
            guardrail = (
                "Nutze ausschließlich den folgenden Kontext aus Wikipedia. "
                "Wenn etwas dort nicht steht, sag knapp, dass du es nicht sicher weißt."
            )
            messages.append({"role": "system", "content": guardrail})
            msg = (
                f"Kontext zum Thema {title.replace('_',' ')}: "
                f"[Quelle: Wikipedia] {snippet}"
            )
            messages.append({"role": "system", "content": msg})
        # Nutzerfrage als letzte Message hinzufügen
        messages.append({"role": "user", "content": user_input})
        # LLM-Aufruf (Ollama) durchführen und gesamte Antwort sammeln
        full_reply_parts = []
        for token in self.stream(messages=messages):
            full_reply_parts.append(token)
        full_reply = "".join(full_reply_parts).strip()
        return full_reply
