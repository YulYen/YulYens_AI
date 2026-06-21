"""Einmaliger Live-Durchlauf des Persona-E-Mail-Adapters.

Pollt das Postfach GENAU EINMAL: ungelesene Mails an eine gemappte Adresse
werden von der Persona beantwortet (echter Versand!), danach beendet sich das
Skript. Braucht ein laufendes Ollama mit dem konfigurierten Modell und die
gesetzten YULYEN_MAIL_*-Umgebungsvariablen.

Aufruf (aus dem Projekt-Root):
    python scripts/mail_runonce.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config.config_singleton import Config  # noqa: E402
from core.factory import AppFactory  # noqa: E402
from email_adapter.service import EmailAdapterConfig, EmailAdapterService  # noqa: E402


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config(path=str(ROOT / "config.yaml"))
    cfg.ensemble = "classic"

    factory = AppFactory()
    provider = factory.get_one_shot_provider()

    email_cfg = EmailAdapterConfig.from_mapping(getattr(cfg, "email_adapter", {}))
    service = EmailAdapterService(email_cfg, provider)

    print(">>> Starte EINEN Poll-Durchlauf (Strg+C bricht ab)...\n")
    answered = service.run_once()
    print(f"\n>>> Fertig. Beantwortete Mails: {answered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
