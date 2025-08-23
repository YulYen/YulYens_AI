# Yul Yen’s AI Orchestra

**Note (English):**  
This is a private project and repository. The short introduction is written in English in case someone outside Germany stumbles upon it – but from here on the documentation continues in German, since the AI personas (Leah, Doris, Peter) are primarily designed to operate in German.  

*Yul Yen’s AI Orchestra is a local AI project with multiple personas, designed for private use and experimentation.*

**Yul Yen’s AI Orchestra** ist eine lokal laufende KI-Umgebung, die mehrere **Personas** (Leah, Doris, Peter) vereint.  
Sie alle basieren auf einem lokalen LLM (über [Ollama](https://ollama.com/) oder kompatible Backends) und bringen eigene Charaktere und Sprachstile mit.  

```mermaid
flowchart TD
    A[🪄 Dirigent (Julian / Yul Yen)] --> B{🎤 Stimmen}
    B --> L[Leah – empathisch]
    B --> D[Doris – sarkastisch]
    B --> P[Peter – nerdig]

    A --> C{🖥️ Core Plattform}
    C --> O[Ollama Runtime]
    C --> W[Gradio WebUI 🎹]
    C --> T[Terminal UI 🥁]

    O --> M[(LLM-Modelle: Leo13B, GPT-OSS20B...)]
    
    W --> X[Publikum 👥]
    T --> X

    A --> H{📖 Wissen & Struktur}
    H --> K[Wiki-Proxy / Kiwix – Spickzettel]
    H --> CFG[Config (yaml/json) – Notenheft]
    H --> LOG[Logging – Partituren]

    A --> Z{🔮 Zukunft}
    Z --> R[RAG / Kontextkompression – Karl]
    Z --> S[Tool-Use / TTS-STT]

    style A fill:#ffe6cc,stroke:#333,stroke-width:2px
    style B fill:#f0f0f0,stroke:#999
    style C fill:#f0f0f0,stroke:#999
    style H fill:#f0f0f0,stroke:#999
    style Z fill:#f0f0f0,stroke:#999
```

Das Projekt unterstützt:
- **Terminal-UI** mit farbiger Konsolenausgabe & Streaming  
- **Web-UI** auf Basis von [Gradio](https://gradio.app) (im lokalen Netzwerk erreichbar)  
- **API (FastAPI)** zur Integration in externe Anwendungen  
- **Wikipedia-Integration** (online oder offline via Kiwix-Proxy)  
- **Logging & Tests** für stabile Nutzung  

---

## Ziele

- Bereitstellung einer **privaten, lokal laufenden KI** für deutschsprachige Interaktion  
- Mehrere **Charaktere mit unterschiedlichem Stil**:  
  - **Leah**: empathisch, freundlich  
  - **Doris**: sarkastisch, humorvoll  
  - **Peter**: faktenorientiert, analytisch  
- **Erweiterbares Fundament** für zukünftige Features (z. B. LoRA-Finetuning, Tool-Use, RAG)  
- **KISS-Prinzip**: einfache, nachvollziehbare Architektur  

---

## Architekturüberblick

- **Konfiguration**: Alle Einstellungen zentral in `config.yaml`  
- **Core**:  
  - `OllamaStreamer` für LLM-Aufrufe & Streaming  
  - Wikipedia-Support inkl. spaCy-basiertem Keyword-Extractor  
- **Personas**: Systemprompts & Eigenheiten in `src/config/personas.py`  
- **UI**:  
  - `TerminalUI` für CLI  
  - `WebUI` (Gradio) mit Persona-Auswahl & Avataren  
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
- Optional für Offline-Wiki:  
  - [Kiwix](https://kiwix.org/) + deutsches ZIM-Archiv  

---


## Installation

```bash
git clone https://github.com/YulYen/YulYens_AI.git
cd YulYens_AI

# Virtuelle Umgebung
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt
```

### Sprachmodell für spaCy

Für die Wikipedia-Integration wird ein deutsches Sprachmodell benötigt.  
Die Auswahl soll zukünftig über die Konfiguration (`config.yaml`) erfolgen.  
Zusätzlich muss das jeweilige Modell manuell installiert werden:

```bash
# Mittleres Modell (Kompromiss)
python -m spacy download de_core_news_md

# Großes Modell (genauer, aber etwas langsamer und größer)
python -m spacy download de_core_news_lg
```


---

## Nutzung

### Konfiguration (`config.yaml`)

```yaml
core:
  model_name: "leo-hessianai-13b-chat.Q5"

ui:
  type: "terminal"   # Alternativen: "web", null (nur API)
  web:
    host: "0.0.0.0"
    port: 7860

wiki:
  mode: "offline"    # "offline", "online" oder false
  proxy_port: 8042
  snippet_limit: 1600
```

### Start

```bash
python src/launch.py
```

- **Terminal-UI**  
  - Eingabe: Fragen tippen  
  - Befehle: `exit` (beenden), `clear` (neue Unterhaltung)  

- **Web-UI**  
  - Startet automatisch bei `ui.type: "web"`  
  - Im Browser öffnen: `http://127.0.0.1:7860`  
  - Persona auswählen, chatten  

- **API (FastAPI)**  
  ```bash
  curl -X POST http://127.0.0.1:8013/ask \
       -H "Content-Type: application/json" \
       -d '{"question":"Wer hat die Relativitätstheorie entwickelt?"}'
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

🚧 **Work in Progress** – stabil nutzbar, aber aktiv in Entwicklung.  
Privates Projekt, **nicht für Produktivbetrieb gedacht**.
