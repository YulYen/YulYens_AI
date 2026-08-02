# CLAUDE.md — Yul Yen's AI Orchestra

Dieses Dokument ist der Einstiegspunkt für Claude Code in diesem Projekt.

## Arbeitsweise: jeder Branch frisch von `main`

**Immer `git fetch origin main` und den neuen Branch von dort abzweigen** — nie
vom Stand des vorherigen Tickets, auch nicht, wenn dessen PR „gleich gemergt
wird". Zwei Zweige, die nacheinander entstehen, hängen sonst beide eine Zeile an
dieselbe Stelle in `backlog.md` (oben ins Archiv), und der zweite bekommt einen
Konflikt, sobald der erste drin ist. Genau so passiert, deshalb steht es hier:

```bash
git fetch origin main
git checkout -b claude/<thema> origin/main
```

Ist ein PR bereits gemergt, wird er nicht weiterbenutzt — neue Arbeit heißt
neuer Branch von `main`.

### Ausnahme: eine einzelne Textdatei darf direkt auf `main`

Eine übersichtliche Änderung an **genau einer** Textdatei — ein Backlog-Ticket,
eine Zeile Doku, ein korrigierter Tippfehler — geht ohne Branch und ohne PR
direkt auf `main`. Ein Review-Prozess für eine Zeile Prosa kostet mehr
Aufmerksamkeit, als er einbringt.

Alles andere bleibt beim PR: sobald **Code** betroffen ist oder **mehrere
Dateien**, ist der PR die Stelle, an der man die Änderung als Ganzes sieht.
Im Zweifel Branch — die Ausnahme ist für den offensichtlichen Fall gedacht,
nicht für den grenzwertigen.

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
wurde. Ausgelöst wurde er damals von der schlechten False-Positive-Rate des
Guards: ein Artikel über `localhost` traf die Injection-Regel. Diese Regel ist
seit #62 weg, der Defekt bliebe aber derselbe — ein Artikel *über*
Prompt-Injection zitiert nun einmal Angriffssätze. Alle Verbraucher — Anzeige,
Injektion, `/quellen` im Terminal — gehen deshalb durch diese eine Methode.
`inject_wiki_context`/`inject_briefing_context` behalten ihren `guard`-Parameter
als letzte Schranke vor dem Prompt.

Die Rolle ist weiterhin `system` — sie nach `user` zu verschieben ändert das
Antwortverhalten aller Personas und braucht einen Lauf am echten Modell (#60).

### Das Guard-Regelwerk: benannte Regeln, kurze Brücken (#62)
Die Muster in `security/tinyguard.py` sind `Rule(name, pattern)` statt roher
Regex-Strings, und `check_input`/`check_output` liefern den Namen als `rule` mit.
Der Korpus prüft ihn (`expect.rule`) — sonst sieht ein Fall, der aus dem
**falschen** Grund geblockt wird, genauso aus wie ein Erfolg. Beim Umbau ist
genau das aufgefallen: `ctx_weapon_instructions_in_article` wurde nie von der
Anleitungsregel gefangen, sondern von der Bau-Regel davor.

Zwei Entwurfsregeln, an denen die alte Liste gescheitert ist:

1. **Themenwörter sind keine Angriffe.** `localhost`, `http://127.0.0.1`,
   `file://`, `/etc/passwd`, `system32\config\sam` sagen nur, *worüber* ein Text
   spricht. Das Modell kann keine Dateien lesen — die Regeln haben nie etwas
   geschützt und dafür die eigenen Fragen des Projekts geblockt. Ersatzlos raus.
2. **Der Abstand zwischen Verb und Objekt ist der Präzisionskiller, nicht die
   Wortliste.** `\bübergehe\b.{0,80}\b(regeln)\b` verbindet über achtzig Zeichen
   fast jedes Verb mit fast jedem Substantiv. Brücken sind kurz und überspringen
   keine Teilsatzgrenze (`[^,.!?\n]` statt `.`) — eine Anweisung an das Modell
   steht am Stück, und „Wir bauen ein Modellflugzeug, keine Bombe" ist keine.

Gemessen an 20 alltäglichen Sätzen (lokale URLs, Code-Fragen, Rollenbitten):
**vorher 8 Fehlalarme, jetzt 0**, bei unveränderter Trefferzahl auf 18 Angriffen.

**Wer eine Injection-Regel ergänzt, legt in `evals/guard_redteam.yaml` den Satz
daneben, den sie nicht treffen darf** (`ok_…`). Ohne diese Gegenprobe ist eine
Verschärfung nicht messbar — die Recall-Seite meldet sich von selbst, die
Precision-Seite nie.

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

### Test-Doubles kommen aus `tests/doubles.py` (#67)
Streamer, Guard und Factory werden **nicht** von Hand nachgebaut, sondern über
`streamer_double()`, `permissive_guard_double()` und `factory_double()` bezogen.
Alle drei bauen auf `create_autospec(…, instance=True)`.

`factory_double()` belegt `get_auth_provider()` und `get_store()` mit den echten
Produktionsvorgaben (`DisabledAuth`, `NullStore`) vor — beide sind *falsy*, und
genau dort schlägt die stille Richtung sonst zu: `gradio_auth()` wäre ein Mock
statt `None`, `store.records` ein wahrer Mock statt `False`.

Der Grund ist ein Fehler, der an einem Tag viermal zuschlug — in zwei Richtungen:

| Richtung | Vorher | Jetzt |
|---|---|---|
| **laut** | `SimpleNamespace`/eigene Stub-Klassen fielen mit `AttributeError`, sobald der Produktivcode eine neue Methode rief | jede Methode des Originals ist automatisch da |
| **still, teuer** | ein nacktes `Mock()` liefert für *jedes* Attribut ein wahrheitswertiges Mock; `getattr(streamer, "guard", None)` bekam nie `None`, der Test blieb grün, und es fiel erst tief im Guard mit `'Mock' object is not subscriptable` | ein nie gesetztes Instanzattribut fehlt ehrlich, `getattr(…, None)` ergibt `None` |

**Klassen-Annotationen an den Kollaborateuren wären der falsche Weg.** Sie würden
`guard` und `persona_options` in `dir()` heben — und damit die stille Richtung
wieder öffnen. Ein Attribut, das noch niemand gesetzt hat, *soll* fehlen.

**Was `create_autospec` nicht abfängt:** *Setzen* unbekannter Attribute bleibt
erlaubt (kein `spec_set`, sonst ließe sich `persona_options` gar nicht
vorbelegen). Ein Tippfehler in der Vorbelegung bliebe also stumm — deshalb prüft
`test_the_presets_are_attributes_a_real_streamer_actually_has` sie gegen eine
echte Instanz. Wer eine Vorbelegung ergänzt, trägt sie dort nach.

Vorbelegt ist bewusst nur das Nötigste. `stream` liefert eine **Liste**, keinen
`iter([])` — ein Iterator wäre nach dem ersten Aufruf stumm leer.

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
  Fehlschlag); ein Gegentest schlägt an, sobald die Lücke geschlossen ist. Genau
  so ist #62 abgenommen worden: `ctx_code_snippet_in_article_is_kept` fing an zu
  bestehen, also musste das Flag fallen. `KNOWN_GAP_IDS` in
  `tests/test_evals_cli.py` ist damit wieder leer
- **Der Judge-Parser liest Markdown mit, aber nicht mehr (#71):** ein reales 8B-Modell
  antwortet `1: **5** | …` statt `1: 5 | …` — formattreu, nur fett. Vorher wurde daraus
  `score=None`, also ein Durchfaller trotz sauberer Bewertung; ein Baseline-Lauf hätte
  lauter Nullen gemessen. `_SCORE_LINE` erlaubt jetzt Auszeichnung *um* die beiden
  Zahlen (`**`, `__`, Backticks, Aufzählungszeichen, `Punktzahl:`, `5/5`) — die Zeile
  muss aber weiter mit der Erwartungsnummer beginnen und die Punktzahl eine einzelne
  1–5 sein. Jede Lockerung braucht die Gegenprobe, dass Ziffern im Fließtext weiterhin
  `None` ergeben; `unscored` ist die einzige Schranke gegen einen stumm durchgewinkten
  Judge
- `expect.rule` nennt die Regel, die einen Guard-Fall fangen *soll* (#62). Nur
  `reason` zu prüfen reicht nicht: ein Fall, der von der falschen Regel gefangen
  wird, sieht sonst aus wie ein Erfolg

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
  shared_without_login: false  # WebUI ohne Anmeldung trotzdem aufzeichnen (#72)

security:
  enabled: true
  guard: BasicGuard

email_adapter:
  enabled: false             # opt-in IMAP/SMTP-Bridge (Personas per Mail)
  allowed_senders: []        # PFLICHT bei enabled: true (#14e)
  max_body_chars: 4000       # Kappt Prompt *und* Antwortzitat (#14h)

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
| `data/conversations.sqlite3` | **das Gespräch**, wie der Nutzer es sieht — Verlauf (#25), später Suche (#49) und Fakten (#24) |
| `logs/conversation_*.json` | roher Mitschnitt der *Versuche* zum Debuggen, **opt-in** über `logging.conversation_jsonl` |

**Die Rollenverteilung stimmt erst seit #59.** Vorher schrieb `stream()` beides,
und damit protokollierte die Ablage Generierungs*versuche* statt des Gesprächs:
„Nochmal 🔄" hängte Frage und verworfene Antwort erneut an (dreimal gedrückt →
drei Fragen und drei Antworten im Store, während die Oberfläche eine zeigte),
„Stop ⏹" ließ die Antwort ganz weg, und Ask-All wie Self-Talk zeichneten gar
nichts auf, weil dort nie eine Gesprächs-ID gesetzt wurde.

Jetzt gilt: **die Oberfläche besitzt den Gesprächsstand, die Ablage spiegelt
ihn.** `stream()` schreibt nur noch den JSONL-Mitschnitt (der *soll* Versuche
festhalten); den Store bedient `record_conversation(messages)`, aufgerufen vom
Aufrufer, sobald der Turn steht. `ConversationStore.sync` ersetzt den ganzen
Nachrichtenverlauf statt anzuhängen — dadurch kann keine Buchführung mehr
auseinanderlaufen, und injizierter System-Kontext (Wiki, Briefing) bleibt
draußen, weil er zum Prompt gehört und nicht zum Gespräch.

Wer einen **neuen Antwortweg** baut, muss `record_conversation` aufrufen —
sonst ist er wieder spurlos wie Ask-All davor.

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

**Ohne Anmeldung wird nichts aufgezeichnet (#72).** `DisabledAuth` — der
Default — gibt *jedem* Besucher die Identität `local`. Alle Gespräche tragen
damit denselben Eigentümer, und die Eigentümerprüfung unten läuft ins Leere:
wer die Seite erreicht, sieht im Verlauf die Gespräche aller anderen, kann sie
fortsetzen und löschen. Deshalb liefert `AppFactory.get_store()` einen
`NullStore`, wenn `ui.type: web` ohne Anmeldung läuft — mit einer Meldung, die
beide Auswege nennt. Der ausdrückliche Weg in den gemeinsamen Topf ist
`storage.shared_without_login: true` (Default aus); dann warnt der Start einmal
laut, was geteilt wird. **Terminal und API sind nicht betroffen** — dort gibt es
keine Anmeldung, die fehlen könnte.

Die Web-UI fragt die Ablage, ob sie überhaupt schreibt (`store.records`), und
lässt die Verlauf-Karte sonst weg. Eine Karte über einem `NullStore` verspricht
etwas, das sich nie füllen kann — das galt auch schon bei
`storage.enabled: false`. Wer an der Karte etwas bindet, prüft deshalb auf
`None` (wie bei Ask-All); `test_the_app_still_starts_without_a_store` hält fest,
dass die App ohne sie startet.

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
jede Test-Session in die echte Datenbank. **Dieser Satz stimmte lange nicht ganz
(#64f):** die Fixture hängt an `Config._load_config`, und zwei Tests bauen sich
ein eigenes Config-Objekt, das dort nie vorbeikommt und kein `storage`-Feld
hatte. `build_store` nahm seinen Default, ein voller Lauf legte
`data/conversations.sqlite3` an (leer, aber da). Deshalb gibt es jetzt einen
zweiten Riegel: die Fixture biegt zusätzlich `storage.store.DEFAULT_STORE_PATH`
nach `tmp_path`. Wer künftig am ersten vorbeikommt, schreibt trotzdem nicht ins
Repo — und wer ein Config-Objekt von Hand baut, sollte es ohnehin nicht tun
(siehe `tests/doubles.py`).

### Anmeldung (#53): eine Naht, kein Sicherheitsprodukt
`src/auth/provider.py` beantwortet „wer bedient die UI". Drei Provider über
`ui.web.auth.provider`:

| Provider | Verhalten |
|---|---|
| `disabled` (**Default**) | kein Login, alle sind `local` — und deshalb zeichnet die WebUI nichts auf (#72) |
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

**Zwei Richtungen, zwei Reaktionen — der Unterschied ist Absicht:**

| Lage | Reaktion |
|---|---|
| `provider: local`, aber **kein Nutzer auflösbar** (meist ein nicht durchgereichtes `env:`) | **Abbruch** (`AuthConfigError`, Exit 4) |
| App horcht auf nicht-Loopback **ohne** konfigurierte Anmeldung | laute Warnung, Start läuft weiter |
| WebUI **ohne** Anmeldung, `storage.enabled: true` | Ablage bleibt aus, Verlauf-Karte weg (#72); `storage.shared_without_login: true` schaltet sie mit lauter Warnung wieder ein |

Der erste Fall bricht ab, weil dort jemand ausdrücklich Schutz konfiguriert hat
und ihn sonst stillschweigend verlöre; die frühere Begründung („lieber offen und
laut") unterstellt einen Tippfehler, der häufigere Auslöser ist aber eine
systemd-Unit ohne `EnvironmentFile` oder ein Container ohne `--env`. Der zweite
Fall warnt nur — „im Heimnetz ohne Login" ist ein legitimer Betriebsmodus.

`ui.web.host` steht seit dieser Runde auf **`127.0.0.1`**. Vorher war `0.0.0.0`
der Default, ohne dass es irgendwo stand.

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
Abgleich, nicht `extra="forbid"` — sonst blockiert jede neue Sektion sofort
alles.

**Der Abgleich läuft seit #66 rekursiv (`_extra_key_problems`).** Vorher traf er
nur die oberste Ebene, also genau die Ebene, auf der sich niemand vertippt:
`security` ist richtig geschrieben, `pii_protecton` darunter lief still ins
Leere — der Schutz war aus, und nichts sagte es. Dasselbe für `storage.enable`
und `ui.web.auth.user` (letzteres hat in #63 die Anmeldung entwertet).

Zwei Regeln fürs Weiterbauen, beide notwendig:

1. **Neue Config-Optionen gehören ins Modell**, nicht in eine Liste daneben. Die
   bekannten Keys werden aus den pydantic-Modellen abgeleitet (`model_extra`) —
   `KNOWN_TOP_LEVEL_KEYS` ist ersatzlos weg, weil zwei Quellen für dieselbe
   Wahrheit auseinanderlaufen. Fehlt ein Key im Modell, warnt der Start ab
   sofort **bei jedem Nutzer**; `test_every_section_of_the_shipped_config_is_modelled`
   hält die ausgelieferte Datei dagegen.
2. **Ein Mapping, dessen Keys der Nutzer bestimmt, bleibt `dict[str, Any]`** —
   `ui.web.auth.users`, `tts.voices`, `core.knowledge_cutoffs`,
   `email_adapter.address_persona_map`. Dort ist jeder Key gültig; die Rekursion
   steigt nur in echte Untermodelle ein. Sonst wäre jeder angelegte Nutzer eine
   Warnung — und Warnungen, die immer kommen, liest bald niemand mehr.

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
| **Broadcast/Ask-All** | Eine Frage an alle Personas; Antworten live tokenweise gestreamt als Markdown-Sektion pro Persona. WebUI streamt **parallel** (`iter_broadcast_events_parallel`: Worker-Thread + Queue pro Persona; Fallback `ui.experimental.broadcast_parallel: false`), Terminal sequenziell (`iter_broadcast_events`). Echter Speedup braucht `OLLAMA_NUM_PARALLEL` ≥ Persona-Zahl, sonst serialisiert Ollama. **Ein Token-Event trägt nur sein Token** (#64d) — der kumulative Text wurde pro Token neu gebaut und ins Event gelegt, also quadratisch in der Antwortlänge; wer den laufenden Text braucht, sammelt in einer Liste und fügt beim Anzeigen zusammen (so macht es die WebUI, ein paar Mal pro Sekunde statt einmal pro Token) |
| **Briefing (RSS)** | Gewählte Persona fasst die Feeds aus `briefing.feeds` zusammen (WebUI-Button „Briefing 📰" bzw. `/briefing` im Terminal). Kontext-Injektion wie beim Wiki (`briefing/feeds.py`); nicht erreichbare Feeds werden mit Hint übersprungen |
| **Quellen (#32)** | Zugeklapptes Accordion „Quellen 📚" unter dem Chat. Zeigt pro injiziertem Wikipedia-Snippet den Titel als Link auf kiwix-serve, die Herkunft und **den Snippet-Text selbst** samt Zeichenzahl (`1200 von 9800 Zeichen injiziert (gekürzt)` bzw. `51 Zeichen (vollständig)`). `wiki.snippet_limit` kürzt — erst die Anzeige macht sichtbar, was das Modell nie gesehen hat. Datenquelle ist `WikiSnippet` aus `wiki/lookup.py`; die Originallänge liefert der Proxy als `full_length` mit. Ask-All hat ein eigenes Accordion innerhalb seiner Gruppe (#32a), im Terminal zeigt `/quellen` denselben Inhalt ungekürzt. Meta-Zeile geteilt über `format_snippet_meta` |
| **Statuszeile (#36)** | Unter dem Chat: `Kontext █░░░ 424 / 8.192 Token (5 %) · 24,0 Tok/s · erster Token nach 1,9 s`. Füllstand aus `approx_token_count` + `num_ctx`, Tempo aus `StreamStats` (der Provider legt sie nach jedem Stream auf sich selbst ab). Ab `context_utils.threshold` (75 %) fett — ab da greift die Kompression. Wert nur im Schluss-Yield, sonst `gr.update()` |
| **Feedback (#40)** | 👍/👎 an jeder Bot-Bubble, append-only nach `logs/feedback_votes.jsonl`. **Eine Bot-Bubble ist nicht automatisch eine Modellantwort:** Wiki-Hinweise, die Meldung über verworfene Quellen, Briefing-Hinweise und die Kontext-Kompressionswarnung stehen in derselben Spalte und tragen ebenfalls einen Daumen. Erkannt wird das daran, dass Beiwerk **nie in der LLM-History** landet — wer eine neue Hinweis-Bubble einführt, bekommt den Schutz dadurch geschenkt, solange er sie nicht ins Kontextfenster gibt. Ein Vote, der sich nicht gegen die History prüfen lässt, wird verworfen: für einen Trainingsdaten-Kanal (#7) ist eine verlorene Bewertung billiger als eine erfundene. **Jede Zeile trägt seit #65 `conversation_id` + `message_index`** — ohne die ist ein Vote ein loses Textpaar, mit ihnen ein Join auf die Ablage (Persona, Modell, Zeitraum, Gesprächsverlauf davor). Der Index zählt **Positionen unter den Antwort-Bubbles**, nicht Texte: Hinweis-Bubbles stehen in der Anzeige zwischen den Antworten und in der Ablage nicht, und zweimal „Ja." im selben Gespräch ist keine Seltenheit. Den Wortlaut liefert die Ablage, nicht die Anzeige — gegen sie wird später gejoint. Ohne Anmeldung gibt es keine Ablage (#72); dann bleibt `conversation_id` leer und der Vote wird trotzdem geschrieben |
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
`_StreamModerator.feed()` rief `process_output` **pro Token über den gesamten
bisherigen Text** auf, war also quadratisch im Antwortumfang. Mit #58 behoben,
mit der ausgelieferten Config gemessen (nur `output_blocklist` aktiv):

| Antwort | vorher | jetzt |
|---|---|---|
| 200 Tokens (800 Zeichen) | 4 ms | 4 ms |
| 1000 Tokens (4.000 Zeichen) | 102 ms | 23 ms |
| 2000 Tokens (8.000 Zeichen) | 409 ms | 45 ms |
| 4000 Tokens (16.000 Zeichen) | **1.605 ms** | **85 ms** |

Der Holdback kostet weiterhin einmalig; der wachsende Anteil ist weg, weil der
Moderator nur noch ein Fenster um die Freigabegrenze prüft
(`_CONTEXT_WINDOW_CHARS`) statt alles Bisherige. `test_moderation_cost_stays_
linear_in_the_answer_length` hält das fest — es misst bewusst das *Verhältnis*,
nicht die absolute Zeit, damit es auf langsamen Runnern nicht flackert.

### ⚠️ Der Freigabe-Index läuft über den rohen Text, nicht über den maskierten
Die Maskierung ändert die Länge (`max@example.com` → `[PII]`). Zählt man mit,
wie viel vom *maskierten* Text schon raus ist, zeigt der Index nach dem ersten
Treffer auf die falsche Stelle: Modelltext verschwindet oder kommt doppelt
(belegt: aus „… Adresse [PII] und dann noch viel Text …" wurde ausgeliefert
„… Adresse vorname.nachname.abt**viel Text** …").

Deshalb zählt `_released` **rohe** Zeichen, und die Freigabegrenze darf nie
mitten in einem Treffer liegen — das prüft `BasicGuard.output_match_crossing`
und zieht sie sonst vor den Trefferanfang zurück. Nur dadurch liefert das
Maskieren eines Abschnitts *für sich* dasselbe Ergebnis wie über den ganzen
Text. Die Invariante steht als Test da: gestreamt muss herauskommen, was
`process_output` am Stück liefert — solange das Muster in den Holdback passt.
Passt es nicht, darf der Präfix durchrutschen; das ist die dokumentierte
Best-effort-Grenze und keine Regression.

**Aufgezeichnet wird, was der Moderator freigibt** — nicht der rohe Token.
Vorher sammelte `stream()` die Rohtokens, und bei `pii_protection: true` stand
im Store und im JSONL-Mitschnitt die unmaskierte Fassung, während der
Bildschirm maskiert war. Über Verlauf, Markdown-Export und JSON-Download kam
sie vollständig wieder heraus — die Maskierung war Bildschirmschoner statt
Datenschutz.

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

### ⚠️ Ein Link ist ein Reload, und ein Reload ist eine neue Sitzung (#69)
Der Theme-Umschalter waren zwei `<a href="?__theme=…">`. Ein Klick navigierte,
also lud die Seite neu, also bekam Gradio einen neuen `session_hash` — und
damit war **jeder** `gr.State` neu initialisiert: Persona, Streamer,
`conversation_state`, Gast. Im Browser nachgestellt: getippter, noch nicht
abgeschickter Text weg, zurück auf der Startseite. Beim Entwurf von #36 stand
das als „der Reload ist der Preis" im Code; der Preis war aber nie kosmetisch.

Dark-Mode ist im ausgelieferten Gradio-Bundle nichts als die Klasse `dark` am
`<body>` (Funktion `Ue` in `templates/frontend/assets/Index-*.js`). Der
Umschalter setzt sie jetzt selbst: ein `gr.Button` mit `fn=None` + `js=` —
für Gradio heißt das `backend_fn: false`, also **kein Request**. Die Wahl liegt
im `localStorage`, wiederhergestellt über `gr.Blocks(js=…)`.

Zwei Dinge, die beim Bauen wehtaten:
- Die Wiederherstellung muss **nach** Gradios eigener Initialisierung laufen
  (`Je()` liest `?__theme` bzw. `prefers-color-scheme`), sonst flackert es oder
  Gradio gewinnt — daher der `setTimeout(…, 0)`.
- Beide Skripte sind **je für sich vollständig**. Hinge der Klick am Lade-Skript,
  wäre ein früher Klick stumm wirkungslos.

Merksatz fürs Weiterbauen: alles, was rein clientseitig ist (Theme, Fokus,
Scrollen), gehört in `js=` — eine Navigation kostet die ganze Sitzung.

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
- **Quick Wins:** #53a Identität für API/Mail, #27 Ask-All-Moderator,
  #42 Perf-Benchmark (mypy läuft seit #52 über `src/core`; nächste Module bewusst einzeln)
- **Aus Review-Runde 2 (#57):** #58, #59, #62, #64, #65, #66 und #67 sind erledigt
  (Archiv), #14 bis auf den Server-Teil (#14a). Offen: #61 Gradio 5.x
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
#58 Moderator-Umschreibung, #59 Ablage = Gespräch, #62 Guard-Regelwerk, #67 Test-Doubles,
#54 Gesprächs-Ablage (SQLite), #25 Verlauf, #55 Review-Befunde, #57 Review-Befunde Runde 2.

### E-Mail-Adapter: die Reihenfolge ist die Regel (#14)

Der Adapter (`email_adapter/service.py`, opt-in) ist der einzige Kanal, über den
**Fremde** die Instanz erreichen — und der einzige, der unter der Domain des
Betreibers nach außen sendet. Vier Regeln, die man beim nächsten Umbau leicht
umdreht und die dann teuer sind:

1. **Geantwortet wird an `From`, nie an `Reply-To`.** Über `Reply-To` ließ sich
   die Instanz dazu bringen, an einen *Dritten* zu schreiben — mit gültigem
   SPF/DKIM der eigenen Domain und dem Text des Absenders im Zitat. Dieselbe
   Zeile speist die Schleifenerkennung; mit `Reply-To` war auch die umgehbar.
2. **Erst markieren, dann senden.** Andersherum kostet ein fehlgeschlagenes
   Markieren nicht *eine* Antwort, sondern *jede*: die Mail bleibt UNSEEN und
   wird bei jedem Poll neu beantwortet (gemessen: 4 Zyklen, 4 identische
   Antworten, `run_once()` meldete jedes Mal 0). `_mark_processed` fällt
   deshalb auf `\Seen` zurück, wenn das Verschieben scheitert.
3. **Ohne `allowed_senders` startet der Adapter nicht.** Fail-closed wie bei
   fehlenden Zugangsdaten: der Dienst kostet LLM-Läufe und verschickt Mail.
4. **Gekürzt wird einmal beim Lesen** (`max_body_chars`), nicht an jeder
   Verwendungsstelle — Prompt und Antwortzitat erben es dadurch.

Nicht behoben und deshalb ticketiert (#14a): der IMAP-Ordnertrenner wird
geraten statt per `LIST` erfragt. Regel 2 nimmt dem Fehler die Katastrophe.

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
- `feedback_votes.jsonl` — 👍/👎-Bewertungen (#40), append-only, eine Zeile pro Vote;
  seit #65 mit `conversation_id`/`message_index` als Schlüssel in die Ablage
