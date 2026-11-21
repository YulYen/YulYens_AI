#!/usr/bin/env python
"""Entry point for the MCP server (#39) — the code lives in src/mcp_adapter/.

pip install 'mcp>=2.3,<3'
claude mcp add yulyen -- python /pfad/zu/YulYens_AI/scripts/mcp_server.py -e classic
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Ein MCP-Client startet den Server aus seinem eigenen Arbeitsverzeichnis;
# config.yaml, logs/ und data/ liegen aber relativ zum Repo.
os.chdir(ROOT)

from mcp_adapter.server import main  # noqa: E402  (path setup must run first)

if __name__ == "__main__":
    sys.exit(main())
