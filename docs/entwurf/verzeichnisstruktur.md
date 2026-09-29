# Verzeichnisstruktur

Die Datei-für-Datei-Karte. `CLAUDE.md` trägt nur noch die Paketebene.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Verzeichnisstruktur

```
<repo-root>/
├── .claude/
│   ├── settings.json          # registriert den Sitzungs-Hook
│   └── hooks/session-start.sh # richtet die Sandbox ein (nur remote, siehe arbeitsweise.md)
├── src/
│   ├── launch.py              # Haupteinstiegspunkt (inkl. --doctor Systemcheck, --list-ensembles)
│   ├── core/
│   │   ├── llm_core.py        # Abstrakte LLM-Schnittstelle
│   │   ├── ollama_llm_core.py # Ollama-Implementierung
│   │   ├── dummy_llm_core.py  # Mock-LLM für Tests
│   │   ├── streaming_provider.py  # Kern-Streamer (Logging, Security, Wiki)
│   │   ├── orchestrator.py    # Broadcast an alle Personas
│   │   ├── ask_all_moderator.py  # Fazit über eine Ask-All-Runde (#27)
│   │   ├── factory.py         # AppFactory (Lazy Singletons)
│   │   ├── context_utils.py   # Token-Zählung
│   │   ├── context_summarizer.py  # "Karl": LLM-basierte Kontext-Zusammenfassung
│   │   ├── system_checks.py   # Deep-Checks für /healthz und --doctor
│   │   └── utils.py           # Hilfsfunktionen
│   ├── config/
│   │   ├── config_singleton.py  # YAML-Config (Singleton, reset_instance() für Tests)
│   │   ├── personas.py          # Ensemble-Loader
│   │   ├── schema.py            # pydantic-Prüfung für config.yaml + Ensembles
│   │   ├── texts.py             # i18n (MutableMapping)
│   │   └── logging_setup.py
│   ├── ui/
│   │   ├── web_ui.py            # Gradio-UI (Startseite, Ask-All, Verlauf, Gast)
│   │   ├── terminal_ui.py       # Terminal-UI (farbig)
│   │   ├── webui_layout.py      # Gradio-Layout-Builder + Ausgabe-Key-Listen
│   │   ├── webui_format.py      # Reine Formatierer (Statuszeile, Quellen, Markdown)
│   │   ├── webui_chat.py        # Stream-Lebenszyklus: Chat, Briefing, Nochmal (#56)
│   │   ├── webui_features.py    # Welche Funktionen verfügbar sind — und warum nicht (#56)
│   │   ├── session.py           # SessionContext: Zustand *einer* Browser-Sitzung
│   │   ├── feedback.py          # 👍/👎-Votes + Schlüssel in die Ablage (#40/#65)
│   │   ├── webui_events.py      # Verdrahtung der Gradio-Events (#56)
│   │   ├── history_access.py    # nutzergebundener Zugriff auf die Ablage (#25)
│   │   ├── conversation_io_terminal.py  # JSON-Im-/Export (Austausch, nicht Ablage)
│   │   ├── persona_chooser.py   # Geteilte interaktive Persona-Auswahl (Terminal)
│   │   └── self_talk.py         # AI-Dialog-Modus
│   ├── api/
│   │   ├── app.py               # FastAPI: /ask, /health, /healthz + /v1-Router
│   │   ├── openai_compat.py     # OpenAI-kompatible Endpunkte (#37)
│   │   └── provider.py          # One-Shot + stream_messages (Client-History)
│   ├── email_adapter/
│   │   └── service.py           # opt-in IMAP/SMTP-Bridge (Personas per Mail)
│   ├── wiki/
│   │   ├── lookup.py            # WikiLookup + Snippet-Abruf (WikiSnippet) + Injektion
│   │   ├── wikipedia_proxy.py   # HTTP-Proxy (Port 8042, nur 127.0.0.1, threaded)
│   │   ├── spacy_keyword_finder.py  # NLP-Schlüsselwortextraktion
│   │   └── kiwix_autostart.py
│   ├── auth/
│   │   └── provider.py         # Identitäts-Naht der WebUI (#53)
│   ├── storage/
│   │   └── store.py            # Gesprächs-Ablage in SQLite (#54)
│   ├── security/
│   │   └── tinyguard.py         # BasicGuard (Prompt-Injection, PII, Blocklist)
│   ├── tts/
│   │   ├── piper_tts.py         # TTS-Wrapper
│   │   └── audio_player.py      # WAV-Wiedergabe: winsound / CLI-Player-Dispatch (#34)
│   ├── stt/
│   │   └── whisper_stt.py       # Spracheingabe via faster-whisper (optional, lazy)
│   ├── rss/
│   │   ├── feeds.py             # RSS/Atom als Kontextquelle: Cache + Block (#73)
│   │   └── trigger.py           # Heuristik „ist das eine Nachrichtenfrage?"
│   ├── evals/                   # Eval-Suite (#41): Korpus-Loader, Judge, Runner, Report
│   ├── bench/                   # Stoppuhr (#42): Harness, Treiber, Fragensatz, Report
│   └── version.py               # __version__ — die einzige Quelle der Version (#74)
├── evals/                       # Eval-Korpora als YAML (siehe evals/ReadMe.md)
│   ├── personas/*.yaml          # Goldene Fragen pro Persona
│   ├── behaviour/*.yaml         # Verhaltensbeweise (drei Zeitstempel)
│   ├── karl_summary.yaml        # Qualität der Karl-Zusammenfassungen
│   └── guard_redteam.yaml       # Angriff → erwartetes Guard-Verhalten
├── scripts/
│   ├── run_evals.py             # Einstieg der Eval-Suite
│   └── run_bench.py             # Einstieg der Stoppuhr (#42)
├── ensembles/
│   └── classic/
│       ├── personas_base.yaml   # LLM-Optionen pro Persona
│       └── locales/{de,en}/personas.yaml  # Lokalisierte Prompts
├── tests/
│   ├── conftest.py              # Fixtures: client, client_with_date_and_wiki
│   └── test_*.py                # ein Modul je Bereich (inkl. test_web_ui_wiring.py,
│                                #   test_continuation.py, test_imports.py)
├── locales/
│   ├── de.yaml                  # UI-Texte Deutsch (Parität mit en.yaml, per Test)
│   └── en.yaml                  # UI-Texte Englisch
├── config.yaml                  # Hauptkonfiguration
├── pyproject.toml               # Black/Ruff + pytest-Konfiguration
├── Makefile                     # make setup / format / lint / types / test / test-ci / evals / bench / clean / run
├── docs/
│   ├── {de,en}/                 # Betreiber-Doku (ReadMe, Features, …)
│   └── entwurf/                 # Begründungen und Messungen hinter CLAUDE.md
├── CHANGELOG.md                 # nutzersichtbare Änderungen, englisch (#74)
├── backlog.md                   # offene Tickets mit Effort/Benefit
└── backlog_archiv.md            # erledigte Tickets — die Projektgeschichte
```
