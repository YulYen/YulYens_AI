# backlog.md

Priorisiert nach Aufwand/Nutzen, Risiko und Reifegrad. Die Reihenfolge ist von
oben (zuerst angehen) nach unten (später) gruppiert. Die `No.`-Spalte ist eine
stabile ID und ändert sich nicht beim Umsortieren. (Stand: 2026-07-04)

## Tier A — Sicherheit & Korrektheit (zuerst)

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 18 | Wrongdoing guardrail (violence/weaponization) | Add a minimal deterministic guardrail for violent wrongdoing requests (e.g., weapons/explosives/attack instructions). Implement as pre-LLM input check + session lock (once triggered, keep blocking follow-ups like "it's for a novel"). Provide safe alternative response templates and add unit tests for common bypass patterns. **DONE: `wrongdoing_protection` in `tinyguard.py` (EN/DE verb+objekt-Patterns, Session-Lock via `_wrongdoing_locked`/`reset_session`), Locale-Template `security_wrongdoing`, Config-Flag, 17 Unit-Tests in `tests/test_wrongdoing_guard.py`. Default on.** | S | M | Security/Robustness |
| 19 | Drei-Zeitstempel-Transparenz | Personas verwechseln Tagesdatum, Modell-Trainings-Cutoff und Kiwix-Datenstand. Alle drei Werte im System-Prompt klar trennen. **DONE: `_system_prompt_with_date` (src/core/utils.py) baut einen beschrifteten Drei-Stempel-Block — Datum aus Systemuhr, Cutoff aus Per-Modell-Map `core.knowledge_cutoffs`, Wiki-Stand aus `zim_prefix` (Regex) bzw. live/aus. Fehlende Werte ehrlich als 'unbekannt' benannt, Guidance-Satz gegen Verwechslung. 7 Locale-Keys (de/en), 17 Tests inkl. End-to-End über Factory. Verhaltensbeweis am echten LLM steht noch aus (braucht Ollama).** | M | M | Quality/Correctness |

## Tier B — Quick Wins & „fast fertig" abschließen

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 2 | Web-UI "New conversation" in stream | End streaming cleanly so that the "New conversation" button works. **DONE: "New conversation" (Chat/Self-Talk) und Ask-All-Reset brechen laufende Streams jetzt aktiv ab (`cancels=[…]` in `web_ui.py:_bind_events`); der geschlossene Generator beendet über das `finally` in `YulYenStreamingProvider.stream` auch den Ollama-Stream.** | M | L | Bugfix |
| 9 | Ask-all (broadcast): WebUI Wiki + Streaming | TerminalUI-Flow läuft. **DONE: Wiki-Kontext im Broadcast — Lookup läuft einmal pro Frage (WebUI `_on_submit_ask_all` + Terminal `_run_ask_all_flow`), Snippets gehen via `context_messages` durch `orchestrator.py` an alle Personas, Hints erscheinen im Status/Terminal. Live-Streaming im WebUI war bereits umgesetzt (`iter_broadcast_events` streamt tokenweise in Markdown-Sektionen, gedrosseltes Update).** | S | M | Orchestration |
| 20 | Ask-all results table polish | **DONE (2026-07-04, anders als geplant): Die editierbare `gr.Dataframe` wurde komplett durch live gestreamte `gr.Markdown`-Sektionen ersetzt — die Dataframe-Komponente verliert in Gradio 4.44 Streaming-Updates aus Generatoren (per Minimal-Repro bestätigt) und hatte einen festen 500px-Scroll-Viewport. Ergebnis: read-only, Markdown sauber gerendert, keine Scrollbalken. Persona-Avatare entfallen (kein Tabellen-Layout mehr). Die Console-Warnung `Too many arguments provided for the endpoint` tritt weiterhin vereinzelt auf (Gradio-intern, keine beobachtete Auswirkung).** | S | S | UX/Technology |
| 5 | Health checks/monitoring | Status page (Ollama/VRAM), simple `/healthz` endpoint plus VRAM probe. **DONE: `/healthz` (FastAPI) liefert aggregierten Status (ok/degraded/error, HTTP 503 bei kritischem Ausfall) aus gemeinsamem `core/system_checks.py` (Ollama erreichbar, Modell gepullt, spaCy, Kiwix, VRAM via nvidia-smi). `/health` bleibt als günstiger Liveness-Stub.** | S | M | Technical foundation |
| 21 | Setup-Doktor / Preflight-Check | `python src/launch.py --doctor`: prüft Ollama-Erreichbarkeit, ob das konfigurierte Modell gepullt ist, spaCy-Modell, Kiwix, VRAM — mit konkreten Fix-Hinweisen statt kryptischer Tracebacks. **DONE: nutzt dasselbe `core/system_checks.py` wie #5, farbiger Report (colorama), Exit-Code 1 bei kritischem Ausfall. Schwere Imports (gradio/uvicorn) lazy gemacht, damit der Doktor auch bei kaputtem UI-Stack läuft.** | S | L | Technical foundation |
| 14 | Email to/from AI | DONE (MVP): `src/email_adapter/service.py` auf main, end-to-end live getestet (KAS-Postfach, LEAH antwortet via IMAP/SMTP). Helfer-Skript `scripts/mail_smoketest.py` (Login-Check). Default `enabled: false`. Offen: (a) `processed_mailbox` mit KAS/Dovecot-Punkt-Trenner (`INBOX.YulYenProcessed`) scharf testen; (b) Dauerbetrieb via `launch.py` verifizieren; (c) Postfach-Passwort rotieren (stand im Chat). | S | M | Integration |
| 22 | Kiwix/ZIM aktualisieren + Install/Update-Anleitung | Der Offline-Wikipedia-Dump (`wiki.offline.zim_prefix` = `wikipedia_de_all_nopic_2025-06`) ist ~1 Jahr alt → veralteter Wissensstand (jetzt auch im Prompt sichtbar, siehe #19). Aktuellen ZIM beziehen (Download-Mirror / `kiwix-manage`), `zim_prefix`/`zim_path` aktualisieren und eine kurze README-Anleitung zum Installieren/Updaten schreiben (inkl. Plattenplatz-Hinweis und Verifikation via `--doctor`/#21). | S | M | Integration/Docs |

## Tier C — Strategische Hebel (größerer Aufwand, hoher Nutzen)

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 7 | LoRA fine-tuning pipeline | IN PROGRESS → LoRA adapter for LeoLM13B | L | XL | Research/Quality |
| 17 | Faster first token | Warm-up, prompt diet, stream buffer | M | L | Performance |
| 12 | Karl (context summarizer) | Compress history on demand with an LLM summary instead of the current approach. **DONE (MVP): `KarlSummarizer` in `src/core/context_summarizer.py`, opt-in via `context_management.strategy: "karl"` (Standard bleibt `heuristic`), Fallback auf Heuristik bei Fehlern, Tests in `tests/test_context_summarizer.py`. Offen: Qualität der Zusammenfassungen am echten LLM bewerten.** | L | L | Technical foundation |

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
