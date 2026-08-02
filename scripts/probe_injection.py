#!/usr/bin/env python
"""Einstieg für die Injektions-Probe (#60b).

Misst am echten Modell, ob eine im Fremdtext versteckte Anweisung befolgt wird —
und ob Rollentrennung (#60) oder Guard (#60a) das verhindern. Braucht Ollama.

    python scripts/probe_injection.py -e classic
    python scripts/probe_injection.py -e classic --repeats 3 --persona DORIS

Hintergrund und Deutung der Arme: src/evals/injection_probe.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evals.injection_probe import render, run_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="probe_injection",
        description="Misst Befolgung versteckter Anweisungen aus Fremdtext (#60b).",
    )
    parser.add_argument("-c", "--config", help="Pfad zur config.yaml.")
    parser.add_argument("-e", "--ensemble", help="Persona-Ensemble.")
    parser.add_argument("--persona", default="PETER", help="Persona (Default: PETER).")
    parser.add_argument(
        "--repeats", type=int, default=5, help="Läufe je Kombination (Default: 5)."
    )
    parser.add_argument("--out", help="Ergebnis zusätzlich in diese Datei schreiben.")
    args = parser.parse_args(argv)

    from config.config_singleton import Config
    from core.factory import AppFactory

    cfg = Config(path=os.path.abspath(args.config or "config.yaml"))
    cfg.ensemble = args.ensemble or getattr(cfg, "ensemble", None)
    if not cfg.ensemble:
        parser.error("Fehlt: --ensemble / -e (z. B. 'classic').")

    factory = AppFactory()
    result = run_probe(
        factory.get_llm_core(),
        cfg,
        persona=args.persona,
        repeats=max(1, args.repeats),
        keep_alive=int(cfg.core.get("keep_alive", 600)),
    )

    text = render(result)
    print(text)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        print(f"\nGeschrieben: {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
