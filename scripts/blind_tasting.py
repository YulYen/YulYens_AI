#!/usr/bin/env python
"""Entry point for the blind tasting (#99) — the logic lives in src/yulyen_ai/evals/tasting.py.

python scripts/blind_tasting.py run classic@main classic -o logs/tasting/2026-11-22
# blatt.md lesen und Urteile eintragen, dann:
python scripts/blind_tasting.py tally logs/tasting/2026-11-22
"""

from __future__ import annotations

import sys

from yulyen_ai.evals.tasting import main

if __name__ == "__main__":
    sys.exit(main())
