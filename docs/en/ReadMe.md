# Yul Yen's AI Orchestra

> _Translation note (2025-10-30): This document is an English translation of [`docs/de/ReadMe.md`](../de/ReadMe.md) at commit `8d8c4b7d30a63adb857a251be6b1331529267e69`._

**Yul Yen's AI Orchestra** is a locally running AI environment that combines multiple **personas** (Leah, Doris, Peter, Popcorn).

All personas are based on a local LLM (currently via [Ollama](https://ollama.com/) or compatible backends) and come with their own characters and language styles.

The project supports:
- **Terminal UI** with colored console output & streaming
- **Web UI** built on [Gradio](https://gradio.app) (accessible within the local network)
- **API (FastAPI)** for integration into external applications
- **Wikipedia integration** (online or offline via Kiwix proxy)
- **Security filters** (prompt-injection protection & PII detection)
- **Logging & tests** for stable usage

See also: [Features.md](Features.md)

---

## Goals

- Provide a **private, locally running AI** for German-language interaction
- Multiple **characters with distinct styles**:
  - **Leah**: empathetic, friendly
  - **Doris**: sarcastic, humorous, cheeky
  - **Peter**: fact-oriented, analytical
  - **Popcorn**: playful, child-friendly
- **Extensible foundation** for future features (e.g., LoRA fine-tuning, tool use, RAG)
- **KISS principle**: simple, transparent architecture

---

## Architecture overview

- **Configuration**: All settings centrally stored in `config.yaml`
- **Core**:
  - Swappable LLM core (`OllamaLLMCore`, `DummyLLMCore` for tests) including `YulYenStreamingProvider`
  - Wikipedia support including a spaCy-based keyword extractor
- **Personas**: System prompts & quirks in `src/config/personas.py`
- **UI**:
  - `TerminalUI` for the CLI
  - `WebUI` (Gradio) with persona selection & avatars
- **API**: FastAPI server (`/ask` endpoint for one-shot questions)
- **Logging**:
  - Chat transcripts and system logs in `logs/`
  - Wiki proxy writes separate log files

---

## Prerequisites

- **Python 3.10+**
- **Ollama** (or another compatible backend) with an installed model, for example:
  ```bash
  ollama pull leo-hessianai-13b-chat:Q5
  ```
- For tests without Ollama you can set `core.backend: "dummy"` – the echo backend requires no additional downloads and is suitable for CI or quick prototyping.
- Optional for offline wiki usage:
  - [Kiwix](https://kiwix.org/) + German ZIM archive

---

## Installation

```bash
git clone https://github.com/YulYen/YulYens_AI.git
cd YulYens_AI

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

### Language model for spaCy

The Wikipedia integration requires a spaCy model that matches your configured language. The keyword finder now looks up the correct package via the combination of `language` and `wiki.spacy_model_variant`, using the mapping in `wiki.spacy_modell_map` inside `config.yaml`. This keeps the model choice entirely in configuration, without hard-coded defaults.

Example:

```yaml
language: "en"
wiki:
  spacy_model_variant: "medium"
  spacy_modell_map:
    en:
      medium: "en_core_web_md"
      large:  "en_core_web_lg"
```

Additionally, you have to install the corresponding model manually:

```bash
# Medium model (balance between size and accuracy)
python -m spacy download en_core_web_md

# Large model (more accurate, but slower and uses more memory)
python -m spacy download en_core_web_lg
```

---

## Usage

### Configuration (`config.yaml`)

All central settings are controlled through `config.yaml`. Important toggles:

- `language`: controls UI texts and persona prompts (`"de"` or `"en"`).
- `ui.type`: selects the interface (`"terminal"`, `"web"`, or `null` for API only).

Example:

```yaml
language: "de"
core:
  # Choose backend: "ollama" (default) or "dummy" (echo backend for tests)
  backend: "ollama"
  # Default model for Ollama
  model_name: "leo-hessianai-13b-chat.Q5"
  # URL of the locally running Ollama server (protocol + host + port).
  # This value must be set explicitly – there is no silent default.
  ollama_url: "http://127.0.0.1:11434"
  # Warm-up: whether to send a dummy call to the model at startup.
  warm_up: false

ui:
  type: "terminal"   # Alternatives: "web" or null (API only)
  web:
    host: "0.0.0.0"
    port: 7860
    share: false       # Optional Gradio share (requires username/password)

wiki:
  mode: "offline"    # "offline", "online" or false (disabled)
  spacy_model_variant: "large"  # Alternatives: "medium" or direct model name
  proxy_port: 8042
  snippet_limit: 1600
```

#### LLM backends

The key `core.backend` determines which LLM core is used:

- `ollama` *(default)* integrates a running Ollama server. The Python package [`ollama`](https://pypi.org/project/ollama/) needs to be installed (e.g., via `pip install ollama`), and `core.ollama_url` must point to the Ollama instance.
- `dummy` uses the `DummyLLMCore`, which returns each input as `ECHO: ...`. This is ideal for unit tests, continuous integration, or demos without an available LLM. In this mode a placeholder for `core.ollama_url` is sufficient; neither a running Ollama server nor the Python package is required.

#### Security guard

The `security` section selects the guard for input and output checks:

- `security.guard: "BasicGuard"` (default) loads the built-in base protection. The toggles `prompt_injection_protection`, `pii_protection`, and `output_blocklist` control which checks are active.
- `security.guard: "DisabledGuard"` disables the checks via a stub. The aliases `"disabled"`, `"none"`, and `"off"` are accepted as well.
- `security.enabled: false` disables the guard logic entirely, regardless of the selected name.

#### Wikipedia (proxy & autostart)

- In offline mode (`wiki.mode: "offline"`), `kiwix-serve` can be started automatically when `wiki.offline.autostart: true` is set.

### Launch

```bash
python src/launch.py
```

- **Terminal UI**
  - Use in the terminal when `ui.type: "terminal"`
  - Input: simply type your questions
  - Commands: `exit` (quit), `clear` (start a new conversation)

- **Web UI**
  - With `ui.type: "web"`, a web interface starts automatically
  - Open in the browser: `http://<host>:<port>` according to the `ui.web` settings (default: `http://127.0.0.1:7860`)
  - Optional: enable Gradio share via `ui.web.share: true`; credentials come from `ui.web.share_auth`
  - Pick a persona and start chatting

- **API only (no UI)**
  - Set `ui.type: null` – FastAPI keeps running and serves `/ask`

- **API (FastAPI)**
  - Automatically active when `api.enabled: true`
  - Example request using `curl`:
    ```bash
    curl -X POST http://127.0.0.1:8013/ask \
         -H "Content-Type: application/json" \
         -d '{"question":"Who developed the theory of relativity?", "persona":"LEAH"}'
    ```

---

## Example

**Question (Leah):**
> Who is Angela Merkel?

**Answer (streamed):**
> Angela Merkel is a German politician (CDU) who served as the Chancellor of the Federal Republic of Germany from 2005 to 2021. …

---

## Tests

Run with [pytest](https://docs.pytest.org/):
```bash
pytest tests/
```

---

## Status

🚧 **Work in progress** – stable to use, but under active development (including initial LoRA fine-tuning experiments). Private project, **not intended for production use**.
