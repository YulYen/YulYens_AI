#streaming_core_ollama.py
import traceback, socket
from ollama import chat
from streaming_helper import clean_token, replace_wiki_token
import logging



class OllamaStreamer:
    def __init__(self, model_name="plain", warm_up=True, system_prompt = None):
        self.model_name = model_name
        self.system_prompt = system_prompt

        if warm_up:
            print("Starte aufwärmen des Models:"+model_name)
            self._warm_up()

        # Dynamische IP für Wiki-Link ermitteln
        self.local_ip = self._get_local_ip()

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

    def stream(self, messages):
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
            logging.info(messages)
        try:
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
                    buffer += cleaned
                    seps = [" ", "\n", "\t", ".", "?"]
                    count = sum(buffer.count(sep) for sep in seps)
                    logging.debug(f"Buffer:"+ buffer + "###"+str(count))
                    if count >= 2:
                        logging.debug(f"Wiki-Check in Buffer: {repr(buffer)}")
                        replaced = replace_wiki_token(buffer, self.local_ip)
                        yield replaced
                        buffer = ""
            if buffer:
                logging.debug(f"Wiki-Check in final Buffer: {repr(buffer)}")
                yield replace_wiki_token(buffer, self.local_ip)
        except Exception as e:
            logging.error(f"Fehler bei stream():\n{traceback.format_exc()}")
            yield f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"
