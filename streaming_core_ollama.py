#streaming_core_ollama.py
import traceback
from ollama import chat

#client = Client(host='http://localhost:11434')

def send_message_stream_gen(messages, model_name="plain", enable_logging=False):
    """
    Generator für Streaming-Antworten von Ollama über die Python-API.
    Gibt jeden Token (Wort oder Satzzeichen) einzeln aus.
    Bei Fehler wird eine Debug-Zeile mitgegeben.
    """
    try:
        stream = chat(
            model=model_name,
            messages=messages,
            stream=True
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                if enable_logging:
                    print(f"[DEBUG] Token: {repr(token)}")
                yield token

    except Exception as e:
        if enable_logging:
            print(f"[DEBUG] Fehler bei Ollama-Zugriff:\n{traceback.format_exc()}")
        yield f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"


def warm_up_model(model_name="leah13b1", enable_logging=False):
    """
    Sendet eine minimale Nachricht an das Modell, um es aufzuwärmen.
    Gibt True bei Erfolg, False bei Fehler.
    """
    try:
        if enable_logging:
            print(f"[DEBUG] Sende Dummy zur Modellaktivierung: {model_name}")
        client.chat(model=model_name, messages=[{"role": "user", "content": "..."}])
        return True
    except Exception as e:
        if enable_logging:
            print(f"[DEBUG] Fehler {str(e)} beim Aufwärmen des Modells:\n{traceback.format_exc()}")
        return False
    

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
                    self._log(f"Token: {repr(token)}")
                    yield token
        except Exception as e:
            self._log(f"Fehler bei stream():\n{traceback.format_exc()}")
            yield f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"