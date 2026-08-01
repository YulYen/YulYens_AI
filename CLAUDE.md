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
| TTS | Piper (ONNX; Terminal: Autoplay über winsound/CLI-Player, WebUI: Browser-Playback) |
| STT | faster-whisper (optional, WebUI-Mikro) |
| Security | BasicGuard (tinyguard.py) |
| Tests | pytest |
| Formatting | Black (88), Ruff |
| Typen | mypy (`src/core`, `src/storage`, `src/auth`) |

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
│   │   ├── schema.py            # pydantic-Prüfung für config.yaml + Ensembles
│   │   ├── texts.py             # i18n (MutableMapping)
│   │   └── logging_setup.py
│   ├── ui/
│   │   ├── web_ui.py            # Gradio-UI
│   │   ├── terminal_ui.py       # Terminal-UI (farbig)
│   │   ├── webui_layout.py      # Gradio-Layout-Builder + Ausgabe-Key-Listen
│   │   ├── webui_format.py      # Reine Formatierer (Statuszeile, Quellen, Markdown)
│   │   ├── session.py           # SessionContext: Zustand *einer* Browser-Sitzung
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
│   └── test_*.py                # 41 Testmodule (inkl. test_web_ui_wiring.py,
│                                #   test_continuation.py, test_imports.py)
├── locales/
│   ├── de.yaml                  # 150 UI-Texte Deutsch (Parität mit en.yaml)
│   └── en.yaml                  # UI-Texte Englisch
├── config.yaml                  # Hauptkonfiguration
├── pyproject.toml               # Black/Ruff + pytest-Konfiguration
├── Makefile                     # make setup / format / lint / types / test / test-ci / evals / clean / run
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
User-Input ──→ SecurityGuard (Eingang) ──┐
spaCy → Wiki-Proxy (8042) ──→ Guard (Kontext) ──┤
briefing/feeds.py (RSS) ───→ Guard (Kontext) ──┘
                                          → Ollama
           → Token-Stream → SecurityGuard (Ausgang) → UI + TTS + JSON-Log
```

**Der Guard hat zwei Eingänge, nicht einen.** Die frühere Darstellung
(`User-Input → Guard → spaCy → Wiki-Proxy → Ollama`) las sich, als läge der
Guard vor allem, was ins Modell geht — er sah aber ausschließlich die letzte
`user`-Nachricht. Abgerufener Fremdtext (Wiki-Snippet, RSS-Meldung) ging an ihm
vorbei und landete als **`system`**-Nachricht im Prompt, also mit *mehr* Gewicht
als die Frage des Nutzers. Derselbe Satz, den der Guard beim Tippen blockt, kam
über eine heruntergeladene ZIM-Datei ungeprüft durch.

Seit dem Fix prüft `security.tinyguard.accepted_context` den Inhalt (nur
`prompt_injection` und `wrongdoing` verwerfen — ein Artikel darf E-Mail-Adressen
enthalten). Wer einen **dritten** Kontext-Kanal baut, muss ihn dort mit
anschließen; ein Kanal ohne diese Prüfung ist eine Injection-Lücke mit
System-Autorität.

**Gefiltert wird in `WikiLookup.snippets()`, nicht erst beim Injizieren.** Der
erste Anlauf hängte die Prüfung nur an `inject_wiki_context` — dann bekam die
Quellen-Karte (#32) weiterhin die *ungefilterte* Liste und behauptete Quellen,
die das Modell nie gesehen hat. Das ist exakt der Defekt, gegen den #32 gebaut
wurde. Ausgelöst wird er von der bekannt schlechten False-Positive-Rate des
Guards (#62): ein Artikel über `localhost` trifft die Injection-Regel. Alle
Verbraucher — Anzeige, Injektion, `/quellen` im Terminal — gehen deshalb durch
diese eine Methode. `inject_wiki_context`/`inject_briefing_context` behalten
ihren `guard`-Parameter als letzte Schranke vor dem Prompt.

Die Rolle ist weiterhin `system` — sie nach `user` zu verschieben ändert das
Antwortverhalten aller Personas und braucht einen Lauf am echten Modell (#60).

### AppFactory
- Baut und cached alle Komponenten (Streamer, UI, API-Provider, Store, `WikiLookup`)
- Zustand in Tests via `set_provider(None)` + `Config.reset_instance()` zurücksetzen

### WikiLookup: ein Objekt statt fünf Attributen
`wiki/lookup.py` bündelt Modus, Port, Limit, Snippet-Zahl, Timeout und den
Keyword-Finder. `AppFactory.get_wiki_lookup()` baut es einmal; WebUI, TerminalUI,
API-Provider und `respond_one_shot` bekommen es als **ein** Argument. Vorher stand
derselbe Achter-Aufruf an sechs Stellen und dieselben fünf `wiki_*`-Attribute in
drei Klassen — eine neue Wiki-Option hätte man überall nachziehen müssen. Neue
Optionen also **in `WikiLookup`**, nicht als weiteres Argument.

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

storage:
  enabled: true              # Gesprächs-Ablage (SQLite)
  file_exchange: true        # JSON-Down-/Upload im WebUI, /save im Terminal
  history_limit: 50          # wie viele Gespräche der Verlauf zeigt

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

### Ablage der Gespräche (#54): Store ≠ Logfile
`src/storage/store.py` hält die Gespräche in einer SQLite-Datei
(`storage.path`, gitignored). **Das Gesprächs-Logfile war vorher die Persistenz**
— mit zwei unvereinbaren Formaten und ohne Gesprächsbegriff. Jetzt gilt:

| Artefakt | Rolle |
|---|---|
| `data/conversations.sqlite3` | **die Aufzeichnung** — Verlauf (#25), später Suche (#49) und Fakten (#24) |
| `logs/conversation_*.json` | roher Mitschnitt zum Debuggen, **opt-in** über `logging.conversation_jsonl` |

**Der Datei-Im-/Export bleibt, ist aber abschaltbar** (`storage.file_exchange`, Default an) — er ist etwas anderes als die Ablage. `conversation_io_terminal.py`
(JSON hoch-/runterladen im WebUI, `/save` und Laden im Terminal) ist der
*Austausch mit der Außenwelt*: sichern, auf einen anderen Rechner mitnehmen,
weitergeben. Die Ablage ist das *eigene Gedächtnis der App*. Drei Wege, drei
Zwecke:

| Weg | Format | wofür |
|---|---|---|
| Verlauf → Öffnen | — | eigenes Gespräch fortsetzen |
| Verlauf → Als Markdown | Markdown | lesbar weitergeben (Einbahnstraße) |
| „Konversation herunterladen" / Upload | JSON | Austausch, verlustfrei zurückladbar — abschaltbar über `storage.file_exchange`. Ein hochgeladenes Gespräch läuft als **eigener** Eintrag in der Ablage weiter (`app: web-import`); ohne das schriebe jeder Turn nach dem Laden ins Leere |

**Migrationen** über `PRAGMA user_version` plus die Liste `_MIGRATIONS`: neue
Schritte nur **anhängen**, nie einen ausgelieferten Schritt ändern. Die
FTS5-Tabelle für #49 wird Schritt 2 — SQLite bringt FTS5 mit, ein eigener Index
ist unnötig.

**Jeder Schritt läuft ganz oder gar nicht.** Vorher lief er über
`executescript`, das die pendente Transaktion vorher committet und das Skript
selbst nicht klammert: scheiterte Anweisung 2 von 3, blieb Anweisung 1 stehen,
`user_version` blieb zurück — und damit war der Schritt **nie wieder** anwendbar
(„table … already exists"). Der Store degradierte bei jedem weiteren Start zum
`NullStore`, und die App lief weiter, ohne noch etwas aufzuzeichnen. Jetzt steht
`BEGIN`/`COMMIT` im Skript, `user_version` wird darin gesetzt (in SQLite
transaktional), ein Fehlschlag rollt zurück und nennt die Schrittnummer.
Bewusst weiter `executescript` statt einer Zerlegung an `;`: ein FTS5-Trigger
bringt eigene Semikolons im `BEGIN…END`-Rumpf mit.

**Nutzergebundenes Lesen und Löschen:** `load()` und `delete()` nehmen ein
optionales, keyword-only `user`. Mit gesetztem Wert verhält sich ein fremdes
Gespräch wie ein nicht existierendes — die Antwort soll nicht verraten, dass es
die ID gibt. Terminal und API rufen weiter ohne `user`. **Die WebUI muss ihn
immer setzen:** die Gesprächs-ID kommt aus einem `gr.Dropdown`, und dessen
`preprocess` reicht in Gradio 4.44 den Wert des Clients ungeprüft durch — die
Auswahl im Browser ist keine Schranke.

**Die Gesprächs-ID gehört der Oberfläche, nicht dem Streamer:** sie liegt im
`gr.State` `conversation_state` und wird nach einem Streamer-Neubau erneut
gesetzt (`set_conversation`). Sonst begänne jede Fortsetzung ein neues Gespräch.

Aufzeichnen darf **nie** den Stream abbrechen (wie beim Logfile davor), und eine
unbrauchbare Datei degradiert zum `NullStore`, statt den Start zu verhindern.
Tests laufen per autouse-Fixture gegen `storage.enabled: false` — sonst schriebe
jede Test-Session in die echte Datenbank.

### Anmeldung (#53): eine Naht, kein Sicherheitsprodukt
`src/auth/provider.py` beantwortet „wer bedient die UI". Drei Provider über
`ui.web.auth.provider`:

| Provider | Verhalten |
|---|---|
| `disabled` (**Default**) | kein Login, alle sind `local` — Verhalten wie vor #53 |
| `local` | Nutzer aus `ui.web.auth.users`, Passwörter über die `env:`-Konvention |
| `header` | Identität aus dem Header eines vorgeschalteten Proxys |

**Der Wert liegt in der Naht:** `user` hängt an jedem Gespräch in der Ablage
(#54) und steht in jeder Feedback-Vote. Genau das
brauchen #25 (Verlauf), #49 (Suche), #40b und #24 (Fakten über den Nutzer).
Die Identität wird **einmal pro Browser-Sitzung** über `demo.load` + `gr.Request`
in ein `gr.State` geholt — nicht `gr.Request` an jeden Handler hängen, die
Persona-Buttons laufen über `functools.partial`.

**Ehrlich einordnen:** Gradios Basic-Auth geht über HTTP im Klartext. Ohne TLS
ist das eine *Trennung* von Nutzern, kein Schutz gegen Mitlesen. `header`
vertraut dem Header bedingungslos und darf nur hinter einem Proxy laufen, der
ihn von außen entfernt.

**Kein OIDC direkt:** Gradios `auth=`-Callable bekommt nur Name und Passwort —
kein Redirect-Flow, keine Token-Validierung. Keycloak & Co. laufen über
oauth2-proxy/Authelia davor, die die Identität als Header durchreichen; genau
dafür gibt es `HeaderAuth`.

Die Anmeldung gilt **unabhängig von `share`**. Das alte `ui.web.share_auth`
greift nur noch als Fallback (mit Deprecation-Warnung) — es wirkte früher
ausschließlich beim Share-Link, obwohl der Server per Default auf `0.0.0.0`
horcht.

### Schema-Prüfung (#43): zwei Härtegrade
`src/config/schema.py` prüft `config.yaml` und die Ensemble-Dateien mit pydantic.
**Beim Start wird nur gewarnt** (`logging.warning("[CONFIG] …")`) — ein laufendes
Setup darf nicht an einem Schema scheitern, das die persönliche
`config.local.yaml` nie gesehen hat. **`--doctor` und `/healthz` melden denselben
Befund hart** (`CheckResult("config")`), dort will man Strenge. Unbekannte Keys
sind nie ein Fehler, sondern ein Tippfehler-Hinweis: `extra="allow"` plus eigener
Abgleich gegen `KNOWN_TOP_LEVEL_KEYS`, nicht `extra="forbid"` — sonst blockiert
jede neue Sektion sofort alles. Neue Config-Optionen also **immer** dort
nachtragen, sonst warnt der Start grundlos.

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

### CI-Jobs (`.github/workflows/ci.yml`)
| Job | Was er prüft |
|---|---|
| **Format & lint** | `black --check` + `ruff check`, beide als Modul (PATH-Falle unten) |
| **Tests (ubuntu-latest / windows-latest)** | Volle Suite ohne `ollama`-Marker, mit `--cov`. Die Windows-Matrix ist der Punkt: das Projekt läuft Windows-primär, Pfad-/`winsound`-Probleme fielen auf reinem Linux nie auf (#45) |
| **Typen (mypy)** | `python -m mypy` — blockierend über `src/core`, `src/storage` und `src/auth` (Konfiguration in `pyproject.toml`). `follow_imports = silent` liest den Rest fürs Signatur-Wissen mit, meldet dort aber nichts; Erweiterung Modul für Modul |
| **Tests mit spaCy-Modell** | `de_core_news_lg` per `actions/cache` (versionierter Key), dann gezielt `test_spacy_keywords.py` + `test_wiki.py` — die liefen sonst nur als Skips |

Coverage steht als Zahl in der Job-Summary (kein externer Badge-Dienst, der
Account + Token bräuchte). mypy läuft seit #52 blockierend, inzwischen über `src/core`, `src/storage` und
`src/auth`; `make types` ist die lokale Kurzform.

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
| **Quellen (#32)** | Zugeklapptes Accordion „Quellen 📚" unter dem Chat. Zeigt pro injiziertem Wikipedia-Snippet den Titel als Link auf kiwix-serve, die Herkunft und **den Snippet-Text selbst** samt Zeichenzahl (`1200 von 9800 Zeichen injiziert (gekürzt)` bzw. `51 Zeichen (vollständig)`). `wiki.snippet_limit` kürzt — erst die Anzeige macht sichtbar, was das Modell nie gesehen hat. Datenquelle ist `WikiSnippet` aus `wiki/lookup.py`; die Originallänge liefert der Proxy als `full_length` mit. Ask-All hat ein eigenes Accordion innerhalb seiner Gruppe (#32a), im Terminal zeigt `/quellen` denselben Inhalt ungekürzt. Meta-Zeile geteilt über `format_snippet_meta` |
| **Statuszeile (#36)** | Unter dem Chat: `Kontext █░░░ 424 / 8.192 Token (5 %) · 24,0 Tok/s · erster Token nach 1,9 s`. Füllstand aus `approx_token_count` + `num_ctx`, Tempo aus `StreamStats` (der Provider legt sie nach jedem Stream auf sich selbst ab). Ab `context_utils.threshold` (75 %) fett — ab da greift die Kompression. Wert nur im Schluss-Yield, sonst `gr.update()` |
| **Verlauf (#25)** | Karte „Verlauf öffnen 🗂" listet die Gespräche des angemeldeten Nutzers aus dem Store (#54). Auswahl per `gr.Dropdown` (kein `gr.Dataframe`, siehe Stolperfalle unten), Vorschau als Markdown, dazu Öffnen (fortsetzbar — dieselbe Gesprächs-ID), Markdown-Export und Löschen. Länge über `storage.history_limit` (Default 50, neueste zuerst). Gespräche von Gast-Personas bleiben lesbar, aber nicht fortsetzbar — erkannt an ihrem eigenen `app` (`web-guest`) **und** am exakten Personennamen, sonst öffnete ein Gast namens „Leah" das Gespräch still als die echte LEAH. Die Regel steht in `ui/continuation.py` und gilt für **alle drei** Wege in ein gespeichertes Gespräch: Verlauf, JSON-Upload und der Ladepfad im Terminal. Jeder Handler prüft zusätzlich den Eigentümer (`user_state`) |
| **Gast-Persona (#28)** | Karte „Gast anlegen 🎭" → Formular (Name, System-Prompt, Temperatur). Lebt **nur in der Sitzung**: kein YAML, kein Reload. Läuft über `AppFactory.get_streamer_for_guest`, das sich mit dem Persona-Pfad einen `_build_streamer` teilt — Guard, Wiki, Statuszeile, Quellen und Gesprächs-Ablage kommen dadurch gratis mit. Persistenz nach `ensembles/custom/` wäre V2 |
| **Stop / Nochmal (#35)** | Während eines Streams ersetzt „Stop ⏹" den Senden-Button; der Kill-Switch `SessionContext.stream_stop` beendet den Generator geordnet und **behält die Teilantwort** (Suffix `web_stream_stopped_suffix`). Gilt für Einzelchat, Briefing und Self-Talk — dort erst zwischen den Turns, weil `run_turn()` die Antwort in einem Zug holt. „Nochmal 🔄" verwirft die letzte Antwort in Anzeige und LLM-Verlauf und streamt denselben Kontext erneut (Varianz allein aus der Persona-Temperatur); Wiki-/Briefing-Hints bleiben stehen |

### Sitzungszustand gehört in den `gr.State`, nicht ans WebUI-Objekt
Die `WebUI` ist ein **Singleton der AppFactory** und bedient alle Browser
gleichzeitig. Persona, Streamer, die beiden Kill-Switches und der
Self-Talk-Runner hingen anfangs am Objekt — zwei parallele Sitzungen teilten sie
sich also. Belegt im Browser: A wählt LEAH, B danach DORIS, A fragt → die
Nachricht landet in **DORIS'** Gespräch, LEAHs bleibt leer.

Sie liegen deshalb in `SessionContext` (`ui/session.py`) und reisen als
`gr.State` durch die Handler — als **erster** Parameter, passend zur
`inputs=`-Reihenfolge. Gradio legt pro Browser-Sitzung eine eigene Kopie des
Default-Werts an (`SessionState.__getitem__` in `gradio/state_holder.py` macht
einmalig ein `deepcopy` und merkt sie sich), deshalb genügt es, das Objekt
durchzureichen und **in-place** zu ändern; als Output zurück muss es nicht.
Konsequenzen fürs Weiterbauen:

- **Neuer sitzungsabhängiger Zustand gehört in `SessionContext`**, nie an `self`.
  Am WebUI-Objekt bleibt nur, was für alle gleich ist (Config-Flags, Auth, Texte).
- Der Default-Wert muss `deepcopy`-fähig sein — ein Streamer im Default würde die
  Trennung still wieder aufheben.
- Auslieferungsdateien (WAV, JSON, Markdown) hängen aus demselben Grund an der
  Sitzung (`SessionContext.tmp_files`): sonst räumt ein Download im einen Browser
  die Datei eines anderen weg. Beim nächsten Mal wird die vorherige Datei
  derselben Art gelöscht, das Verzeichnis räumt ein `atexit`-Handler ab.
  **Nur die Originale:** Gradio kopiert Ausgabedateien in seinen eigenen Cache
  (`blocks.py` → `processing_utils.move_files_to_cache`) und liefert von dort
  aus. Gut, denn das Löschen kann keinen laufenden Abruf zerreißen — aber die
  zweite Kopie verwaltet Gradio, nicht wir.

### ⚠️ Die Konsolenwarnung „Too many arguments provided for the endpoint" ist normal
Sie kommt aus Gradios **Frontend**
(`_frontend_code/client/src/helpers/api_info.ts`) und vergleicht die Zahl der
gesendeten Werte mit `api_info.parameters`. `gr.State` hat `skip_api = True` und
steht dort nicht drin — **jedes Event mit einem State als Input warnt**, ohne
dass etwas kaputt wäre. Nicht suchen, nicht "reparieren".

### ⚠️ Stolperfalle: gr.Dataframe kann kein Streaming (Gradio 4.44)
Die Dataframe-Komponente **verliert Updates aus Generator-Handlern** — das Frontend
friert nach den ersten Yields ein (gilt für `gr.update` wie Rohwerte, `str` wie
`markdown`-datatype; per Minimal-Repro bestätigt). Zusätzlich: fester 500px-Scroll-
Viewport und eine virtualisierte Tabelle, deren Mess-Klon-Zeilen DOM-Selektoren in
Browser-Tests verfälschen. **Für live wachsende Ausgaben `gr.Markdown` (Voll-Ersatz
pro Yield) oder `gr.Chatbot` verwenden** — so macht es die Ask-All-Ansicht.
Verwandt: `pydantic` ist auf `2.9.2` gepinnt (>2.10 erzeugt bool-Schemas, die
Gradio 4.44 crashen).

### ⚠️ Der Guard-Holdback bestimmt die wahrgenommene Antwortzeit (#51)
`_StreamModerator` (`core/streaming_provider.py`) hält die letzten
`_STREAM_HOLDBACK_CHARS` Zeichen zurück, damit ein PII-/Secret-Muster nicht über
eine Token-Grenze hinweg durchrutscht. Konsequenz: **vor `holdback` Zeichen geht
überhaupt nichts an die Anzeige.** Im Browser gemessen, 24 Zeichen/s:

| Variante | erster Token sichtbar |
|---|---|
| nackte Gradio-App (kein Guard) | 0,95 s |
| Projekt, `holdback: 96` | 4,13 s |
| Projekt, `holdback: 32` (Default) | **1,91 s** |
| Projekt, `holdback: 0` | 0,39 s |

Der Default 32 ist kein runder Wert: das längste Blocklist-Muster (AWS-Secret)
schlägt erst nach Label + 30 Zeichen an, deshalb bleibt Schlüsselmaterial erst
ab einem Holdback von 30 vollständig verdeckt. Darunter rutscht es mit durch —
festgenagelt in `test_default_holdback_keeps_key_material_hidden`.

Der Verzug entsteht **serverseitig** — der SSE-Frame auf `/queue/data` geht erst
bei +4,09 s raus, gerendert wird danach in 40 ms. Beim Suchen also nicht im
Frontend anfangen. Einstellbar über `security.stream_holdback_chars`; bei
abgeschalteten Ausgangs-Checks (`pii_protection` **und** `output_blocklist` aus)
entfällt der Holdback automatisch, weil es dann nichts zu prüfen gibt.

Wichtig für #17/#42: eine backendseitige Messung von „Zeit bis zum ersten Token"
sieht diesen Anteil **nicht** — das Modell liefert längst, die Anzeige wartet.

**Der Holdback ist nur die eine Hälfte.** #51 hat die Zeit bis zum *ersten*
Token gemessen und daraus den Default abgeleitet — korrekt, aber unvollständig.
`_StreamModerator.feed()` ruft `process_output` **pro Token über den gesamten
bisherigen Text** auf, ist also quadratisch im Antwortumfang. Mit der
ausgelieferten Config gemessen (nur `output_blocklist` aktiv):

| Antwort | reine Guard-CPU |
|---|---|
| 200 Tokens (800 Zeichen) | 4 ms |
| 1000 Tokens (4.000 Zeichen) | 102 ms |
| 2000 Tokens (8.000 Zeichen) | 409 ms |
| 4000 Tokens (16.000 Zeichen) | **1.605 ms** |

Zum Vergleich: mit `security.enabled: false` sind es bei 4000 Tokens 3,8 ms.
Der Holdback kostet einmalig, dieser Anteil wächst mit jeder Antwort und läuft
auf dem yieldenden Thread — im parallelen Broadcast viermal gleichzeitig gegen
dieselbe GIL. Behoben wird das zusammen mit zwei weiteren Defekten desselben
Codes in **#58**.

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
Kill-Switch — `SessionContext.ask_all_stop` (`threading.Event`) wird vom Reset-Handler
(eigenes, zuverlässig laufendes Gradio-Event) gesetzt und stoppt die
Broadcast-Worker direkt (`stop_event`-Parameter von `iter_broadcast_events_parallel`).
Für neue streamende Handler dasselbe Muster verwenden, nicht auf `cancels` bauen.

## Backlog (wichtigste offene Punkte)

Siehe [backlog.md](backlog.md) für vollständige Liste mit Effort/Benefit-Matrix
(Generalüberholung 2026-07-30: neue Tickets #24–#48, Erledigtes in Archiv-Sektion).
Highlights:

- **Tier A (LoRA-Strecke):** #40 Feedback-Daumen ✅ → #41 Eval-Suite ✅ → #7 LoRA-Finetuning
  (in Arbeit, LeoLM13B; nicht mehr blockiert). Offen: #41a Baseline-Lauf, #40b Blind-Ranking
- **Quick Wins:** #53a Identität für API/Mail, #27 Ask-All-Moderator, #42 Perf-Benchmark
  (mypy läuft seit #52 über `src/core`; nächste Module bewusst einzeln)
- **Aus Review-Runde 2 (#57):** #58 `_StreamModerator` (verschluckter Text, roher Text im
  Store, quadratische Laufzeit), #59 Ablage = Gespräch statt LLM-Aufruf, #62 Guard-Regelwerk,
  #14 E-Mail-Adapter härten (Reply-To-Reflexion, endlose Dubletten), #61 Gradio 5.x
- **Strategisch:** #24 Langzeit-Gedächtnis (größter UX-Hebel, Store aus #54 als Basis), #49 Volltextsuche (FTS5 als Migrationsschritt), #30 Tool-Use (Türöffner)

Bereits erledigt (Details im Backlog-Archiv): #18 Wrongdoing-Guardrail, #19 Drei-Zeitstempel,
#5 `/healthz`, #21 `--doctor`, #14 E-Mail-Adapter (MVP), #12 Karl (opt-in), #20 Ask-All-Ansicht,
#2 Stream-Abbruch, #9 Wiki im Broadcast, #22 Kiwix/ZIM-Update, #23 Paralleler Broadcast,
#17 Faster first token, #6 Modell-Auswahl (WebUI, session-only), #13 STT MVP (WebUI-Mikro
via faster-whisper, `src/stt/ReadMe.md`), #15 Briefing (RSS-MVP, IoT-Teil offen),
#25 TTS im WebUI (Vorlesen-Button, Browser-Playback), #35 Stop/Regenerate,
#37 OpenAI-kompatible API, #41 Eval-Suite, #50 Guard-Braces-Lücke, #51 Holdback-Latenz,
#32/#32a Wiki-Quellen-Transparenz, #52 mypy für `src/core`, #36 WebUI-Politur,
#43 Config-/Ensemble-Validierung, #53 Identitäts-Naht, #28 Gast-Persona,
#54 Gesprächs-Ablage (SQLite), #25 Verlauf, #55 Review-Befunde, #57 Review-Befunde Runde 2.

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

GET  http://127.0.0.1:8013/health    # Liveness (Prozess antwortet) — ohne Schlüssel
GET  http://127.0.0.1:8013/healthz   # Readiness (Ollama/Modell/spaCy/Kiwix/VRAM, 503 bei kritischem Fehler)

# OpenAI-kompatibel (#37) — "model" ist der Persona-Name
GET  http://127.0.0.1:8013/v1/models
POST http://127.0.0.1:8013/v1/chat/completions
  Body: { "model": "DORIS", "messages": [...], "stream": true|false }
```

### OpenAI-Kompatibilität: worauf zu achten ist
- **`model` = Persona**, nicht LLM. `/v1/models` listet Personas; das echte Modell
  bleibt Serversache (`core.model_name`).
- **`api.openai_compatible.api_key` gilt für *alle* Endpunkte, auch für `/ask`** —
  der Name sagt nur, wo die Option steht. Vorher hing `require_access` allein am
  `/v1`-Router, während `/ask` auf demselben Port dieselbe Fähigkeit ohne
  Schlüssel und ohne Rate-Limit anbot. Die Regel liegt in `check_api_access`,
  die Fehler*form* bleibt pro Router verschieden (`/v1`: OpenAI, `/ask`:
  FastAPI). Ein neuer Endpunkt, der ein LLM anspricht, gehört dort mit dran.
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

**Gespräche liegen nicht hier**, sondern seit #54 in `data/conversations.sqlite3`
(siehe „Ablage der Gespräche"). In `logs/` steht nur noch Betriebs-Diagnostik
(Eval-Reports in `logs/evals/`):
- `yulyen_ai_YYYY-MM-DD_HH-MM.log` — Systemlog
- `conversation_[TIMESTAMP].json` — roher Turn-Mitschnitt als JSONL, **opt-in**
  über `logging.conversation_jsonl` (Default aus). Debug-Artefakt, keine Ablage
- `wiki_proxy_[TIMESTAMP].log` — Wiki-Proxy-Log
- `feedback_votes.jsonl` — 👍/👎-Bewertungen (#40), append-only, eine Zeile pro Vote
