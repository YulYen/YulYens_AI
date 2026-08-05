# Yul Yen’s AI Orchestra

**Yul Yen’s AI Orchestra** ist eine lokal laufende KI-Umgebung, die mehrere **Personas** (Leah, Doris, Peter, Popcorn) vereint.
Sie alle basieren auf einem lokalen LLM (aktuell über [Ollama](https://ollama.com/) oder kompatible Backends) und bringen eigene Charaktere und Sprachstile mit.

Das Projekt unterstützt:
- **Terminal-UI** mit farbiger Konsolenausgabe & Streaming
- **Web-UI** auf Basis von [Gradio](https://gradio.app) (Standard: nur vom eigenen Rechner erreichbar, siehe `ui.web.host`)
- **Ask-All/Broadcast**: eine Frage an alle Personas, Antworten live und parallel gestreamt
- **AI-Dialog (Self-Talk)** zwischen zwei Personas (Terminal + Web)
- **Text-to-Speech (TTS)** mit Piper: automatische WAV-Erstellung im Terminal, „Vorlesen"-Knopf in der Web-UI
- **Spracheingabe (STT)** in der Web-UI: Mikrofon neben dem Eingabefeld (opt-in via faster-whisper)
- **API (FastAPI)** zur Integration in externe Anwendungen (inkl. `/healthz`-Deep-Check und OpenAI-kompatiblen `/v1`-Endpunkten)
- **E-Mail-Adapter** (opt-in): Personas beantworten Mails per IMAP/SMTP
- **Wikipedia-Integration** (online oder offline via Kiwix-Proxy)
- **Nachrichten als Quelle (RSS)**: Feeds im Hintergrund, Meldungen kommen als Kontext dazu, wenn die Frage danach ist
- **Gesprächs-Ablage** in SQLite mit Verlauf, Fortsetzen, Markdown-Export und optionaler Anmeldung
- **Sicherheits-Filter** (Prompt-Injection-Schutz, PII-Erkennung, Wrongdoing-Guardrail)
- **Setup-Doktor** (`--doctor`) für Preflight-Checks mit konkreten Fix-Hinweisen
- **Logging & Tests** für stabile Nutzung


siehe auch: [Features.md](Features.md)

---

## Ziele

- Bereitstellung einer **privaten, lokal laufenden KI** für deutschsprachige Interaktion
- Mehrere **Charaktere mit unterschiedlichem Stil**:
  - **Leah**: empathisch, freundlich
  - **Doris**: sarkastisch, humorvoll, frech
  - **Peter**: faktenorientiert, analytisch
  - **Popcorn**: verspielt, kindgerecht
- **Erweiterbares Fundament** für zukünftige Features (z. B. LoRA-Finetuning, Tool-Use, RAG)
- **KISS-Prinzip**: einfache, nachvollziehbare Architektur

---

## Architekturüberblick

- **Konfiguration**: Alle Einstellungen zentral in `config.yaml`
- **Core**:
  - Austauschbarer LLM-Core (`OllamaLLMCore`, `DummyLLMCore` für Tests) samt `YulYenStreamingProvider`
  - Wikipedia-Support inkl. spaCy-basiertem Keyword-Extractor
- **Personas**: Systemprompts & LLM-Optionen als YAML unter `ensembles/<name>/`; `src/config/personas.py` lädt sie
- **UI**:
  - `TerminalUI` für CLI
  - `WebUI` (Gradio) mit Persona-Auswahl & Avataren
  - Optionaler Ask-All/Broadcast-Modus (per `ui.experimental.broadcast_mode`) über die Ask-All-Option im Terminal-Startmenü und die Ask-All-Kachel in der Web-UI — die Antworten werden tokenweise live gestreamt
- **API**: FastAPI-Server (`/ask`-Endpoint für One-Shot-Fragen, `/health` als Liveness-Stub, `/healthz` als Deep-Check)
- **Kontext-Management**: bei langen Chats wird die History automatisch komprimiert — heuristisch (Standard) oder per LLM-Zusammenfassung („Karl", `context_management.strategy: "karl"`)
- **E-Mail-Adapter**: optionaler IMAP/SMTP-Dienst, der eingehende Mails einer Persona zuordnet und beantwortet (Details in [Features.md](Features.md))
- **Gesprächs-Ablage**: die Gespräche liegen in SQLite (`storage.path`), nicht in Logdateien — der Verlauf in der Web-UI liest von dort
- **Logging**:
  - Systemlogs in `logs/`; der rohe JSONL-Mitschnitt eines Turns ist ein Debug-Artefakt und standardmäßig aus (`logging.conversation_jsonl`)
  - Wiki-Proxy schreibt separate Logdateien

---

## Voraussetzungen

- **Python 3.10+** — geprüft wird in der CI gegen 3.10 und 3.13
- **Ollama** (oder anderes kompatibles Backend) mit installiertem Modell, z. B.:
  ```bash
  ollama pull ministral-3:8b
  ```
  (Das Default-Modell steht in `config.yaml` unter `core.model_name`; eine Bewertung
  verschiedener Modelle findet sich in [modellwechsel_juni_2026.md](../modellwechsel_juni_2026.md).)
- Für Tests ohne Ollama kann `core.backend: "dummy"` gesetzt werden – das Echo-Backend kommt ohne
  zusätzliche Downloads aus und eignet sich für CI oder schnelles Prototyping.
- Optional für Offline-Wiki:
  - [Kiwix](https://kiwix.org/) + deutsches ZIM-Archiv — Installation & Update: [Kiwix_Setup.md](Kiwix_Setup.md)

---

## Installation

```bash
git clone https://github.com/YulYen/YulYens_AI.git
cd YulYens_AI

# Virtuelle Umgebung erstellen
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt
```

### Sprachmodell für spaCy

Für die Wikipedia-Integration wird ein spaCy-Modell benötigt, das zur eingestellten Sprache passt. Der Keyword-Finder ermittelt das passende Paket jetzt über die Kombination aus `language` und `wiki.spacy_model_variant` anhand der Zuordnung in `wiki.spacy_model_map` in der `config.yaml`. Die Modellauswahl bleibt damit vollständig konfigurierbar – ohne hart codierte Vorgaben.

Beispiel:

```yaml
language: "de"
wiki:
  spacy_model_variant: "large"
  spacy_model_map:
    de:
      medium: "de_core_news_md"
      large:  "de_core_news_lg"
```

Zusätzlich muss das jeweilige Modell manuell installiert werden:

```bash
# Mittleres Modell (Kompromiss zwischen Größe und Genauigkeit)
python -m spacy download de_core_news_md

# Großes Modell (genauer, aber langsamer und speicherintensiver)
python -m spacy download de_core_news_lg
```

---

## Nutzung

### Konfiguration (`config.yaml`)

Alle zentralen Einstellungen werden über `config.yaml` gesteuert. Wichtige Schalter:

- `language`: steuert UI-Texte und Persona-Prompts (`"de"` oder `"en"`).
- `ui.type`: wählt die Oberfläche (`"terminal"`, `"web"` oder `null` für nur API).
- `ui.web.host`: **Standard `127.0.0.1`** — die Web-UI ist dann nur vom eigenen Rechner aus erreichbar. Auf `"0.0.0.0"` stellen, wenn andere im Netz sie benutzen sollen; dann aber `ui.web.auth` einschalten, sonst warnt der Start (zu Recht) laut.
- `ui.web.auth.provider`: Anmeldung der Web-UI — `disabled` (Standard), `local` (Nutzer aus `ui.web.auth.users`, Passwörter als `env:NAME`) oder `header` (Identität von einem vorgeschalteten Proxy). Gilt **unabhängig** von `ui.web.share`. Das frühere `ui.web.share_auth` wirkt nur noch als Fallback und wird beim Start angemahnt.
- `storage.enabled`: die Gesprächs-Ablage (SQLite unter `storage.path`), Grundlage für Verlauf, Fortsetzen und Markdown-Export. **Ohne Anmeldung zeichnet die Web-UI trotzdem nichts auf** — alle Besucher wären derselbe Nutzer `local` und sähen gegenseitig ihre Gespräche. Wer das für den Einzelplatz ausdrücklich will, setzt `storage.shared_without_login: true`; der Start warnt dann einmal laut. `storage.history_limit` steuert die Länge der Verlauf-Liste, `storage.file_exchange` den JSON-Down-/Upload.
- `tts.enabled`: schaltet Text-to-Speech ein/aus.
- `tts.features.terminal_auto_create_wav`: erzeugt im Terminal-Modus pro Antwort eine WAV-Datei und spielt sie ab — Windows über `winsound`, Linux/macOS über `paplay`/`aplay`/`ffplay` bzw. `afplay`. Ohne verfügbaren Player bleibt es bei der Datei in `out/`.
- `api.openai_compatible`: schaltet die OpenAI-kompatiblen Endpunkte frei (`/v1/models`, `/v1/chat/completions`), mit denen fremde Clients wie Open WebUI mit den Personas sprechen. **Sobald `api.host` nicht mehr auf `127.0.0.1` steht, gehört hier ein `api_key` gesetzt** — am besten als `"env:YULYEN_API_KEY"` statt im Klartext. `rate_limit_per_minute` begrenzt Anfragen pro Client.
- `email_adapter.allowed_senders`: **Pflichtfeld, sobald `email_adapter.enabled: true` steht.** Nur wer hier eingetragen ist, bekommt eine Antwort — als volle Adresse (`max@example.org`) oder als ganze Domain (`@meine-domain.de`). Fehlt die Liste, startet der Adapter nicht und schreibt den Grund ins Log; die übrige Anwendung läuft weiter. **Beim Aktualisieren einer bestehenden Installation ist das der eine Handgriff, den man nachziehen muss** — vorher konnte jeder, der die Persona-Adresse kennt, die Personas fahren. Verwandt: `email_adapter.max_body_chars` begrenzt, wie viel Mailtext übernommen wird (Prompt *und* Zitat in der Antwort).
- `rss.enabled`: **ein Schalter für Nachrichten** — Hintergrund-Abruf, automatische Verwendung als Quelle und den Briefing-Knopf. Die Sektion hieß früher `briefing:`; der alte Name wird weiterhin gelesen, beim Start aber angemahnt. `rss.show_button` blendet nur den Knopf aus, `rss.max_chars_per_item` begrenzt, wie viel je Meldung ins Kontextfenster geht.
- `security.stream_holdback_chars`: **die Stellschraube, wenn die Antwort „spät losläuft".** Der Ausgangs-Guard hält so viele Zeichen zurück, damit ein Passwort oder eine E-Mail-Adresse nicht schon halb sichtbar ist, bevor er sie erkennt. Der Preis: vor so vielen Zeichen erscheint gar nichts. Im Browser gemessen (24 Zeichen/s): `96` → erstes Wort nach ~4,1 s, `32` (Standard) → ~1,9 s, `0` → ~0,4 s. Der Standard 32 ist auf den typischen Fall gemünzt: lokal, ein Nutzer. **Auf 96 erhöhen**, sobald der Server für andere erreichbar ist (`api.host`/`ui.web.host` ≠ `127.0.0.1`, Gradio-Share-Link, E-Mail-Adapter) oder echte Zugangsdaten in den Gesprächen vorkommen — dann bleibt auch der Text *um* ein Secret herum verdeckt.

Beispiel:

```yaml
language: "de"
core:
  # Backend auswählen: "ollama" (Standard) oder "dummy" (Echo-Backend für Tests)
  backend: "ollama"
  # Standardmodell für Ollama
  model_name: "ministral-3:8b"
  # URL des lokal laufenden Ollama-Servers (Protokoll + Host + Port).
  # Dieser Wert muss explizit gesetzt werden – es gibt keinen stillen Default.
  ollama_url: "http://127.0.0.1:11434"
  # Warm-up: Modell beim Start im Hintergrund vorladen, damit die erste Frage
  # ein warmes Modell trifft. Die App startet auch, wenn Ollama nicht läuft.
  warm_up: true
  # Wie lange Ollama das Modell nach einem Request im Speicher hält (Sekunden).
  # -1 = für immer geladen lassen, 0 = sofort entladen.
  keep_alive: 600

ui:
  type: "web"        # Alternativen: "terminal" oder null (nur API)
  web:
    host: "127.0.0.1"  # Standard: nur lokal. "0.0.0.0" öffnet die UI ins Netz
    port: 7860
    share: false       # Optional: öffentlicher Gradio-Share-Link
    auth:
      provider: "disabled"   # disabled | local | header — gilt unabhängig von `share`

wiki:
  mode: "offline"    # "offline", "online" oder false (deaktiviert)
  spacy_model_variant: "large"  # Alternativen: "medium" oder direkter Modellname
  proxy_port: 8042
  snippet_limit: 1200           # Maximale Länge eines einzelnen Snippets in Zeichen
  max_wiki_snippets: 2          # Wie viele verschiedene Snippets maximal in den Prompt injiziert werden dürfen
```

> 💡 **Lokale Overrides:** Eine optionale `config.local.yaml` (gitignored, neben der
> `config.yaml`) wird per Deep-Merge über die Hauptkonfiguration gelegt. So bleiben
> persönliche Werte (z. B. echte Mail-Zugangsdaten für den E-Mail-Adapter) aus dem
> öffentlichen Repository heraus. Passwörter zusätzlich via `env:NAME`-Platzhalter.

#### LLM-Backends

Der Schlüssel `core.backend` entscheidet, welcher LLM-Core zum Einsatz kommt:

- `ollama` *(Standard)* bindet einen laufenden Ollama-Server ein. Dafür muss das Python-Paket
  [`ollama`](https://pypi.org/project/ollama/) installiert sein (z. B. via `pip install ollama`),
  und `core.ollama_url` zeigt auf die Ollama-Instanz.
- `dummy` nutzt den `DummyLLMCore`, der jede Eingabe als `ECHO: …` zurückgibt. Das ist ideal für
  Unit-Tests, Continuous Integration oder Demos ohne verfügbares LLM. In diesem Modus reicht ein
  Platzhalter für `core.ollama_url`; weder ein laufender Ollama-Server noch das Python-Paket sind nötig.

#### Security-Guard

Der Abschnitt `security` wählt den Guard für Ein- und Ausgabekontrollen aus:

- `security.guard: "BasicGuard"` (Standard) lädt den eingebauten Basisschutz. Die Schalter
  `prompt_injection_protection`, `pii_protection`, `output_blocklist` und
  `wrongdoing_protection` bestimmen, welche Prüfungen aktiv sind. Der Wrongdoing-Guardrail
  (Gewalt-/Waffenanfragen) prüft jede Eingabe für sich; ein Treffer blockt nur diese Anfrage.
  Optional hält `wrongdoing_lock_turns` (Standard `0` = aus) nach einem Treffer die nächsten
  *N* Eingaben gesperrt und fängt so Umgehungsversuche ohne Triggerwort ab („ist nur für
  einen Roman…").
- `security.guard: "DisabledGuard"` deaktiviert die Prüfungen über einen Stub. Die Aliasse
  `"disabled"`, `"none"` und `"off"` werden ebenfalls akzeptiert.
- `security.enabled: false` deaktiviert die Guard-Logik vollständig, unabhängig vom gewählten Namen.

#### Wikipedia (Proxy & Autostart)

- Im Offline-Modus (`wiki.mode: "offline"`) kann `kiwix-serve` automatisch gestartet werden, wenn `wiki.offline.autostart: true` gesetzt ist.
- `wiki.max_wiki_snippets` begrenzt, wie viele unterschiedliche Wikipedia-Ausschnitte pro Frage in den Prompt aufgenommen werden (Standard: 2). So lassen sich Mehrfachtreffer nutzen, ohne den Kontext zu überfrachten.

### Start

```bash
python src/launch.py -e classic
```

Mit dem Parameter `--ensemble` (Kurzform `-e`) wird festgelegt, welches Ensemble gestartet wird.
`classic` ist die Standardwahl für den regulären Betrieb. Für ein alternatives Beispiel-Ensemble wie
`spaceship_crew` lässt sich der Start wie folgt ausführen:

```bash
python src/launch.py -e examples/spaceship_crew
```

Der Name ist ein Pfad unterhalb von `ensembles/` und wird **immer mit Schrägstrich** geschrieben,
auch unter Windows — er landet unverändert in den Avatar-URLs der Web-UI.

Eine detaillierte Anleitung zur Erstellung eigener Ensembles findest du in
[Eigenes Ensemble hinzufügen](Ensemble_hinzufuegen.md).

Optional kann zusätzlich eine alternative Konfigurationsdatei per `--config` (Kurzform `-c`)
übergeben werden, zum Beispiel:

```bash
python src/launch.py -e classic --config pfad/zur/config.yaml
```

#### Ensembles auflisten

Welche Ensembles im Repo liegen — inklusive des Namens, den `-e` erwartet — zeigt:

```bash
python src/launch.py --list-ensembles
```

```
Yul Yen — Verfügbare Ensembles
------------------------------------------------
  classic
      Personas: LEAH (featured), DORIS, PETER, POPCORN
      Sprachen: de, en
  examples/spaceship_crew
      Personas: CAPTAIN_SELINA (featured), ZETA_FLUX, ELIAS_MOREL, LYRA_VEX
      Sprachen: de, en
```

Der Befehl liest nur YAML-Dateien und braucht weder Ollama noch den UI-Stack.

#### Setup-Doktor (Preflight-Check)

Vor dem ersten Start (oder bei Problemen) prüft der Setup-Doktor die gesamte Umgebung —
Ollama-Erreichbarkeit, gepulltes Modell, spaCy-Modell, Kiwix und VRAM — mit konkreten
Fix-Hinweisen statt kryptischer Tracebacks:

```bash
python src/launch.py --doctor
```

Exit-Code 1 signalisiert einen kritischen Ausfall (praktisch für Skripte).

Die Kopfzeile nennt die laufende Version. Sie allein bekommt man auch mit
`python src/launch.py --version`, und über HTTP als Feld `version` in `/health`
— nützlich, bevor man einen Fehler meldet. Was sich zwischen zwei Versionen
geändert hat, steht in [`CHANGELOG.md`](../../CHANGELOG.md) (englisch).

Mitgeprüft wird auch die `config.yaml` selbst: unbekannte Schlüssel werden auf **jeder** Ebene gemeldet, also auch `security.pii_protecton` statt `pii_protection` oder `storage.enable` statt `enabled` — ein Tippfehler, der sonst still dazu führt, dass die Einstellung gar nicht greift. Beim normalen Start ist das nur eine Warnung im Log (ein laufendes Setup soll nicht an einem Schema scheitern), im Doktor ein harter Befund.

- **Terminal-UI**
  - Bei `ui.type: "terminal"` im Terminal nutzen
  - Startmenü: neue Unterhaltung, Konversation laden (JSON), Self-Talk, Ask-All
  - Eingabe: Fragen einfach eintippen
  - Befehle: `exit` (beenden), `clear` (neue Unterhaltung starten), `/save <pfad>` (Konversation als JSON speichern), `/briefing` (Persona fasst die konfigurierten RSS-Feeds zusammen), `/quellen` bzw. `/sources` (die zuletzt injizierten Wikipedia-Ausschnitte im Wortlaut, ungekürzt)

- **Web-UI**
  - Bei `ui.type: "web"` wird automatisch eine Weboberfläche gestartet
  - Im Browser öffnen: `http://<host>:<port>` entsprechend der Einstellungen unter `ui.web` (Standard: `http://127.0.0.1:7860`)
  - Anmeldung (optional): `ui.web.auth.provider` auf `local` oder `header` setzen — sie gilt **unabhängig davon, ob ein Share-Link aktiv ist**. Ohne Anmeldung zeichnet die Web-UI keine Gespräche auf und blendet die Verlauf-Karte aus (`storage.shared_without_login: true` schaltet sie ausdrücklich wieder ein)
  - Optional: öffentlicher Gradio-Share-Link per `ui.web.share: true`. Das alte `ui.web.share_auth` ist veraltet und wirkt nur noch als Fallback, wenn kein `auth`-Abschnitt existiert; der Start mahnt es an
  - Persona auswählen und loschatten
  - Profi-Option: Im zugeklappten „Erweitert"-Bereich unten am Startbildschirm lässt sich das Modell für die laufende Sitzung wechseln (Liste = installierte Ollama-Modelle). Gilt nur bis zum Neustart — danach greift wieder `core.model_name` aus der `config.yaml`
  - Spracheingabe (opt-in): Nach `pip install faster-whisper` erscheint im Persona-Chat ein Mikrofon neben dem Eingabefeld. Aufnehmen → stoppen → das Transkript wird ans Eingabefeld angehängt und kann vor dem Senden editiert werden. Die erste Aufnahme lädt das Whisper-Modell (einmalig inkl. Download) und dauert daher etwas. Details und Modellwahl: [src/stt/ReadMe.md](../../src/stt/ReadMe.md)
  - Nachrichten (RSS): Ist `rss.enabled: true` gesetzt, holt die Anwendung die konfigurierten Feeds **im Hintergrund** (beim Start und dann alle `rss.refresh_minutes`) und hält die neuesten Meldungen im Speicher. Fragt man dann etwas wie „Was gibt's Neues?" oder „Was sagt die Tagesschau?", legt die Persona die passenden Meldungen von selbst als Kontext dazu — mit Datum und dem Stand des Zwischenspeichers. Ein Chat wartet dabei **nie** auf das Netz: was noch nicht geholt ist, fehlt eben. Der Button „Briefing 📰" nutzt denselben Zwischenspeicher und lässt sich mit `rss.show_button: false` ausblenden, ohne die Quelle abzuschalten. Alles zusammen abschalten: `rss.enabled: false`
  - Vorlesen (TTS): Der Button „Vorlesen 🔊" im Persona-Chat spielt die letzte Antwort mit der Piper-Stimme der Persona im Browser ab (im Browser statt über einen System-Player). Erscheint nur, wenn `pip install piper-tts` erfolgt ist und Stimmen im `voices/`-Ordner liegen; abschalten per `tts.features.web_read_aloud: false`. Setup: [src/tts/ReadMe.md](../../src/tts/ReadMe.md)

- **Nur API (ohne UI)**
  - `ui.type: null` setzen – die FastAPI läuft weiter und bedient `/ask`

- **API (FastAPI)**
  - Automatisch aktiv bei `api.enabled: true`
  - `GET /health` — schneller Liveness-Check (`{"status": "ok"}`)
  - `GET /healthz` — Deep-Check (Ollama, Modell, spaCy, Kiwix, VRAM); HTTP 503 bei kritischem Ausfall
  - Beispielaufruf per `curl`:
    ```bash
    curl -X POST http://127.0.0.1:8013/ask \
         -H "Content-Type: application/json" \
         -d '{"question":"Wer hat die Relativitätstheorie entwickelt?", "persona":"LEAH"}'
    ```

---

## Beispiel: Wikipedia schlägt den Trainings-Cutoff

Das Default-Modell hat einen Trainings-Cutoff von Ende 2023 — von der Kanzlerwahl 2025
kann es nichts wissen. Mit dem Offline-Wikipedia-Feature beantwortet PETER die Frage
trotzdem korrekt und nennt seine Quelle:

![PETER beantwortet eine Frage nach dem Trainings-Cutoff mit Wikipedia-Kontext](../screenshot_wiki_feature.png)

---

## Tests

Schneller lokaler Durchlauf (Dummy-Backend, ohne langsame Tests):
```bash
pytest -q -m "not slow and not ollama and not browser"    # entspricht: make test
```

Vor dem Push genügt **ein** Kommando: `make check` — es fährt Linter,
Schichtenprüfung, Typen und Tests nacheinander und stoppt beim ersten Fehler.

Weitere Varianten (siehe `Makefile`): `make test-all` (komplette Suite),
`make test-ci` (derselbe Umfang wie die CI, mit Coverage), `make coverage`,
`make lint` / `make format` (Ruff/Black), `make types` (mypy über das ganze
`src`, zweimal — der zweite Lauf nimmt Windows an), `make lint-imports`
(Schichtenverträge, siehe unten), `make audit` (bekannte
Schwachstellen der Abhängigkeiten gegen `audit_allowlist.yaml` halten — braucht Netz) und
`make evals` / `make evals-full` (Eval-Suite, siehe `evals/ReadMe.md`; nur die
volle Variante braucht ein Modell).

**Der Browser-Rauchtest steht bewusst daneben**, nicht dabei:
```bash
make test-browser
```
Er fährt die *laufende* WebUI mit Dummy-Backend im echten Chromium und prüft,
was in-process unsichtbar bleibt — ob Tokens ankommen, ob „Senden" während des
Streams zu „Stop" wird, ob der Theme-Umschalter die Seite neu lädt, ob eine
Datei beim Browser ankommt. Dafür braucht er Playwright **und** einen
Browser-Build (`pip install playwright && playwright install chromium`), und
genau deshalb ist er aus `make test` und aus der CI ausgenommen. Fehlt
Playwright, wird sauber übersprungen.

---

## Status

🚧 **Work in Progress** – stabil nutzbar, aber aktiv in Entwicklung (inkl. erster LoRA-Finetuning-Experimente).
Privates Projekt, **nicht für Produktivbetrieb gedacht**.
