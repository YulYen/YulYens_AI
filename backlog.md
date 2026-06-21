# backlog.md

Priorisiert nach Aufwand/Nutzen, Risiko und Reifegrad. Die Reihenfolge ist von
oben (zuerst angehen) nach unten (später) gruppiert. Die `No.`-Spalte ist eine
stabile ID und ändert sich nicht beim Umsortieren.

## Tier A — Sicherheit & Korrektheit (zuerst)

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 18 | Wrongdoing guardrail (violence/weaponization) | Add a minimal deterministic guardrail for violent wrongdoing requests (e.g., weapons/explosives/attack instructions). Implement as pre-LLM input check + session lock (once triggered, keep blocking follow-ups like "it's for a novel"). Provide safe alternative response templates and add unit tests for common bypass patterns. **DONE: `wrongdoing_protection` in `tinyguard.py` (EN/DE verb+objekt-Patterns, Session-Lock via `_wrongdoing_locked`/`reset_session`), Locale-Template `security_wrongdoing`, Config-Flag, 17 Unit-Tests in `tests/test_wrongdoing_guard.py`. Default on.** | S | M | Security/Robustness |
| 19 | Drei-Zeitstempel-Transparenz | Personas verwechseln Tagesdatum, Modell-Trainings-Cutoff und Kiwix-Datenstand. Alle drei Werte im System-Prompt klar trennen und Persona-Formulierungen testen, damit kein Modell behauptet sein Wissen reiche bis heute. | M | M | Quality/Correctness |

## Tier B — Quick Wins & „fast fertig" abschließen

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 2 | Web-UI "New conversation" in stream | End streaming cleanly so that the "New conversation" button works. **Stand: ~80 % — Button + Reset funktionieren, aber ein aktiver Stream wird beim Klick nicht aktiv abgebrochen (nur UI-State reset).** | M | L | Bugfix |
| 9 | Ask-all (broadcast): WebUI Wiki + Streaming | TerminalUI-Flow läuft. Offen: Wiki-Kontext im Broadcast (orchestrator.py kennt kein Wiki), Live-Streaming im WebUI (aktuell erst nach Completion sichtbar). | S | M | Orchestration |
| 20 | Ask-all results table polish | Ergebnis-Tabelle der Broadcast-Ansicht hübscher/robuster: read-only statt editierbare `gr.Dataframe` (kein "New row/New column"), Markdown in Zellen rendern (aktuell literale `*Sternchen*`), ggf. Persona-Avatare. Nebenbei Console-Warnung `Too many arguments provided for the endpoint` aufklären. | S | S | UX/Technology |
| 5 | Health checks/monitoring | Status page (Ollama/VRAM), simple `/healthz` endpoint plus VRAM probe. **Stand: ~20 % — nur statischer `/health`-Stub, keine Ollama-/VRAM-Probe.** | S | M | Technical foundation |
| 21 | Setup-Doktor / Preflight-Check | `python src/launch.py --doctor`: prüft beim Start Ollama-Erreichbarkeit, ob das konfigurierte Modell gepullt ist, spaCy-Modell vorhanden, Kiwix erreichbar, Config valide — mit konkreten Fix-Hinweisen statt kryptischer Tracebacks. Senkt Onboarding-Friktion für ein selbst-gehostetes Offline-Projekt; baut auf der `/health`-Logik aus #5 auf. | S | L | Technical foundation |
| 14 | Email to/from AI | DONE (MVP): `src/email_adapter/service.py` auf main, end-to-end live getestet (KAS-Postfach, LEAH antwortet via IMAP/SMTP). Helfer-Skripte `scripts/mail_smoketest.py` (Login-Check) + `scripts/mail_runonce.py` (1 Poll). Default `enabled: false`. Offen: (a) `processed_mailbox` mit KAS/Dovecot-Punkt-Trenner (`INBOX.YulYenProcessed`) scharf testen; (b) Dauerbetrieb via `launch.py` verifizieren; (c) Postfach-Passwort rotieren (stand im Chat). | S | M | Integration |

## Tier C — Strategische Hebel (größerer Aufwand, hoher Nutzen)

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 7 | LoRA fine-tuning pipeline | IN PROGRESS → LoRA adapter for LeoLM13B | L | XL | Research/Quality |
| 17 | Faster first token | Warm-up, prompt diet, stream buffer | M | L | Performance |
| 12 | Karl (context summarizer) | Compress history on demand with an LLM summary instead of the current approach | L | L | Technical foundation |

## Tier D — Nice-to-have / Cool features (später)

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 6 | Model selection in the UI | Dropdown/radio for available models, explicitly selectable per persona and run | S | S | UX/Technology |
| 13 | STT MVP | Simple speech Input | M | M | Cool feature |
| 15 | Daily briefing (IoT + RSS) | Daily short updates | M | M | Cool feature |
| 16 | Sandbox/PDF functions | Local documentation sandbox | L | M | Cool feature |

## Gestrichen

| No. | Name | Grund |
| --- | --- | --- |
| 11 | Easter egg logic | Reine Spielerei (Keyword → Extra-Tagline), 0 % umgesetzt, M-Aufwand für minimalen Nutzen — schlechtester Aufwand/Nutzen im Backlog. Bei Bedarf später als triviales Add-on. |
