# Leah – Private Local AI Assistant

**Note (English):**  
This is a private project and repository. The short introduction is written in English in case someone outside Germany stumbles upon it – but from here on the documentation continues in German, since the AI personas (Leah, Doris, Peter) are primarily designed to operate in German.  

---

## Übersicht

**Leah** ist eine lokal laufende KI, die über [Ollama](https://ollama.com/) oder kompatible Backends genutzt wird.  
Sie bietet:

- **Mehrere Personas** (Leah, Doris, Peter) mit unterschiedlichen Stilen.  
- **Terminal-UI** mit Farbausgabe und Streaming.  
- **Web-UI** (Gradio-basiert), auch im lokalen Netzwerk nutzbar.  
- **Wikipedia-Integration** über einen lokalen Proxy (wahlweise offline mit Kiwix oder online).  
- **Sauberes Logging** (Gesprächsprotokolle, Debug-Logs, Wiki-Proxy-Logs).  
- **Konfiguration per `config.yaml`**, ohne Code ändern zu müssen.  
- **Unit Tests** (Pytest) für wichtige Features wie Konfig-Handling, Wiki-Proxy und Keyword-Erkennung.  

Das Projekt ist **privat** gedacht – als persönliche Assistenz-KI und Experimentierumgebung.  
Es ist **nicht** für den öffentlichen Betrieb oder kommerzielle Nutzung vorgesehen.  

---

## Installation

### 1. Voraussetzungen

- Python **3.10+**
- [Ollama](https://ollama.com/) (lokal installiert)
- Optional: [Kiwix](https://kiwix.org/) + ein deutsches Wikipedia-ZIM (für Offline-Modus)

### 2. Repository klonen

```bash
git clone <PRIVATE_REPO_URL>
cd leah
```

### 3. Virtuelle Umgebung & Dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

---

## Nutzung

### Start über Hauptskript

```bash
python jk_ki_main.py
```

- Lädt `config.yaml`  
- Startet Logging  
- Optional den Wiki-Proxy (falls in `config.yaml` aktiviert)  
- Startet API + UI  

### UI auswählen

In `config.yaml`:

```yaml
ui:
  type: "terminal"   # oder "web"
```

### Personas

Beim Start kannst du zwischen **Leah**, **Doris** und **Peter** wählen:  
- Leah: charmant, empathisch, locker  
- Doris: trocken, sarkastisch, bissig  
- Peter: nerdig, faktenorientiert, freundlich  

---

## Konfiguration

Beispiel `config.yaml` (gekürzt):

```yaml
core:
  model_name: "leo-hessianai-13b-chat.Q5"

ui:
  type: "web"
  greeting: "Chatte mit {persona_name} auf Basis von {model_name}!"

wiki:
  mode: "offline"   # "offline", "online" oder "false"
  proxy_port: 8042
  snippet_limit: 1600
  timeout_connect: 2.0
  timeout_read: 5.0
  offline:
    kiwix_port: 8080
    zim_prefix: "wikipedia_de_all_nopic_2025-06"

logging:
  dir: "logs"
  level: "INFO"
  to_console: true

api:
  host: "127.0.0.1"
  port: 8013
```

---

## Tests

```bash
pytest
```

Getestet werden u.a.:  
- Platzhalter in `config.yaml`  
- Verhalten bei fehlenden Keys  
- Wiki-Proxy (online/offline)  
- KeywordFinder mit spaCy  

---

## Projektstruktur

```
jk_ki_main.py           # Einstiegspunkt
system_prompts.py       # Personas (Leah, Doris, Peter)
streaming_core_ollama.py# Streaming & LLM-Anbindung
terminal_ui.py          # Terminal-Interface
web_ui.py               # Web-Interface (Gradio)
wikipedia_proxy.py      # Offline/Online Wikipedia-Proxy
config.yaml             # Konfiguration
logs/                   # Gesprächs- und Fehler-Logs
tests/                  # Pytest-Tests
```

---

## Hinweise

- Dieses Projekt ist **privat**.  
- Es wird aktiv entwickelt, aber **keine Stabilität oder Sicherheit garantiert**.  
- Ziel: **Experimentierumgebung für lokale LLMs** – mit Fokus auf deutschsprachige Interaktion.  
- Erweiterbar (z. B. weitere Personas, neue UIs, andere Backends).  

---

## Lizenz

Keine öffentliche Lizenz.  
Alle Rechte vorbehalten.  
Nur für private Nutzung.  
