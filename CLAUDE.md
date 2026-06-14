# CLAUDE.md — Yul Yen's AI Orchestra

Dieses Dokument ist der Einstiegspunkt für Claude Code in diesem Projekt.

## Was ist dieses Projekt?

**Yul Yen's AI Orchestra** ist ein lokal laufendes Multi-Persona-KI-Chatsystem.
Es betreibt 4 KI-Charaktere (LEAH, DORIS, PETER, POPCORN) über lokale LLMs via Ollama.
Kein Cloud-Zwang. Offline-Wikipedia via Kiwix integriert. Zwei UIs: Terminal und Gradio-Web.

**Start:** `python src/launch.py -e classic`

## Technologie-Stack

| Bereich | Tech |
|---|---|
| Sprache | Python 3.10+ |
| LLM-Backend | Ollama (lokal) |
| Web-UI | Gradio 4.44 |
| API | FastAPI + Uvicorn |
| NLP/Wiki | spaCy + Kiwix/Wikipedia |
| TTS | Piper (ONNX, Windows) |
| Security | BasicGuard (tinyguard.py) |
| Tests | pytest |
| Formatting | Black (88), Ruff |

## Verzeichnisstruktur

```
c:\J_KI\
├── src/
│   ├── launch.py              # Haupteinstiegspunkt
│   ├── core/
│   │   ├── llm_core.py        # Abstrakte LLM-Schnittstelle
│   │   ├── ollama_llm_core.py # Ollama-Implementierung
│   │   ├── dummy_llm_core.py  # Mock-LLM für Tests
│   │   ├── streaming_provider.py  # Kern-Streamer (Logging, Security, Wiki)
│   │   ├── orchestrator.py    # Broadcast an alle Personas
│   │   ├── factory.py         # AppFactory (Lazy Singletons)
│   │   ├── context_utils.py   # Token-Zählung
│   │   └── utils.py           # Hilfsfunktionen
│   ├── config/
│   │   ├── config_singleton.py  # YAML-Config (Singleton, reset_instance() für Tests)
│   │   ├── personas.py          # Ensemble-Loader
│   │   ├── texts.py             # i18n (MutableMapping)
│   │   └── logging_setup.py
│   ├── ui/
│   │   ├── web_ui.py            # Gradio-UI
│   │   ├── terminal_ui.py       # Terminal-UI (farbig)
│   │   ├── webui_layout.py      # Gradio-Layout-Builder
│   │   ├── conversation_io_terminal.py  # JSON-Speichern/Laden
│   │   └── self_talk.py         # AI-Dialog-Modus
│   ├── api/
│   │   ├── app.py               # FastAPI: /ask, /health
│   │   └── provider.py
│   ├── wiki/
│   │   ├── wikipedia_proxy.py   # HTTP-Proxy (Port 8042)
│   │   ├── spacy_keyword_finder.py  # NLP-Schlüsselwortextraktion
│   │   └── kiwix_autostart.py
│   ├── security/
│   │   └── tinyguard.py         # BasicGuard (Prompt-Injection, PII, Blocklist)
│   └── tts/
│       ├── piper_tts.py         # TTS-Wrapper
│       └── audio_player.py      # Windows winsound
├── ensembles/
│   └── classic/
│       ├── personas_base.yaml   # LLM-Optionen pro Persona
│       └── locales/{de,en}/personas.yaml  # Lokalisierte Prompts
├── tests/
│   ├── conftest.py              # Fixtures: client, client_with_date_and_wiki
│   └── test_*.py                # 13 Testmodule
├── locales/
│   ├── de.yaml                  # 83+ UI-Texte Deutsch
│   └── en.yaml                  # UI-Texte Englisch
├── config.yaml                  # Hauptkonfiguration
├── pyproject.toml               # Black/Ruff-Konfiguration
├── pytest.ini                   # Test-Konfiguration
├── Makefile                     # make format / make lint / make fix
└── backlog.md                   # Feature-Backlog mit Effort/Benefit
```

## Die 4 Personas (Ensemble "classic")

| Name | Charakter | Temperatur | Besonderheit |
|---|---|---|---|
| **LEAH** | Warmherzig, kreativ | 0.65 | `featured: true` (Standard) |
| **DORIS** | Bodenständig, direkt | 0.60 | |
| **PETER** | Sachlich, präzise | 0.10 | Niedrige Temp. = faktenorientiert |
| **POPCORN** | Verspielt, witzig | 0.80 | Höchste Kreativität |

Alle Personas: `repeat_penalty: 1.15`, `num_ctx: 8192`.

## Wichtige Architektur-Muster

### Config-Singleton
```python
cfg = Config("config.yaml")   # Einmal laden
cfg.ensemble = "classic"
cfg.override("core", {"backend": "dummy"})  # für Tests
Config.reset_instance()        # in Tests: Isolation
```

### LLM-Abstraktion
- `LLMCore` (abstrakt) → `OllamaLLMCore` (Produktion) / `DummyLLMCore` (Tests)
- Swappable ohne UI/API-Änderungen

### Streaming-Flow
```
User-Input → SecurityGuard (pre-check) → spaCy → Wiki-Proxy (8042) → Ollama
           → Token-Stream → SecurityGuard (post-check) → UI + TTS + JSON-Log
```

### AppFactory
- Baut und cached alle Komponenten (Streamer, UI, API-Provider)
- Zustand in Tests via `set_provider(None)` + `Config.reset_instance()` zurücksetzen

## Tests ausführen

```bash
pytest -q                     # Schnelldurchlauf (Dummy-Backend)
pytest -m "not slow"          # Ohne langsame Tests
pytest -m "ollama"            # Nur wenn Ollama läuft
pytest tests/test_ai_via_api.py  # Gezielt
```

- Test-Fixture `client`: Dummy-Backend, Wiki deaktiviert
- Test-Fixture `client_with_date_and_wiki`: echte Wiki-Integration (braucht spaCy-Modell)
- Marker `@pytest.mark.ollama`: wird geskippt wenn Ollama nicht erreichbar

## Konfiguration (config.yaml)

Wichtige Schalter:

```yaml
core:
  backend: "ollama"          # oder "dummy" für Tests
  model_name: "ministral-3:8b"
  include_date: true         # Datum in System-Prompts

ui:
  type: web                  # "web" | "terminal" | null (API-only)
  experimental:
    broadcast_mode: true     # Ask-All aktivieren

wiki:
  mode: offline              # "offline" (Kiwix) | "online" (Wikipedia) | false
  proxy_port: 8042

tts:
  enabled: true
  features:
    terminal_auto_create_wav: true  # WAV in out/ bei jeder Antwort

api:
  enabled: true
  port: 8013

security:
  enabled: true
  guard: BasicGuard
```

## Code-Stil

- **Black** mit `line-length = 88`
- **Ruff** Regeln: E, F, I (Imports), UP (pyupgrade), ISC
- `make format` → Black + Ruff-Fix
- `make lint` → Ruff check only
- Keine Docstrings für einfache Methoden, kurze Inline-Kommentare nur wenn nötig

## Feature-Modi

| Modus | Beschreibung |
|---|---|
| **Chat** | Einzelne Persona, Streaming |
| **AI-Dialog** | Zwei Personas konversieren automatisch (`_endegelaende_` = Stop) |
| **Broadcast/Ask-All** | Eine Frage an alle Personas, Ergebnisse als Tabelle |

## Backlog (wichtigste offene Punkte)

Siehe [backlog.md](backlog.md) für vollständige Liste mit Effort/Benefit-Matrix. Highlights:

- **#9** Ask-All: Wiki-Unterstützung fehlt noch, WebUI-Streaming
- **#12** Karl: Context-Kompressor (LLM-basiert)
- **#13** STT MVP: Spracheingabe
- **#18** Wrongdoing-Guardrail: Waffen-/Gewaltfilter mit Session-Lock
- **#7** LoRA-Finetuning: In Arbeit (LeoLM13B)

## Sprachstrategie

- Projekt-Sprache in `config.yaml`: `language: "de"` (Standard)
- Locale-Dateien: `locales/de.yaml`, `locales/en.yaml`
- Persona-Prompts lokalisiert in `ensembles/classic/locales/{de,en}/personas.yaml`
- UI-Texte via `Config.t()` formatiert

## Wichtige API-Endpunkte

```
POST http://127.0.0.1:8013/ask
  Body: { "persona": "LEAH", "message": "Hallo", "history": [] }
  
GET  http://127.0.0.1:8013/health
```

## Logging

Alle Logs in `logs/`:
- `yulyen_ai_YYYY-MM-DD_HH-MM.log` — Systemlog
- `conversation_[PERSONA]_[TIMESTAMP].json` — Gesprächslog (JSON)
- `wiki_proxy_[TIMESTAMP].log` — Wiki-Proxy-Log
