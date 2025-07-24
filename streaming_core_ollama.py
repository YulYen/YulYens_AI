#streaming_core_ollama.py
import traceback, re, socket
from ollama import chat


class OllamaStreamer:
    def __init__(self, model_name="plain", enable_logging=False, warm_up=True, system_prompt = None):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.enable_logging = enable_logging
        self.local_ip = self._get_local_ip()


        if warm_up:
            print("Starte aufwärmen des Models:"+model_name)
            self._warm_up()

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

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Dummy-Verbindung, um lokale IP zu ermitteln
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"

    
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
                    cleaned = self._clean_token(token)
                    buffer += cleaned
                    if any(sep in cleaned for sep in [" ", "\n"]):
                        replaced = self._replace_wiki_token(buffer)
                        buffer = ""
                        if replaced:
                            yield replaced
            if buffer:
                yield self._replace_wiki_token(buffer)
        except Exception as e:
            self._log(f"Fehler bei stream():\n{traceback.format_exc()}")
            yield f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"

    def _clean_token(self, token: str) -> str:
        # Dummy-Tags raus
        token = re.sub(r"<dummy\d+>", "", token)

        # Einzelne irrelevante Tokens rausfiltern
        stripped = token.strip().lower()
        if stripped in ["assistant", "assistent:", "antwort:"]:
            return ""

        return token
    
    def _replace_wiki_token(self, text: str) -> str:
        if self.enable_logging:
            self._log(f"Wiki-Check in Text: {repr(text)}")

        def ersetze(match):
            thema = match.group(1)
            link = f"http://{self.local_ip}:8080/content/wikipedia_de_all_nopic_2025-06/{thema}"
            ersatz = f"Leah schlägt bei Wikipedia nach: {link}"
            if self.enable_logging:
                self._log(f"Ersetze !wiki!{thema} → {ersatz}")
            return ersatz

        return re.sub(r"!wiki!([\wÄÖÜäöüß\-]+)", ersetze, text)
