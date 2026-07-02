"""Verbindungs-Smoke-Test für den Persona-E-Mail-Adapter.

Prüft NUR die IMAP- und SMTP-Logins und zählt ungelesene Mails.
Es wird KEINE E-Mail verschickt und nichts verändert.

Aufruf (aus dem Projekt-Root, mit gesetzten YULYEN_MAIL_*-Variablen):
    python scripts/mail_smoketest.py
"""

from __future__ import annotations

import smtplib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from email_adapter.service import EmailAdapterConfig, open_imap  # noqa: E402


def main() -> int:
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg = EmailAdapterConfig.from_mapping(raw.get("email_adapter", {}))

    print("=== Konfiguration (aufgelöst) ===")
    print(
        f"  IMAP : {cfg.imap_host}:{cfg.imap_port}  user={cfg.imap_username or '(leer!)'}"
    )
    print(
        f"  SMTP : {cfg.smtp_host}:{cfg.smtp_port}  user={cfg.smtp_username or '(leer!)'}"
    )
    print(f"  From : {cfg.smtp_from_address}")
    print(f"  Map  : {cfg.address_persona_map}")
    print(f"  IMAP-Passwort gesetzt: {'ja' if cfg.imap_password else 'NEIN'}")
    print(f"  SMTP-Passwort gesetzt: {'ja' if cfg.smtp_password else 'NEIN'}")
    print()

    ok = True

    # --- IMAP ---------------------------------------------------------------
    print("--- IMAP-Login ---")
    try:
        imap = open_imap(cfg)
        imap.login(cfg.imap_username, cfg.imap_password)
        status, data = imap.select(cfg.source_mailbox, readonly=True)
        print(f"  Login OK. SELECT {cfg.source_mailbox}: status={status}")
        s, d = imap.uid("search", None, "UNSEEN")
        n = len(d[0].split()) if (s == "OK" and d and d[0]) else 0
        print(f"  Ungelesene Mails in {cfg.source_mailbox}: {n}")
        imap.logout()
    except Exception as exc:
        ok = False
        print(f"  IMAP FEHLER: {type(exc).__name__}: {exc}")
    print()

    # --- SMTP (nur Login, kein Versand) -------------------------------------
    print("--- SMTP-Login ---")
    try:
        if cfg.smtp_ssl:
            smtp = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20)
        if cfg.smtp_starttls:
            smtp.starttls()
        smtp.login(cfg.smtp_username, cfg.smtp_password)
        print("  Login OK. (Es wurde KEINE Mail gesendet.)")
        smtp.quit()
    except Exception as exc:
        ok = False
        print(f"  SMTP FEHLER: {type(exc).__name__}: {exc}")
    print()

    print("=== Ergebnis:", "ALLES GRÜN ✅" if ok else "FEHLER ❌", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
