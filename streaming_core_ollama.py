#streaming_core_ollama.py
import traceback, re
from ollama import chat


class OllamaStreamer:
    def __init__(self, model_name="plain", enable_logging=False, warm_up=True):
        self.model_name = model_name
        self.enable_logging = enable_logging

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

    def stream(self, messages):
        try:
            stream = chat(
                model=self.model_name,
                messages=messages,
                stream=True
            )
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    cleaned = self._clean_token(token)
                    if cleaned:
                        self._log(f"Token: {repr(cleaned)}")
                        yield cleaned
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