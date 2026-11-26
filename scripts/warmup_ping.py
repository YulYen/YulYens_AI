#!/usr/bin/env python
"""Warmup-Ping: lädt das Chat-Modell in Ollama vor, ohne die App zu starten.

Ein Modell, das nicht ganz in den VRAM passt (der Default ``gemma4:26b`` auf
einer 16-GB-Karte), braucht beim ersten Laden von der Platte gut 100 Sekunden.
Dieses Skript zahlt die Zeit vorher — beim Windows-Start, beim Öffnen von
VS Code oder von Hand —, damit die App danach ein warmes Modell vorfindet.

    python scripts/warmup_ping.py                    # Modell aus config(.local).yaml
    python scripts/warmup_ping.py --keep-alive 7200  # zwei Stunden geladen halten
    python scripts/warmup_ping.py -e examples/classic_ministral14b

Vorgewärmt wird über ``AppFactory.warm_up_model`` — derselbe Weg wie beim
App-Start, mit dem größten ``num_ctx`` aller Personas. Das ist der Punkt: Lädt
der Ping das Modell mit einem anderen Kontextfenster als die erste echte
Anfrage, lädt Ollama es dann ein zweites Mal, und der Ping war umsonst.

``--keep-alive`` ist bewusst länger als ``core.keep_alive`` (600 s): Wer beim
Hochfahren vorwärmt, startet die App selten in den nächsten zehn Minuten.
Sobald die App läuft, setzt jede Anfrage den Zähler wieder auf ihren Wert.
Ein Fehler (Ollama aus, Modell fehlt) bricht nichts ab — es steht im Log, der
Ping endet trotzdem mit 0, damit ein Autostart nicht mit einer Fehlermeldung
aufpoppt.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from yulyen_ai.paths import PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lädt das Chat-Modell in Ollama vor, ohne die App zu starten."
    )
    parser.add_argument(
        "-e",
        "--ensemble",
        default="classic",
        help="Ensemble, dessen größtes num_ctx gilt (Default: classic).",
    )
    parser.add_argument(
        "--keep-alive",
        type=int,
        default=3600,
        help="Sekunden, die Ollama das Modell danach hält (Default 3600, -1 = immer).",
    )
    args = parser.parse_args(argv)

    # Autostart und VS-Code-Task starten in beliebigen Verzeichnissen;
    # config.yaml und das Ensemble liegen relativ zum Repo.
    os.chdir(PROJECT_ROOT)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from yulyen_ai.config.config_singleton import Config
    from yulyen_ai.core.factory import AppFactory

    cfg = Config("config.yaml")
    cfg.ensemble = args.ensemble
    cfg.override("core", {"keep_alive": args.keep_alive})

    model = cfg.core["model_name"]
    print(f"Wärme {model} vor …", flush=True)
    started = time.monotonic()
    AppFactory().warm_up_model()
    print(
        f"Fertig nach {time.monotonic() - started:.0f} s. "
        f"Ollama hält {model} für {args.keep_alive} s."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
