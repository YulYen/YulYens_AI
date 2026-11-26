"""Die Version dieses Stands — eine Zahl, eine Quelle (#74).

**Warum hier und nicht in `pyproject.toml`:** `[project]` liest die Zahl per
`dynamic` von hier (`attr = "yulyen_ai.version.__version__"`). So gibt es sie
zur Laufzeit ohne `importlib.metadata` — das wüsste nach einem `git pull` ohne
Neuinstallation noch die alte Zahl.

**Das Modul importiert bewusst nichts.** Damit darf jede Schicht es lesen, ohne
einen der Verträge aus `[tool.importlinter]` zu verletzen — auch der Guard, der
sonst nur die Config kennen darf.

`CHANGELOG.md` trägt dieselbe Zahl als oberste Versionsüberschrift.
`tests/test_version_consistency.py` hält beide zusammen: zwei Quellen für
dieselbe Wahrheit laufen auseinander, wenn nichts sie aneinander bindet — die
Lehre aus `KNOWN_TOP_LEVEL_KEYS` (#66).
"""

from __future__ import annotations

__version__ = "3.0.0"
