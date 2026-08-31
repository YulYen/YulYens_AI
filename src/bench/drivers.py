"""Die zwei Wege, auf denen der Harness Tokens bezieht (#42).

Sie messen **nicht** dasselbe, und das ist Absicht:

| Weg | im Messpfad |
|---|---|
| `in-process` | Persona-Prompt, Guard (Ein- und Ausgang), Holdback, Modell |
| `http` | dazu FastAPI/SSE und alles, was der laufende Server sonst tut — bei aktivem Wiki also auch spaCy und der Kiwix-Abruf |

Wer beide fährt, bekommt die Differenz geschenkt. Wer sie verwechselt,
vergleicht zwei Läufe, die nie vergleichbar waren — deshalb steht der Modus
in der Kopfzeile jedes Reports.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

_HTTP_TIMEOUT = (10, 300)  # (connect, read) — ein 13B-Modell darf lange denken


class InProcessDriver:
    """Fragt die Streamer direkt, ohne Server und ohne Netz.

    Der Streamer wird **pro Persona einmal** gebaut und wiederverwendet. Ein
    frischer Streamer je Messung wäre sauberer aussehende Isolation, würde aber
    den Aufbau des Objekts mitmessen — und genau das soll die Stoppuhr nicht.
    """

    mode = "in-process"

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._streamers: dict[str, Any] = {}
        self._last: Any = None

    def _streamer(self, persona: str) -> Any:
        if persona not in self._streamers:
            self._streamers[persona] = self._factory.get_streamer_for_persona(persona)
        return self._streamers[persona]

    def guard(self, persona: str) -> Any:
        return getattr(self._streamer(persona), "guard", None)

    def stream(self, persona: str, question: str) -> Iterator[str]:
        streamer = self._streamer(persona)
        self._last = streamer
        # Bewusst ohne Wiki-/RSS-Injektion: der Kontext-Abruf hängt an spaCy und
        # am Kiwix-Server, schwankt je Frage um Sekunden und würde die Zahl
        # dominieren, die hier gemessen werden soll. Wer den vollen Pfad will,
        # nimmt --api-url gegen den laufenden Server.
        return streamer.stream(messages=[{"role": "user", "content": question}])

    def model_stats(self) -> tuple[int | None, int | None]:
        stats = getattr(self._last, "last_stream_stats", None)
        if stats is None:
            return None, None
        return getattr(stats, "t_first_ms", None), getattr(stats, "tokens", None)


class HttpDriver:
    """Fährt den laufenden Server über die OpenAI-kompatible Route (#37).

    `model` ist dort der Persona-Name — dieselbe Konvention wie im Rest des
    Projekts. Die Modell-Kennzahlen bleiben leer: über HTTP ist nur zu sehen,
    wann das erste Zeichen ankommt, nicht wann das Modell es erzeugt hat. Genau
    diese Lücke ist der Grund, warum der in-process-Modus der Standard ist.
    """

    mode = "http"

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def stream(self, persona: str, question: str) -> Iterator[str]:
        import requests

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": persona,
                "messages": [{"role": "user", "content": question}],
                "stream": True,
            },
            stream=True,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return self._iter_sse(response)

    @staticmethod
    def _iter_sse(response: Any) -> Iterator[str]:
        try:
            for raw in response.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                token = (choices[0].get("delta") or {}).get("content") or ""
                if token:
                    yield token
        finally:
            response.close()

    def model_stats(self) -> tuple[int | None, int | None]:
        return None, None
