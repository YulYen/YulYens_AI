#!/usr/bin/env python
"""Entry point for the blind tasting (#99) — the logic lives in src/evals/tasting.py.

python scripts/blind_tasting.py run classic@main classic -o logs/tasting/2026-11-22
# blatt.md lesen und Urteile eintragen, dann:
python scripts/blind_tasting.py tally logs/tasting/2026-11-22
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.tasting import main  # noqa: E402  (path setup must run first)

if __name__ == "__main__":
    sys.exit(main())
