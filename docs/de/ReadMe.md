# Yul Yen’s AI Orchestra

**Yul Yen’s AI Orchestra** ist eine lokal laufende KI-Umgebung, die mehrere **Personas** (Leah, Doris, Peter, Popcorn) vereint.  
Sie alle basieren auf einem lokalen LLM (aktuell über [Ollama](https://ollama.com/) oder kompatible Backends) und bringen eigene Charaktere und Sprachstile mit.  

Das Projekt unterstützt:  
- **Terminal-UI** mit farbiger Konsolenausgabe & Streaming  
- **Web-UI** auf Basis von [Gradio](https://gradio.app) (im lokalen Netzwerk erreichbar)  
- **API (FastAPI)** zur Integration in externe Anwendungen  
- **Wikipedia-Integration** (online oder offline via Kiwix-Proxy)  
- **Sicherheits-Filter** (Prompt-Injection-Schutz & PII-Erkennung)  
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
- **Personas**: Systemprompts & Eigenheiten in `src/config/personas.py`  
- **UI**:
  - `TerminalUI` für CLI
  - `WebUI` (Gradio) mit Persona-Auswahl & Avataren
  - Optionaler Ask-All/Broadcast-Modus (per `ui.experimental.broadcast_mode`), nutzt `/askall <Frage>` im Terminal und die Ask-All-Kachel in der Web-UI
- **API**: FastAPI-Server (`/ask`-Endpoint für One-Shot-Fragen)
- **Logging**:
  - Chatverläufe und Systemlogs in `logs/`
  - Wiki-Proxy schreibt separate Logdateien  

---

## Voraussetzungen

- **Python 3.10+**
- **Ollama** (oder anderes kompatibles Backend) mit installiertem Modell, z. B.:
  ```bash
  ollama pull leo-hessianai-13b-chat:Q5
  ```
- Für Tests ohne Ollama kann `core.backend: "dummy"` gesetzt werden – das Echo-Backend kommt ohne
  zusätzliche Downloads aus und eignet sich für CI oder schnelles Prototyping.
- Optional für Offline-Wiki:
  - [Kiwix](https://kiwix.org/) + deutsches ZIM-Archiv

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

Beispiel:

```yaml
language: "de"
core:
  # Backend auswählen: "ollama" (Standard) oder "dummy" (Echo-Backend für Tests)
  backend: "ollama"
  # Standardmodell für Ollama
  model_name: "leo-hessianai-13b-chat.Q5"
  # URL des lokal laufenden Ollama-Servers (Protokoll + Host + Port).
  # Dieser Wert muss explizit gesetzt werden – es gibt keinen stillen Default.
  ollama_url: "http://127.0.0.1:11434"
  # Warm-up: ob beim Start ein Dummy-Aufruf zum Modell geschickt wird.
  warm_up: false

ui:
  type: "terminal"   # Alternativen: "web" oder null (nur API)
  web:
    host: "0.0.0.0"
    port: 7860
    share: false       # Optional Gradio-Share (Benutzername/Passwort nötig)

wiki:
  mode: "offline"    # "offline", "online" oder false (deaktiviert)
  spacy_model_variant: "large"  # Alternativen: "medium" oder direkter Modellname
  proxy_port: 8042
  snippet_limit: 1600           # Maximale Länge eines einzelnen Snippets in Zeichen
  max_wiki_snippets: 2          # Wieviele verschiedene Snippets maximal in den Prompt injiziert werden dürfen
```

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
  `prompt_injection_protection`, `pii_protection` und `output_blocklist` bestimmen, welche
  Prüfungen aktiv sind.
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
python src/launch.py -e examples\spaceship_crew
```

Eine detaillierte Anleitung zur Erstellung eigener Ensembles findest du in
[Eigenes Ensemble hinzufügen](Ensemble_hinzufuegen.md).

Optional kann zusätzlich eine alternative Konfigurationsdatei per `--config` (Kurzform `-c`)
übergeben werden, zum Beispiel:

```bash
python src/launch.py -e classic --config pfad/zur/config.yaml
```

- **Terminal-UI**  
  - Bei `ui.type: "terminal"` im Terminal nutzen  
  - Eingabe: Fragen einfach eintippen  
  - Befehle: `exit` (beenden), `clear` (neue Unterhaltung starten)  

- **Web-UI**
  - Bei `ui.type: "web"` wird automatisch eine Weboberfläche gestartet
  - Im Browser öffnen: `http://<host>:<port>` entsprechend der Einstellungen unter `ui.web` (Standard: `http://127.0.0.1:7860`)
  - Optional: Gradio-Share per `ui.web.share: true` aktivieren; Zugangsdaten kommen aus `ui.web.share_auth`
  - Persona auswählen und loschatten

- **Nur API (ohne UI)**
  - `ui.type: null` setzen – die FastAPI läuft weiter und bedient `/ask`

- **API (FastAPI)**
  - Automatisch aktiv bei `api.enabled: true`
  - Beispielaufruf per `curl`:
    ```bash
    curl -X POST http://127.0.0.1:8013/ask \
         -H "Content-Type: application/json" \
         -d '{"question":"Wer hat die Relativitätstheorie entwickelt?", "persona":"LEAH"}'
    ```  

---

## Beispiel

**Frage (Leah):**  
> Wer ist Angela Merkel?

**Antwort (gestreamt):**  
> Angela Merkel ist eine deutsche Politikerin (CDU) und war von 2005 bis 2021 Bundeskanzlerin der Bundesrepublik Deutschland. …

---

## Tests

Mit [pytest](https://docs.pytest.org/) ausführen:  
```bash
pytest tests/
```

---

## Status

🚧 **Work in Progress** – stabil nutzbar, aber aktiv in Entwicklung (inkl. erster LoRA-Finetuning-Experimente).  
Privates Projekt, **nicht für Produktivbetrieb gedacht**.