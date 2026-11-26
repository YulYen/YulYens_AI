#!/usr/bin/env python
"""Einstieg für die Stoppuhr (#42).

Misst die Antwortzeiten des Streaming-Pfads: Zeit bis zum ersten
*ausgelieferten* Zeichen und Durchsatz. Braucht Ollama — außer mit
``--backend dummy``, das nur zeigt, dass der Harness läuft.

    python scripts/run_bench.py -e classic
    python scripts/run_bench.py -e classic --model leo-hessianai-13b-chat.Q5
    python scripts/run_bench.py -e classic --holdback 0        # die Tabelle aus #51
    python scripts/run_bench.py -e classic --api-url http://127.0.0.1:8013/v1

Was gemessen wird und was nicht: src/yulyen_ai/bench/harness.py.
"""

from __future__ import annotations

import sys

from yulyen_ai.bench.cli import main

if __name__ == "__main__":
    sys.exit(main())
