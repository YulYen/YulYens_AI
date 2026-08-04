"""Welche optionalen Funktionen die WebUI anbietet — und warum nicht (#56).

Sechs Fragen, die vorher in `WebUI.__init__` nebeneinander lagen und jede
anders beantwortet wurde: mal aus der Config, mal aus einem installierten
Paket, mal aus der Ablage. Als lose Bools am Objekt war das schwer zu
überblicken und noch schwerer zu erweitern — wer eine siebte Funktion ergänzt,
sieht nirgends, dass es dazu ein *Muster* gibt.

**Das Muster ist der zweistufige Schalter.** Drei der sechs Funktionen hängen
nicht nur an der Config, sondern zusätzlich an etwas, das da sein muss:

| Funktion | Config sagt ja | …und außerdem |
|---|---|---|
| Vorlesen | `tts.enabled` + `tts.features.web_read_aloud` | `piper` installiert |
| Mikrofon | `stt.enabled` | `faster-whisper` installiert |
| Verlauf | `storage.enabled` | die Ablage zeichnet wirklich auf (#72) |

Für diese drei gilt: **eingeschaltet, aber nicht verfügbar ist eine Meldung
wert.** Sonst sucht jemand eine halbe Stunde nach einem Mikrofon, das nie
erscheinen kann, weil ein `pip install` fehlt. Vorher standen dafür zwei
handgeschriebene `if`-Blöcke im Konstruktor (und für den Verlauf gar keiner);
hier ist es eine Zeile pro Funktion, und `_notes` sammelt sie an einer Stelle.

**Nicht hier: die beiden RSS-Schalter.** `rss_enabled` und `briefing_enabled`
leiten sich aus dem Feed-Cache ab, den der `ChatController` ohnehin hält — sie
dort zu berechnen ist eine Zeile, sie hierher zu holen hieße, den Cache an zwei
Objekte zu geben. Wer sie sucht: `ui/webui_chat.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils import (
    is_broadcast_enabled,
    is_broadcast_parallel,
    is_file_exchange_enabled,
    module_available,
)
from stt.whisper_stt import is_stt_available

if TYPE_CHECKING:
    from config.config_singleton import Config


@dataclass(frozen=True)
class WebFeatures:
    """Die Antworten, auf die das Layout seine Sichtbarkeit stützt.

    ``frozen``, weil eine Funktion nicht mitten im Betrieb auftaucht: alles
    hier steht beim Start fest. Ein Test, der eine Funktion umschalten will,
    baut ein neues Exemplar (``replace()``) — das ist eine Zeile und sagt
    deutlicher, was gemeint ist, als ein nachträgliches Feld-Setzen.
    """

    history: bool
    file_exchange: bool
    broadcast: bool
    broadcast_parallel: bool
    stt: bool
    tts_read_aloud: bool

    @classmethod
    def detect(cls, cfg: Config, store: Any) -> WebFeatures:
        stt_cfg = getattr(cfg, "stt", {}) or {}
        tts_cfg = getattr(cfg, "tts", {}) or {}
        tts_features = tts_cfg.get("features", {}) or {}

        # Jede Zeile: was die Config will — und was zusätzlich da sein muss.
        wanted_stt = bool(stt_cfg.get("enabled"))
        wanted_tts = bool(tts_cfg.get("enabled")) and bool(
            tts_features.get("web_read_aloud")
        )
        # Der Verlauf ist der Sonderfall: die Config kann `storage.enabled: true`
        # sagen und die Ablage trotzdem nichts aufzeichnen, weil ohne Anmeldung
        # alle Besucher derselbe Nutzer wären (#72). `records` ist die ehrliche
        # Antwort, `storage.enabled` nur die Absicht.
        wanted_history = bool((getattr(cfg, "storage", {}) or {}).get("enabled", True))

        features = cls(
            history=bool(getattr(store, "records", False)),
            file_exchange=is_file_exchange_enabled(cfg),
            broadcast=is_broadcast_enabled(cfg),
            broadcast_parallel=is_broadcast_parallel(cfg),
            stt=wanted_stt and is_stt_available(),
            tts_read_aloud=wanted_tts and module_available("piper"),
        )
        for note in features._notes(
            stt=wanted_stt, tts=wanted_tts, history=wanted_history
        ):
            logging.info(note)
        return features

    def _notes(self, *, stt: bool, tts: bool, history: bool) -> list[str]:
        """„Du hast es eingeschaltet, aber es kann nicht erscheinen."

        Getrennt von `detect`, damit ein Test die Meldungen prüfen kann, ohne
        sich am Logging festzuhalten — und damit sichtbar bleibt, dass alle
        drei Fälle dieselbe Form haben.
        """
        notes: list[str] = []
        if tts and not self.tts_read_aloud:
            notes.append(
                "TTS-Vorlesen aktiviert, aber piper ist nicht installiert — "
                "Button bleibt ausgeblendet (pip install piper-tts)."
            )
        if stt and not self.stt:
            notes.append(
                "STT aktiviert, aber faster-whisper ist nicht installiert — "
                "Mikrofon bleibt ausgeblendet (pip install faster-whisper)."
            )
        if history and not self.history:
            # Der Fall, für den es vorher gar keine Meldung gab. Die Ablage
            # sagt beim Bauen selbst, *warum* sie nichts aufzeichnet (#72);
            # hier steht nur, was das für die Oberfläche bedeutet.
            notes.append(
                "Ablage eingeschaltet, zeichnet aber nichts auf — die "
                "Verlauf-Karte bleibt deshalb weg (Grund siehe [STORE] oben)."
            )
        return notes
