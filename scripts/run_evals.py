#!/usr/bin/env python
"""Entry point for the eval suite (#41).

python scripts/run_evals.py -e classic
python scripts/run_evals.py -e classic --guard-only   # needs no model
"""

from __future__ import annotations

import sys

from yulyen_ai.evals.cli import main

if __name__ == "__main__":
    sys.exit(main())
