#!/usr/bin/env python
"""Entry point for the eval suite (#41).

Adds ``src`` to sys.path so the suite runs from a plain checkout without
PYTHONPATH fiddling — same convenience as ``python src/launch.py``.

    python scripts/run_evals.py -e classic
    python scripts/run_evals.py -e classic --guard-only   # needs no model
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.cli import main  # noqa: E402  (path setup must run first)

if __name__ == "__main__":
    sys.exit(main())
