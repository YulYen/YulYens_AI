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
<repo-root>/
├── src/
│   ├── launch.py              # Haupteinstiegspunkt (inkl. --doctor Systemcheck)
│   ├── core/
│   │   ├── llm_core.py        # Abstrakte LLM-Schnittstelle
│   │   ├── ollama_llm_core.py # Ollama-Implementierung
│   │   ├── dummy_llm_core.py  # Mock-LLM für Tests
│   │   ├── streaming_provider.py  # Kern-Streamer (Logging, Security, Wiki)
│   │   ├── orchestrator.py    # Broadcast an alle Personas
│   │   ├── factory.py         # AppFactory (Lazy Singletons)
│   │   ├── context_utils.py   # Token-Zählung
│   │   ├── context_summarizer.py  # "Karl": LLM-basierte Kontext-Zusammenfassung
│   │   ├── system_checks.py   # Deep-Checks für /healthz und --doctor
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
│   │   ├── persona_chooser.py   # Geteilte interaktive Persona-Auswahl (Terminal)
│   │   └── self_talk.py         # AI-Dialog-Modus
│   ├── api/
│   │   ├── app.py               # FastAPI: /ask, /health, /healthz
│   │   └── provider.py
│   ├── email_adapter/
│   │   └── service.py           # opt-in IMAP/SMTP-Bridge (Personas per Mail)
│   ├── wiki/
│   │   ├── wikipedia_proxy.py   # HTTP-Proxy (Port 8042)
│   │   ├── spacy_keyword_finder.py  # NLP-Schlüsselwortextraktion
│   │   └── kiwix_autostart.py
│   ├── security/
│   │   └── tinyguard.py         # BasicGuard (Prompt-Injection, PII, Blocklist)
│   └── tts/
│       ├── piper_tts.py         # TTS-Wrapper
│       └── audio_player.py      # winsound (Windows-only, plattform-sicher)
├── ensembles/
│   └── classic/
│       ├── personas_base.yaml   # LLM-Optionen pro Persona
│       └── locales/{de,en}/personas.yaml  # Lokalisierte Prompts
├── tests/
│   ├── conftest.py              # Fixtures: client, client_with_date_and_wiki
│   └── test_*.py                # 23 Testmodule
├── locales/
│   ├── de.yaml                  # 83+ UI-Texte Deutsch
│   └── en.yaml                  # UI-Texte Englisch
├── config.yaml                  # Hauptkonfiguration
├── pyproject.toml               # Black/Ruff + pytest-Konfiguration
├── Makefile                     # make format / lint / fix / test / test-all / clean / run
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
- spaCy-Modelle (`python -m spacy download de_core_news_lg`) schalten die
  Keyword-/Wiki-Tests frei; ohne Modell werden sie sauber geskippt

## Konfiguration (config.yaml)

Wichtige Schalter:

```yaml
core:
  backend: "ollama"          # oder "dummy" für Tests
  model_name: "ministral-3:8b"
  warm_up: true              # Modell beim Start im Hintergrund vorladen
  keep_alive: 600            # Sekunden im Speicher nach Request (-1 = für immer)
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

email_adapter:
  enabled: false             # opt-in IMAP/SMTP-Bridge (Personas per Mail)

context_management:
  strategy: "heuristic"      # "heuristic" (Default) | "karl" (LLM-Zusammenfassung)
```

### Lokales Override: `config.local.yaml` (gitignored)
Beim Laden wird ein optionales `config.local.yaml` (neben `config.yaml`) **per
Deep-Merge** über `config.yaml` gelegt (lokale Werte gewinnen). Damit bleiben
persönliche/geheime Werte (z. B. echter Mail-Host/-Adresse) aus der **öffentlichen**
`config.yaml` heraus, während die App lokal trotzdem läuft. `config.local.yaml` ist
in `.gitignore` — niemals committen. Passwörter weiterhin via `env:NAME`.

**Tests ignorieren das lokale Override:** Die Test-Suite setzt automatisch
`YULYEN_SKIP_LOCAL_CONFIG=1` (autouse-Fixture in `tests/conftest.py`), damit
eine persönliche `config.local.yaml` die Tests nicht anders laufen lässt als
in der CI (z. B. würde `api.enabled: false` sonst API-Tests brechen).

## Code-Stil

- **Black** mit `line-length = 88`
- **Ruff** Regeln: E, F, I (Imports), UP (pyupgrade), ISC
- `make format` → Black + Ruff-Fix
- `make lint` → Ruff check only
- Keine Docstrings für einfache Methoden, kurze Inline-Kommentare nur wenn nötig

### Pre-commit / Versions-Pinning (wichtig!)
CI (`.github/workflows/ci.yml`) prüft `black --check .` + `ruff check .`. **Black/Ruff
sind in `requirements-dev.txt` gepinnt** (aktuell `black==24.4.2`, `ruff==0.4.10`) —
exakt dieselben Versionen in `.pre-commit-config.yaml`. Eine **abweichende lokale
Black-Version formatiert anders und lässt die CI fehlschlagen.** Daher:

```bash
pip install -r requirements-dev.txt   # gepinnte Tool-Versionen ins venv
pre-commit install                    # Hook aktivieren (einmalig pro Clone)
```

Danach formatiert jeder Commit automatisch mit der CI-Version (Hook läuft isoliert,
unabhängig von sonstigen venv-Versionen). Tool-Versionen nur bewusst und **synchron**
in `requirements-dev.txt` **und** `.pre-commit-config.yaml` ändern.

#### ⚠️ Bekannte Falle: PATH-Shadowing (ist schon mehrfach passiert!)
Black/Ruff **immer als Modul aufrufen**, nie als nacktes Binary:

```bash
python -m black .        # statt: black .
python -m ruff check .   # statt: ruff check .
```

Grund: In Sandboxes/CI-Runnern/Systemen liegt oft ein **anderes, neueres Black
im PATH** (z. B. `/root/.local/bin/black`), das das pip-installierte, gepinnte
24.4.2 verdeckt. Neuere Black-Versionen formatieren Multiline-Strings anders
("hugging" von `gr.HTML("""…""")`) → lokal sieht alles sauber aus, aber
`black --check .` in der CI schlägt fehl. Vor dem Formatieren im Zweifel
`python -m black --version` gegen den Pin in `requirements-dev.txt` prüfen
(`black --version` zeigt ggf. das falsche PATH-Binary!). Das Makefile ruft
bewusst `python -m black`/`python -m ruff` auf.

## Feature-Modi

| Modus | Beschreibung |
|---|---|
| **Chat** | Einzelne Persona, Streaming |
| **AI-Dialog** | Zwei Personas konversieren automatisch (Stop: Antwort enthält `endegelaende` oder endet auf `_ende_`) |
| **Broadcast/Ask-All** | Eine Frage an alle Personas; Antworten live tokenweise gestreamt als Markdown-Sektion pro Persona. WebUI streamt **parallel** (`iter_broadcast_events_parallel`: Worker-Thread + Queue pro Persona; Fallback `ui.experimental.broadcast_parallel: false`), Terminal sequenziell (`iter_broadcast_events`). Echter Speedup braucht `OLLAMA_NUM_PARALLEL` ≥ Persona-Zahl, sonst serialisiert Ollama |

### ⚠️ Stolperfalle: gr.Dataframe kann kein Streaming (Gradio 4.44)
Die Dataframe-Komponente **verliert Updates aus Generator-Handlern** — das Frontend
friert nach den ersten Yields ein (gilt für `gr.update` wie Rohwerte, `str` wie
`markdown`-datatype; per Minimal-Repro bestätigt). Zusätzlich: fester 500px-Scroll-
Viewport und eine virtualisierte Tabelle, deren Mess-Klon-Zeilen DOM-Selektoren in
Browser-Tests verfälschen. **Für live wachsende Ausgaben `gr.Markdown` (Voll-Ersatz
pro Yield) oder `gr.Chatbot` verwenden** — so macht es die Ask-All-Ansicht.
Verwandt: `pydantic` ist auf `2.9.2` gepinnt (>2.10 erzeugt bool-Schemas, die
Gradio 4.44 crashen).

### ⚠️ Stolperfalle: Gradio `cancels` schließt Generatoren nicht (Gradio 4.44)
`cancels=[...]` bricht nur den **asyncio-Task** ab (`task.cancel()` in
`gradio/utils.py`); `reset_iterators` löscht bloß die Referenz — das `finally`
eines laufenden Generator-Handlers wird **nicht zuverlässig ausgeführt**, im
Backend gestartete Arbeit (LLM-Streams, Threads) läuft weiter (live gemessen:
Streams liefen nach Cancel komplett durch). **Lösung im Projekt:** expliziter
Kill-Switch — `WebUI._ask_all_stop` (`threading.Event`) wird vom Reset-Handler
(eigenes, zuverlässig laufendes Gradio-Event) gesetzt und stoppt die
Broadcast-Worker direkt (`stop_event`-Parameter von `iter_broadcast_events_parallel`).
Für neue streamende Handler dasselbe Muster verwenden, nicht auf `cancels` bauen.

## Backlog (wichtigste offene Punkte)

Siehe [backlog.md](backlog.md) für vollständige Liste mit Effort/Benefit-Matrix. Highlights (Stand 2026-07-07):

- **#13** STT MVP: Spracheingabe
- **#7** LoRA-Finetuning: In Arbeit (LeoLM13B)
- **#14** E-Mail-Adapter: Rest-Punkte (processed_mailbox scharf testen, Dauerbetrieb, PW rotieren)

Bereits erledigt (Details im Backlog): #18 Wrongdoing-Guardrail, #19 Drei-Zeitstempel,
#5 `/healthz`, #21 `--doctor`, #14 E-Mail-Adapter (MVP), #12 Karl (opt-in), #20 Ask-All-Ansicht,
#2 Stream-Abbruch, #9 Wiki im Broadcast, #22 Kiwix/ZIM-Update (`docs/{de,en}/Kiwix_Setup.md`),
#23 Paralleler Broadcast, #17 Faster first token (Startup-Warm-up, `core.keep_alive`,
WebUI-Stream-Drossel; bewusst ohne Prompt-Diät).

## Sprachstrategie

- Projekt-Sprache in `config.yaml`: `language: "de"` (Standard)
- Locale-Dateien: `locales/de.yaml`, `locales/en.yaml`
- Persona-Prompts lokalisiert in `ensembles/classic/locales/{de,en}/personas.yaml`
- UI-Texte via `Config.t()` formatiert

## Wichtige API-Endpunkte

```
POST http://127.0.0.1:8013/ask
  Body: { "question": "Hallo", "persona": "LEAH" }
  → { "answer": "..." }

GET  http://127.0.0.1:8013/health    # Liveness (Prozess antwortet)
GET  http://127.0.0.1:8013/healthz   # Readiness (Ollama/Modell/spaCy/Kiwix/VRAM, 503 bei kritischem Fehler)
```

Dieselben Deep-Checks gibt es auch ohne laufenden Server: `python src/launch.py --doctor`.

## Logging

Alle Logs in `logs/`:
- `yulyen_ai_YYYY-MM-DD_HH-MM.log` — Systemlog
- `conversation_[PERSONA]_[TIMESTAMP].json` — Gesprächslog (JSON)
- `wiki_proxy_[TIMESTAMP].log` — Wiki-Proxy-Log
