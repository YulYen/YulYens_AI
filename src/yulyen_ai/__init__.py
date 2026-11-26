"""Yul Yen's AI Orchestra — das Paket.

Alles Laufzeitliche liegt unter diesem einen Namen (`yulyen_ai.core`,
`yulyen_ai.ui`, …). Vorher lagen die Teilpakete als `core`, `config`, `ui` …
direkt in `src/` und waren nur über `PYTHONPATH=src` oder `sys.path`-Griffe
importierbar; installiert hätten sie Allerweltsnamen in jedes venv gelegt, in
dem auch ein fremdes Paket `config` liegen kann.

Installiert wird editierbar: `pip install -e .` (siehe `paths.py`, warum nie
als Wheel). Gestartet wird mit `python -m yulyen_ai`.

Dieses Modul importiert bewusst nichts — `import yulyen_ai.version` soll nicht
die halbe App laden.
"""
