#!/usr/bin/env python
"""Entry point for the MCP server (#39) — the code lives in src/yulyen_ai/mcp_adapter/.

pip install 'mcp>=2.3,<3'
claude mcp add yulyen -- python /pfad/zu/YulYens_AI/scripts/mcp_server.py -e classic
"""

from __future__ import annotations

import os
import sys

from yulyen_ai.mcp_adapter.server import main
from yulyen_ai.paths import PROJECT_ROOT

# Ein MCP-Client startet den Server aus seinem eigenen Arbeitsverzeichnis;
# config.yaml, logs/ und data/ liegen aber relativ zum Repo.
os.chdir(PROJECT_ROOT)

if __name__ == "__main__":
    sys.exit(main())
