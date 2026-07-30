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
| TTS | Piper (ONNX; Terminal: Windows-Autoplay, WebUI: Browser-Playback) |
| STT | faster-whisper (optional, WebUI-Mikro) |
| Security | BasicGuard (tinyguard.py) |
| Tests | pytest |
| Formatting | Black (88), Ruff |

## Verzeichnisstruktur

```
<repo-root>/
├── src/
│   ├── launch.py              # Haupteinstiegspunkt (inkl. --doctor Systemcheck, --list-ensembles)
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
│   │   ├── app.py               # FastAPI: /ask, /health, /healthz + /v1-Router
│   │   ├── openai_compat.py     # OpenAI-kompatible Endpunkte (#37)
│   │   └── provider.py          # One-Shot + stream_messages (Client-History)
│   ├── email_adapter/
│   │   └── service.py           # opt-in IMAP/SMTP-Bridge (Personas per Mail)
│   ├── wiki/
│   │   ├── wikipedia_proxy.py   # HTTP-Proxy (Port 8042)
│   │   ├── spacy_keyword_finder.py  # NLP-Schlüsselwortextraktion
│   │   └── kiwix_autostart.py
│   ├── security/
│   │   └── tinyguard.py         # BasicGuard (Prompt-Injection, PII, Blocklist)
│   ├── tts/
│   │   ├── piper_tts.py         # TTS-Wrapper
│   │   └── audio_player.py      # winsound (Windows-only, plattform-sicher)
│   ├── stt/
│   │   └── whisper_stt.py       # Spracheingabe via faster-whisper (optional, lazy)
│   ├── briefing/
│   │   └── feeds.py             # RSS/Atom-Briefing (spiegelt wiki/lookup.py)
│   └── evals/                   # Eval-Suite (#41): Korpus-Loader, Judge, Runner, Report
├── evals/                       # Eval-Korpora als YAML (siehe evals/ReadMe.md)
│   ├── personas/*.yaml          # Goldene Fragen pro Persona
│   ├── behaviour/*.yaml         # Verhaltensbeweise (drei Zeitstempel)
│   ├── karl_summary.yaml        # Qualität der Karl-Zusammenfassungen
│   └── guard_redteam.yaml       # Angriff → erwartetes Guard-Verhalten
├── scripts/
│   └── run_evals.py             # Einstieg der Eval-Suite
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
- Test-Fixture `ollama_config`: Config gegen echtes Ollama, für `@pytest.mark.ollama`-Tests
  ohne HTTP-Client (z. B. Eval-Suite)
- Marker `@pytest.mark.ollama`: wird geskippt wenn Ollama nicht erreichbar
- spaCy-Modelle (`python -m spacy download de_core_news_lg`) schalten die
  Keyword-/Wiki-Tests frei; ohne Modell werden sie sauber geskippt

## Eval-Suite (#41)

Messbare Antwort auf „ist das Modell besser geworden?" — das Vergleichsartefakt
für #7 (LoRA). Details in [evals/ReadMe.md](evals/ReadMe.md).

```bash
python scripts/run_evals.py -e classic               # voll (braucht Ollama)
python scripts/run_evals.py -e classic --guard-only  # Guard-Teil, braucht kein Modell
make evals                                           # Kurzform für --guard-only
```

- Korpora als YAML in `evals/`, Code in `src/evals/` — neue Fälle per YAML, nicht per Testcode
- `checks` = deterministisch (Regex/Länge, Platzhalter `{today_de}` & Co.),
  `expect_traits` = LLM-as-judge 1–5 (4+ besteht, 3 nicht)
- **Judge-Bias:** per Default bewertet das Modell sich selbst und ist nachsichtig.
  Nur der Vergleich zweier Läufe mit gleichem Judge ist aussagekräftig (`report.csv`)
- Der Guard-Red-Team-Korpus läuft ohne Modell als parametrisierter Test in der CI mit
  (`tests/test_guard_redteam.py`) — Angriffsmuster gehören in `evals/guard_redteam.yaml`
- Korpus-Loader ist streng: unbekannte Keys, kaputte Regexe, doppelte IDs und
  erwartungslose Fälle fliegen beim Laden raus
- `known_gap: true` markiert eine dokumentierte Guard-Schwäche (gemeldet, kein
  Fehlschlag); ein Gegentest schlägt an, sobald die Lücke geschlossen ist

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
    web_read_aloud: true            # "Vorlesen"-Button im WebUI (braucht piper-tts)

stt:
  enabled: true              # WebUI-Mikro; braucht zusätzlich `pip install faster-whisper`
  model: "small"             # tiny | base | small | medium | large-v3
  language: "de"             # null = Auto-Erkennung

briefing:
  enabled: true              # WebUI-Button + /briefing (Terminal); Netz nur auf Klick
  feeds:                     # Liste von {name, url} (RSS 2.0 oder Atom)
    - name: "tagesschau"
      url: "https://www.tagesschau.de/index~rss2.xml"

api:
  enabled: true
  port: 8013
  openai_compatible:         # /v1/models + /v1/chat/completions (#37)
    enabled: true
    api_key: ""              # leer = offen; besser "env:YULYEN_API_KEY"
    rate_limit_per_minute: 60

security:
  enabled: true
  guard: BasicGuard

email_adapter:
  enabled: false             # opt-in IMAP/SMTP-Bridge (Personas per Mail)

context_management:
  strategy: "heuristic"      # "heuristic" (Default) | "karl" (LLM-Zusammenfassung)

evals:                       # nur von scripts/run_evals.py gelesen (#41)
  out_dir: "logs/evals"
  judge_model: "same_as_chat"  # eigenes Modell = weniger Judge-Bias
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
| **Briefing (RSS)** | Gewählte Persona fasst die Feeds aus `briefing.feeds` zusammen (WebUI-Button „Briefing 📰" bzw. `/briefing` im Terminal). Kontext-Injektion wie beim Wiki (`briefing/feeds.py`); nicht erreichbare Feeds werden mit Hint übersprungen |
| **Stop / Nochmal (#35)** | Während eines Streams ersetzt „Stop ⏹" den Senden-Button; der Kill-Switch `WebUI._stream_stop` beendet den Generator geordnet und **behält die Teilantwort** (Suffix `web_stream_stopped_suffix`). Gilt für Einzelchat, Briefing und Self-Talk — dort erst zwischen den Turns, weil `run_turn()` die Antwort in einem Zug holt. „Nochmal 🔄" verwirft die letzte Antwort in Anzeige und LLM-Verlauf und streamt denselben Kontext erneut (Varianz allein aus der Persona-Temperatur); Wiki-/Briefing-Hints bleiben stehen |

### ⚠️ Stolperfalle: gr.Dataframe kann kein Streaming (Gradio 4.44)
Die Dataframe-Komponente **verliert Updates aus Generator-Handlern** — das Frontend
friert nach den ersten Yields ein (gilt für `gr.update` wie Rohwerte, `str` wie
`markdown`-datatype; per Minimal-Repro bestätigt). Zusätzlich: fester 500px-Scroll-
Viewport und eine virtualisierte Tabelle, deren Mess-Klon-Zeilen DOM-Selektoren in
Browser-Tests verfälschen. **Für live wachsende Ausgaben `gr.Markdown` (Voll-Ersatz
pro Yield) oder `gr.Chatbot` verwenden** — so macht es die Ask-All-Ansicht.
Verwandt: `pydantic` ist auf `2.9.2` gepinnt (>2.10 erzeugt bool-Schemas, die
Gradio 4.44 crashen).

### ⚠️ Stolperfalle: Button-Updates nie als eigenes Event vor den Stream hängen
Der naheliegende Weg für „Senden ⇄ Stop tauschen" ist ein kleines Event vor dem
Stream-Handler (`btn.click(toggle).then(stream)`). **Kostet ~3,5 s bis zum ersten
Token** — das gequeuete `.then()` startet erst nach einem vollen Roundtrip des
ersten Events. Stattdessen die Button-Updates **in denselben Yields** des
Stream-Generators mitschicken (`WebUI._with_stream_controls`, #35): Stop erscheint
dann nach 0,16 s. Achtung beim Schluss-Yield: für `gr.State` müssen die echten
Werte erneut mitgeschickt werden, `gr.update()` würde den Update-Marker als
Zustand speichern.

Verwandt: **`cancels` kann nur gequeuete Events abbrechen.** Zeigt die Liste auf
ein `queue=False`-Event (z. B. das letzte Glied einer `.then()`-Kette), verweigert
Gradio den Start der App komplett mit „Queue needs to be enabled!".

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

Siehe [backlog.md](backlog.md) für vollständige Liste mit Effort/Benefit-Matrix
(Generalüberholung 2026-07-30: neue Tickets #24–#48, Erledigtes in Archiv-Sektion).
Highlights:

- **Tier A (LoRA-Strecke):** #40 Feedback-Daumen ✅ → #41 Eval-Suite ✅ → #7 LoRA-Finetuning
  (in Arbeit, LeoLM13B; nicht mehr blockiert). Offen: #41a Baseline-Lauf, #40b Blind-Ranking
- **Quick Wins:** #35 Stop/Regenerate, #32 Wiki-Quellen, #50 Guard-Braces-Lücke, #14 E-Mail-Restpunkte
- **Strategisch:** #24 Langzeit-Gedächtnis (größter UX-Hebel), #30 Tool-Use (Türöffner), #37 OpenAI-kompatible API

Bereits erledigt (Details im Backlog-Archiv): #18 Wrongdoing-Guardrail, #19 Drei-Zeitstempel,
#5 `/healthz`, #21 `--doctor`, #14 E-Mail-Adapter (MVP), #12 Karl (opt-in), #20 Ask-All-Ansicht,
#2 Stream-Abbruch, #9 Wiki im Broadcast, #22 Kiwix/ZIM-Update, #23 Paralleler Broadcast,
#17 Faster first token, #6 Modell-Auswahl (WebUI, session-only), #13 STT MVP (WebUI-Mikro
via faster-whisper, `src/stt/ReadMe.md`), #15 Briefing (RSS-MVP, IoT-Teil offen),
#25 TTS im WebUI (Vorlesen-Button, Browser-Playback).

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

# OpenAI-kompatibel (#37) — "model" ist der Persona-Name
GET  http://127.0.0.1:8013/v1/models
POST http://127.0.0.1:8013/v1/chat/completions
  Body: { "model": "DORIS", "messages": [...], "stream": true|false }
```

### OpenAI-Kompatibilität: worauf zu achten ist
- **`model` = Persona**, nicht LLM. `/v1/models` listet Personas; das echte Modell
  bleibt Serversache (`core.model_name`).
- **Fehler-Bodies müssen `{"error": {...}}` auf oberster Ebene haben.** FastAPIs
  `HTTPException(detail=…)` erzeugt `{"detail": {"error": …}}` — eine Ebene zu tief,
  das offizielle openai-SDK findet die Felder dann nicht. Deshalb eigene
  `OpenAIError` + Exception-Handler (`api/openai_compat.py`), und
  `RequestValidationError` wird unter `/v1` auf 400 + OpenAI-Form gemappt (`/ask`
  behält FastAPIs Standardform).
- **`temperature`/`top_p`/`max_tokens` werden angenommen und ignoriert** — Sampling
  gehört zur Persona, sonst kann jeder Aufrufer den Charakter plattmachen.
- **Client-History wird durchgereicht**, Karl/Heuristik greifen hier nicht
  (OpenAI-Semantik: der Client besitzt sein Kontextfenster).
- Verifikation gegen das echte SDK: `pip install openai`, dann `base_url` auf
  `http://127.0.0.1:8013/v1` zeigen. Bewusst **keine** Dependency im Projekt.

Dieselben Deep-Checks gibt es auch ohne laufenden Server: `python src/launch.py --doctor`.

## Logging

Alle Logs in `logs/` (Eval-Reports in `logs/evals/`):
- `yulyen_ai_YYYY-MM-DD_HH-MM.log` — Systemlog
- `conversation_[PERSONA]_[TIMESTAMP].json` — Gesprächslog (JSON)
- `wiki_proxy_[TIMESTAMP].log` — Wiki-Proxy-Log
- `feedback_votes.jsonl` — 👍/👎-Bewertungen (#40), append-only, eine Zeile pro Vote
