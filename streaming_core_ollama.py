#streaming_core_ollama.py
import traceback
import datetime, json, os
from ollama import chat
from streaming_helper import clean_token
import logging



class OllamaStreamer:
    def __init__(self, model_name="plain", warm_up=True, system_prompt = None, log_path="conversation.json"):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.conversation_log_path = log_path

        if warm_up:
            print("Starte aufwärmen des Models:"+model_name)
            self._warm_up()

    def _warm_up(self):
        logging.info(f"Sende Dummy zur Modellaktivierung: {self.model_name}")
        try:
            chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "..."}]
            )
            logging.info("Modell erfolgreich vorgewärmt.")
        except Exception as e:
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
        try:
            # Letzte User-Nachricht loggen
            last_user = None
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = m.get("content","")
                    break
            if last_user:
                self._append_conversation_log("user", last_user)

            # --- NEU: Teile der Assistant-Antwort sammeln ---
            full_reply_parts = []

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
                    # in den sichtbaren Stream-Puffer
                    buffer += cleaned
                    # --- NEU: immer auch in die Gesamtreply schreiben ---
                    full_reply_parts.append(cleaned)

                    # dein bestehendes Schwellen-/Flush-Verhalten
                    seps = [" ", "\n", "\t", ".", "?"]
                    count = sum(buffer.count(sep) for sep in seps)
                    logging.debug(f"Buffer:"+ buffer + "###"+str(count))
                    if count >= 1:
                        yield buffer
                        buffer = ""

            # Restpuffer noch ausgeben (sichtbar), NICHT doppelt in parts schieben
            if buffer:
                yield buffer

            # --- NEU: Am Ende eine einzige Log-Zeile für die gesamte Antwort ---
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)

        except Exception as e:
            logging.error(f"Fehler bei stream():\n{traceback.format_exc()}")
            err = f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"
            # sinnvoll: auch Fehler in die Konversations-Logs schreiben
            self._append_conversation_log("assistant", err)
            yield err