# CLAUDE.md — Yul Yen's AI Orchestra

Dieses Dokument ist der Einstiegspunkt für Claude Code in diesem Projekt. Es
enthält **Regeln, keine Geschichte**: was man wissen muss, damit beim nächsten
Umbau nichts still umfällt. Warum eine Regel gilt, was dabei gemessen wurde und
welche Annahme sich nicht bestätigt hat, steht in `docs/entwurf/`. Jede Regel
hier verweist darauf.

## Bevor du einen Bereich anfasst: lies seine Entwurfsdatei

| Du arbeitest an … | lies zuerst |
|---|---|
| Guard, Wiki-/RSS-Kontext, einem neuen Kontext-Kanal | [docs/entwurf/guard.md](docs/entwurf/guard.md) |
| WebUI, Gradio-Events, Sitzungszustand | [docs/entwurf/webui.md](docs/entwurf/webui.md) |
| Ablage, Verlauf, Suche, Anmeldung, Votes, Logs | [docs/entwurf/ablage-und-anmeldung.md](docs/entwurf/ablage-und-anmeldung.md) |
| Antwortzeit, Holdback, Stoppuhr | [docs/entwurf/latenz.md](docs/entwurf/latenz.md) |
| Tests, Test-Doubles, Browser-Test, Eval-Suite | [docs/entwurf/tests-und-evals.md](docs/entwurf/tests-und-evals.md) |
| RSS, Ask-All/Fazit, Mail-Adapter, API, Feature-Modi | [docs/entwurf/funktionen.md](docs/entwurf/funktionen.md) |
| `config.yaml`, Schema-Prüfung | [docs/entwurf/konfiguration.md](docs/entwurf/konfiguration.md) |
| Linter, mypy, CI, Pins, Audit | [docs/entwurf/werkzeuge.md](docs/entwurf/werkzeuge.md) |
| Version, Changelog, Tag | [docs/entwurf/versionierung.md](docs/entwurf/versionierung.md) |
| Branches, Doku-Pflicht, Sandbox | [docs/entwurf/arbeitsweise.md](docs/entwurf/arbeitsweise.md) |
| „Welche Datei macht was?" | [docs/entwurf/verzeichnisstruktur.md](docs/entwurf/verzeichnisstruktur.md) |

Die Überschriften sind beim Umzug (2026-09-29) **wortgleich** geblieben. Ein
älterer Verweis der Form „CLAUDE.md, Abschnitt „X"" — in Code-Kommentaren, im
Archiv, im Changelog — findet sich mit `grep -rn "X" docs/entwurf`.

## Arbeitsweise

- **Jeder Branch frisch von `main`**, nie vom Stand des vorherigen Tickets —
  sonst hängen zwei Branches beide oben in `backlog_archiv.md` und
  `CHANGELOG.md` an, und der zweite bekommt einen Konflikt:
  `git fetch origin main && git checkout -b claude/<thema> origin/main`.
  Ein gemergter PR wird nicht weiterbenutzt.
- **Prosa ohne Code darf direkt auf `main`**, wenn beide Fragen mit Nein
  beantwortet sind: *Ist Code betroffen?* (`config.yaml`, Ensemble-YAML und
  Locales zählen als Code) und *braucht es eine `CHANGELOG.md`-Zeile?* Ein
  Übersetzungspaar `docs/{de,en}/…` ist eine Änderung. Im Zweifel Branch.
- **Doku gehört zur Änderung, nicht danach.** Vor dem Commit durchsehen:

  | Was geändert wurde | Wo es nachgezogen werden muss |
  |---|---|
  | Makefile-Ziel, Testkommando, Marker | `docs/{de,en}/ReadMe.md`, `CONTRIBUTING.md` |
  | Config-Schalter | beide ReadMes (Schalterliste) + `config.yaml`-Kommentar |
  | Nutzerseitiges Verhalten | `docs/{de,en}/Features.md` **und** `CHANGELOG.md` unter `## [Unreleased]` |
  | Entwurfsentscheidung, Stolperfalle | `docs/entwurf/<bereich>.md` — und hier eine Zeile, siehe unten |
  | Ticketstand | `backlog.md`; Erledigtes wandert nach `backlog_archiv.md` |
  | Abhängigkeits-Pin | `requirements*.txt`-Kommentar; bei Bedarf `.pre-commit-config.yaml` |

  `tests/test_docs_consistency.py` prüft nur den mechanischen Teil (Kommandos
  gegen den Makefile). Ob ein Absatz noch stimmt, prüft kein Test. Ändert
  sich die deutsche Fassung, ändert sich die englische mit.
- **Datierte Berichte werden nicht nachgezogen** (`docs/modellwechsel_juni_2026.md`,
  veröffentlichte Changelog-Einträge, Archiv-Einträge). Ist eine Aussage
  überholt, kommt ein datierter Hinweis davor. Ein Protokoll, das keine
  Entscheidung festhält und auf das nichts verlinkt, darf dagegen weg.

### Wohin neue Regeln gehören

Diese Datei war bis zum 2026-09-29 auf 2083 Zeilen gewachsen — ein Achtel des
Quellcodes, bei jeder Sitzung komplett geladen. Die wichtigen Regeln standen
zwischen Messtabellen, und drei Abschnitte weiter widersprach sie sich selbst
(#77). Damit das nicht wieder passiert:

1. **Begründung, Messung, Geschichte → `docs/entwurf/<bereich>.md`.** Dort
   darf es ausführlich sein.
2. **Hierher kommt höchstens eine Zeile** — und nur, wenn die Regel beim
   nächsten Umbau *ohne Nachschlagen* umfallen würde. Mit Verweis.
3. Passt eine Regel in keinen Bereich, ist das ein Hinweis auf einen neuen
   Bereich, nicht auf einen neuen Abschnitt hier.

## Versionierung und Changelog (#74)

- Die Version steht in **`src/version.py`** und sonst nirgends;
  `CHANGELOG.md` trägt sie als oberste Überschrift
  (`tests/test_version_consistency.py`). Baseline ist 2.0.0 (2026-08-05).
- **Ins Changelog gehört nur, was ein Betreiber merkt** (Schalter, Default,
  Bedienelement, Pflichtfeld). Interner Umbau nicht. Die Zeile kommt **im
  selben PR** unter `## [Unreleased]`, auf **Englisch** — Changelog und
  `docs/en/` richten sich an den Betreiber, alles andere hier an den Entwickler.
- **Eine stille Verhaltensänderung ist ein Bruch** (MAJOR), auch wenn die
  Config gültig bleibt (#72). Eine Deprecation, die weitergelesen wird, nicht.
- Getaggt wird, wenn Yul „runder Stand" sagt — über die Releases-Oberfläche:
  **Pre-Release-Haken weg** (sonst 404 auf `/releases/latest`) und die
  generierten Notes **durch den Changelog-Eintrag ersetzen**.

Details: [versionierung.md](docs/entwurf/versionierung.md).

## Wo diese Sitzung läuft — und was dort fehlt

| | Sandbox | Yuls Kiste |
|---|---|---|
| Abhängigkeiten | kommen **leer** an (Hook installiert) | eingerichtetes venv |
| Clone | **flach** — `git tag` schweigt, `git log --reverse` lügt (Hook vertieft) | vollständig |
| Ollama, Modell | nicht da → `@pytest.mark.ollama` wird übersprungen | da |
| spaCy `de_core_news_lg` | nicht da → Keyword-/Wiki-Tests übersprungen | da |
| Playwright | Paket fehlt, **Chromium liegt aber** unter `/opt/pw-browsers` | nach Bedarf |
| Kiwix/ZIM, Piper, faster-whisper, echter Mailserver, Windows | nichts davon | teils |
| `git push` | Branches und `main` ja, **Tag-Refs nein** (403 vom Gateway) | alles |

- **Vor jeder Aussage über die Historie** (Tags, Alter, Commit-Zahl):
  `git rev-parse --is-shallow-repository`, bei `true` erst
  `git fetch --unshallow origin`. `v1.0.0` wäre fast überschrieben worden.
- Der Hook `.claude/hooks/session-start.sh` läuft **nur remote**, endet
  **immer mit 0** und holt das spaCy-Modell **bewusst nicht**.
- Was die Sandbox nicht prüfen kann, gehört in „Nicht geprüft" der PR-Vorlage.

Details: [arbeitsweise.md](docs/entwurf/arbeitsweise.md).

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
| Web-UI | Gradio 6.22 |
| API | FastAPI + Uvicorn |
| NLP/Wiki | spaCy + Kiwix/Wikipedia |
| TTS | Piper (ONNX; Terminal: Autoplay über winsound/CLI-Player, WebUI: Browser-Playback) |
| STT | faster-whisper (optional, WebUI-Mikro) |
| Security | BasicGuard (tinyguard.py) |
| Tests | pytest |
| Formatting | Black (88), Ruff |
| Schichten | import-linter (Verträge in `pyproject.toml`) |
| Typen | mypy über das ganze `src` (Linux **und** `--platform win32`) |

## Verzeichnisse

| Pfad | Inhalt |
|---|---|
| `src/launch.py` | Einstieg (`--doctor`, `--list-ensembles`, `--version`) |
| `src/core/` | LLM-Abstraktion, Streamer + Moderator, Orchestrator (Ask-All), Fazit, AppFactory, Kontext-Kanäle, Karl |
| `src/config/` | Config-Singleton, Ensemble-Loader, pydantic-Schema, i18n |
| `src/ui/` | WebUI (aufgeteilt in Layout/Format/Chat/Features/Events), Terminal, Sitzung, Feedback, Verlauf, Self-Talk |
| `src/api/` | FastAPI (`/ask`, `/health`, `/healthz`) + OpenAI-kompatibles `/v1` |
| `src/security/tinyguard.py` | BasicGuard: benannte Regeln für Eingang, Kontext und Ausgang |
| `src/wiki/`, `src/rss/` | die zwei Kontextquellen |
| `src/storage/`, `src/auth/` | Gesprächs-Ablage (SQLite) und Identitäts-Naht |
| `src/email_adapter/`, `src/tts/`, `src/stt/` | opt-in Kanäle |
| `src/evals/`, `src/bench/` | Eval-Suite und Stoppuhr; Einstiege in `scripts/` |
| `src/version.py` | die einzige Quelle der Version |
| `evals/` | Eval-Korpora als YAML (Guard-Red-Team, Personas, Karl) |
| `ensembles/<name>/` | `personas_base.yaml` + `locales/{de,en}/personas.yaml` |
| `locales/{de,en}.yaml` | UI-Texte, Parität per Test |
| `backlog.md` / `backlog_archiv.md` | offene Tickets / Erledigtes samt Begründung |

Datei für Datei: [verzeichnisstruktur.md](docs/entwurf/verzeichnisstruktur.md).

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
Ein optionales `config.local.yaml` (gitignored) wird per Deep-Merge darübergelegt
— nie committen, Passwörter über `env:NAME`.

### LLM-Abstraktion
- `LLMCore` (abstrakt) → `OllamaLLMCore` (Produktion) / `DummyLLMCore` (Tests)
- Swappable ohne UI/API-Änderungen

### Streaming-Flow
```
User-Input ──→ SecurityGuard (Eingang) ──┐
spaCy → Wiki-Proxy (8042) ──→ Guard (Kontext) ──┤
rss/feeds.py (RSS-Cache) ──→ Guard (Kontext) ──┘
                                          → Ollama
           → Token-Stream → SecurityGuard (Ausgang) → UI + TTS + JSON-Log
```

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

## Regeln, die still umfallen

Jede Zeile ist eine Entscheidung, die wie ein Detail aussieht. Die Begründung —
meist ein Fehler, der genau so passiert ist — steht in der verlinkten Datei.

### Guard und Kontext → [guard.md](docs/entwurf/guard.md)

- **Der Guard hat zwei Eingänge.** Abgerufener Fremdtext geht **nur** über
  `core/context_channels.inject_context` — ein dritter Kanal wird in `CHANNELS`
  eingetragen, nie `injected_message` direkt (AST-Test in
  `tests/test_context_channels.py`).
- **Erst filtern, dann zusammenfügen.** Guard-Brücken mit `\s+` überspringen
  Zeilenumbrüche; zwei harmlose Schlagzeilen ergeben zusammen einen Treffer.
- **Gefiltert wird in `WikiLookup.snippets()`**, sonst zeigt die Quellen-Karte
  Quellen, die das Modell nie sah.
- **Die Rollentrennung (#60) ist kein Schutz** — ein 8B-Modell befolgt
  eingeschleuste Anweisungen unabhängig von der Rolle. Was wirkt, ist der Guard,
  und der fängt an echten ZIM-Artikeln nur 6 von 33 Umformulierungen.
- **Neue Regel: erst fragen, ob der Nutzer das darf.** Wenn ja (Persona
  umdefinieren, Antwortformat vorgeben), gehört sie in `check_context_only`.
- **Neue Injection-Regel = Gegenprobe daneben** (`ok_…` in
  `evals/guard_redteam.yaml`) und `expect.rule`. Keine Themenwörter, kurze
  Brücken ohne Teilsatzgrenze (`[^,.!?\n]`), keine Vergangenheitsformen in
  Absichtsmarkern. `known_gap`/`KNOWN_GAP_IDS` schlagen in beide Richtungen an.
- Nachmessen am echten Modell: `python scripts/probe_injection.py -e classic`.
  Eine konditionale Nutzlast braucht ihre eigene Frage (`Payload.frage`).

### Latenz → [latenz.md](docs/entwurf/latenz.md)

- **Der Guard-Holdback bestimmt die wahrgenommene Antwortzeit** — zwei Drittel
  entstehen nach dem Modell. Default 32, weil das AWS-Secret-Muster erst ab 30
  vollständig verdeckt ist. Ist die Antwort kürzer als der Holdback, streamt
  sie gar nicht.
- **`_released` zählt rohe Zeichen**, nicht maskierte; die Freigabegrenze darf
  nie in einem Treffer liegen (`output_match_crossing`). Aufgezeichnet wird,
  was der Moderator freigibt, nicht der Rohtoken.
- Der Moderator prüft nur ein Fenster um die Freigabegrenze — nie wieder alles
  Bisherige pro Token (war quadratisch).
- **Stoppuhr: erstes ausgeliefertes Zeichen und Zeichen/s vergleichen, nie die
  Gesamtdauer.** Rundenweise messen, Median, Fehlermeldung ist keine Bestzeit.
  Der Fragensatz liegt in `src/bench/questions.py` (ändern = Vergleichbarkeit
  aufgeben). Das Skript heißt `run_bench.py`, weil `bench.py` das Paket verdeckt.

### Ablage der Gespräche → [ablage-und-anmeldung.md](docs/entwurf/ablage-und-anmeldung.md)

- **Die Oberfläche besitzt den Gesprächsstand, die Ablage spiegelt ihn.**
  `stream()` schreibt nur den JSONL-Mitschnitt; wer einen **neuen Antwortweg**
  baut, ruft `record_conversation(messages)`, sonst bleibt er spurlos.
- **Ask-All und Self-Talk: offen (#77).** Der Code zeichnet seit #59 auf
  (`app: ask-all`/`self-talk`), eine Entscheidung vom 2026-08-05 sagt
  „bewusst nicht". Bis #77 entschieden ist, auf keine der beiden Seiten bauen.
- **Ohne Anmeldung zeichnet die WebUI nichts auf (#72)** — `NullStore`; die
  Verlauf-Karte hängt an `store.records` und kann `None` sein.
- **Die WebUI setzt bei `load()`/`delete()`/`search()` immer `user`** — die
  Auswahl im Dropdown ist keine Schranke. Fremd = nicht existent.
- **Migrationen nur anhängen**, jeder Schritt in `BEGIN`/`COMMIT`. Ein
  optionaler Schritt (`_OPTIONAL_MIGRATIONS`, z. B. FTS5) hält die Kette an,
  statt die ganze Ablage zum `NullStore` zu machen.
- **Sucheingabe ist Text, nicht FTS5-Syntax** (`_fts_query` quotet jedes Wort).
- Aufzeichnen darf **nie** den Stream abbrechen. Votes liegen in
  `data/feedback_votes.jsonl`, nicht in `logs/` (das ist wegwerfbar).
- **Anmeldung:** `provider: local` ohne auflösbaren Nutzer bricht den Start ab;
  `header` nur hinter einem Proxy, der den Header von außen entfernt.

### WebUI und Gradio → [webui.md](docs/entwurf/webui.md)

- **Sitzungszustand gehört in `SessionContext` (`gr.State`), nie an `self`** —
  die `WebUI` ist ein Singleton für alle Browser. Der Default muss
  `deepcopy`-fähig sein.
- **Button-Updates in denselben Yield** (`ChatController.with_controls`), nie
  als eigenes Event davor (+3,5 s). `cancels` bricht nur gequeuete Events ab und
  schließt keine Generatoren — für Abbruch einen Kill-Switch (`threading.Event`).
- **Ein Aufgerufener setzt den Kill-Switch seines Aufrufers nicht**; und für
  einen Zusammenbau, der an einer Nebenwirkung hängt, mindestens ein Test gegen
  das echte Gegenstück, nicht gegen eine Attrappe.
- **`content` kommt als Liste zurück** — jeder Leser geht durch
  `webui_format.bubble_text`. `evt.index` ist flach; ein nicht deutbarer Index
  wird verworfen, nicht geraten.
- **`launch(js=…)` will einen Anweisungsblock, `click(js=…)` eine
  Pfeilfunktion** — die Verwechslung ist stumm. Ein Link ist ein Reload und
  damit eine neue Sitzung; alles rein Clientseitige gehört in `js=`.
- Die Konsolenwarnung „Too many arguments provided for the endpoint" ist
  normal. `gr.Dataframe` nicht für live wachsende Ausgaben.
- **Ein Modul bekommt eine Regel, nicht hundert Zeilen.** Keine delegierenden
  Wrapper; was weitergereicht wird, kommt beim Bauen herein.

### Funktionen → [funktionen.md](docs/entwurf/funktionen.md)

- **RSS:** Guard pro Meldung vor dem Zusammenfügen; `items_for` holt nie selbst
  (Hintergrund-Thread startet in `launch.py`, nicht in der Factory); nur Plural
  löst aus; ein Personenbezug schlägt alles.
- **Ask-All-Fazit:** das Häkchen ist die Entscheidung (kein Config-Schalter);
  kein Kontext-Kanal, weil eigene, schon moderierte Ausgabe; genau **eine**
  `user`-Nachricht; gekürzt mit Marker; von der ruhigsten Persona nur
  `INHERITED_OPTIONS` (`config.personas.quietest_persona_name`).
- **Broadcast:** ein Token-Event trägt nur sein Token (sonst quadratisch).
- **Mail-Adapter:** Antwort an `From`, nie `Reply-To`; **erst markieren, dann
  senden**; ohne `allowed_senders` kein Start; einmal beim Lesen kürzen.
- **API:** `model` = Persona; `api_key` gilt für **alle** Endpunkte
  (`check_api_access`); OpenAI-Fehler mit `{"error": …}` auf oberster Ebene;
  Sampling-Parameter werden ignoriert.

### Konfiguration → [konfiguration.md](docs/entwurf/konfiguration.md)

- **Neue Config-Option = Feld im pydantic-Modell** (`config/schema.py`), keine
  Liste daneben. Unbekannte Keys warnen rekursiv; Mappings mit Nutzer-Keys
  bleiben `dict[str, Any]`. Beim Start nur Warnung, `--doctor`/`/healthz` hart.
- Tests setzen `YULYEN_SKIP_LOCAL_CONFIG=1` und `storage.enabled: false`
  (autouse in `tests/conftest.py`); ein Config-Objekt baut man nicht von Hand.

## Tests und Kommandos → [tests-und-evals.md](docs/entwurf/tests-und-evals.md)

```bash
make check          # lint → lint-imports → types → test; vor jedem Push
make test           # Suite ohne slow/ollama/browser
make test-browser   # laufende WebUI im echten Chromium (~100 s)
make evals          # Guard-Red-Team ohne Modell
make bench          # Stoppuhr, braucht Ollama
```

- **Test-Doubles aus `tests/doubles.py`** (`create_autospec`), nie `Mock()` oder
  `SimpleNamespace` — ein nacktes Mock ist für jedes Attribut wahr.
- **Nach einem Gradio-Bump `make test-browser` von Hand** — kein anderes Gate
  schaut dorthin. Rollen-Selektoren, Locale festnageln, nie `networkidle`.
- **Evals: den Ø-Judge-Score vergleichen, nicht die Bestehensquote** (27 %
  gegen 1,9 % Streuung). Baseline für #7: Ø 3,73.

## Werkzeuge → [werkzeuge.md](docs/entwurf/werkzeuge.md)

### Pre-commit / Versions-Pinning (wichtig!)

Black und Ruff sind in `requirements-dev.txt` **und** `.pre-commit-config.yaml`
gepinnt — nur synchron ändern. Nach dem Clone: `pip install -r
requirements-dev.txt && pre-commit install`. Urteilt ein gepinntes Werkzeug
plötzlich anders, zuerst `python -m <tool> --version` gegen den Pin halten
(`gradio` zieht `ruff` als eigene Abhängigkeit).

#### ⚠️ Bekannte Falle: PATH-Shadowing (ist schon mehrfach passiert!)

**`python -m black`, `python -m ruff`, `python -m pytest`, `python -m mypy`** —
nie das nackte Binary. Im PATH liegt oft eine andere Version oder ein anderer
Interpreter.

- **Ein Prüfer, der abbricht, meldet weniger Fehler, nicht keine** — nach dem
  Einhängen einmal `checked N source files` ansehen.
- **import-linter:** eine neue Aufwärts-Abhängigkeit ist eine benannte Ausnahme
  mit Grund, keine stille. Greift eine Mutationsprobe nicht, erst nachsehen, ob
  die Mutation überhaupt im Code steht.
- **Audit-Allowlist und `known_gap` schlagen in beide Richtungen an**; ein
  Eintrag ohne Begründung ist ein Stummschalter.
- Wer einen CI-Job ändert, stellt auch seine Installationsmenge nach.

## Das Training läuft nicht in diesem Repo (#7)

`transformers` ist hier **absichtlich** nicht importierbar: Gradio 6 verlangt
`huggingface_hub>=1.0`, `transformers` 4.43 `<1.0`. Den ImportError nicht
„reparieren" und kein Trainings-venv daneben anlegen — die LoRA-Strecke lebt im
privaten Repo `YY_AI_Trainingground`. Hierher gehört nur der Vergleich
(Eval-Suite, Baseline).

## Backlog

[backlog.md](backlog.md) sind die offenen Tickets mit Effort/Benefit,
[backlog_archiv.md](backlog_archiv.md) das Erledigte samt Begründung — die
ausführliche Projektgeschichte.
