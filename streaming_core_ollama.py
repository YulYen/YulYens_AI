#streaming_core_ollama.py
import traceback, socket
from ollama import chat
from streaming_helper import clean_token, replace_wiki_token


class OllamaStreamer:
    def __init__(self, model_name="plain", enable_logging=False, warm_up=True, system_prompt = None):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.enable_logging = enable_logging

        if warm_up:
            print("Starte aufwärmen des Models:"+model_name)
            self._warm_up()

        # Dynamische IP für Wiki-Link ermitteln
        self.local_ip = self._get_local_ip()

    def _log(self, message):
        if self.enable_logging:
            print(f"[DEBUG] {message}")

    def _warm_up(self):
        self._log(f"Sende Dummy zur Modellaktivierung: {self.model_name}")
        try:
            chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "..."}]
            )
            self._log("Modell erfolgreich vorgewärmt.")
        except Exception as e:
            self._log(f"Fehler beim Aufwärmen des Modells:\n{traceback.format_exc()}")

    def stream(self, messages):
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
            self._log(messages)
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
                    #self._log(f"Buffer:"+ buffer + "###"+str(count))
                    if count >= 2:
                        #self._log(f"Wiki-Check in Buffer: {repr(buffer)}")
                        replaced = replace_wiki_token(buffer, self.local_ip, self.enable_logging, self._log)
                        #if replaced != buffer:
                            #self._log(f"Wiki ersetzt in: {repr(replaced)}")
                        yield replaced
                        buffer = ""
            if buffer:
                #self._log(f"Wiki-Check in final Buffer: {repr(buffer)}")
                yield replace_wiki_token(buffer, self.local_ip, self.enable_logging, self._log)
        except Exception as e:
            self._log(f"Fehler bei stream():\n{traceback.format_exc()}")
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
