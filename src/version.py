"""Die Version dieses Stands — eine Zahl, eine Quelle (#74).

**Warum hier und nicht in `pyproject.toml`:** dort gibt es keinen
`[project]`-Abschnitt, nur `[tool.*]`. Einen anzulegen, bloß um diese Zeile
unterzubringen, würde behaupten, das Projekt sei ein Paket — es wird aber
geklont und über `requirements.txt` installiert. Die Paketierung ist ein
eigener Umbau (#44 Teil 2), und dann zieht die Zahl dorthin um.

**Das Modul importiert bewusst nichts.** Damit darf jede Schicht es lesen, ohne
einen der Verträge aus `[tool.importlinter]` zu verletzen — auch der Guard, der
sonst nur die Config kennen darf.

`CHANGELOG.md` trägt dieselbe Zahl als oberste Versionsüberschrift.
`tests/test_version_consistency.py` hält beide zusammen: zwei Quellen für
dieselbe Wahrheit laufen auseinander, wenn nichts sie aneinander bindet — die
Lehre aus `KNOWN_TOP_LEVEL_KEYS` (#66).
"""

from __future__ import annotations

__version__ = "2.0.0"
