#!/usr/bin/env python
"""Einstieg für die Stoppuhr (#42).

Misst die Antwortzeiten des Streaming-Pfads: Zeit bis zum ersten
*ausgelieferten* Zeichen und Durchsatz. Braucht Ollama — außer mit
``--backend dummy``, das nur zeigt, dass der Harness läuft.

    python scripts/run_bench.py -e classic
    python scripts/run_bench.py -e classic --model leo-hessianai-13b-chat.Q5
    python scripts/run_bench.py -e classic --holdback 0        # die Tabelle aus #51
    python scripts/run_bench.py -e classic --api-url http://127.0.0.1:8013/v1

Fügt ``src`` zu sys.path hinzu, damit der Lauf aus einem nackten Checkout
funktioniert — dieselbe Bequemlichkeit wie bei ``python src/launch.py``.

Was gemessen wird und was nicht: src/bench/harness.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bench.cli import main  # noqa: E402  (Pfad muss zuerst stehen)

if __name__ == "__main__":
    sys.exit(main())
