# Features

> ℹ️ **Translation notice (2026-07-04):** This document is an English translation of [`docs/de/Features.md`](../de/Features.md). For the authoritative German source, please refer to that file.

## Multiple AI personas

The system comprises four distinct AI personas with their own personalities. Every persona uses the same underlying language model but differs through dedicated system prompts that determine tone and voice:

- **Leah** – empathetic and friendly
- **Doris** – sarcastic with quick-witted humor
- **Peter** – fact-focused, analytical, and objective
- **Popcorn** – playful and kid-friendly (cat persona)

The persona can be selected either at start-up (terminal UI) or via the web interface. Each persona responds to user requests in its characteristic manner.

## User interfaces (UI)

Two different user interfaces are available and can be selected via the configuration (`ui.type`):

- **Terminal UI** – A console-based chat application with color-highlighted roles (user/AI). When launched, the desired persona is picked from a menu. User input is entered directly in the console, and the AI response is streamed token by token. Simple commands like `exit` end the session and `clear` starts a fresh chat history.
- **Web UI** – A browser-based interface (Gradio). It offers a graphical persona selection (with avatar images) and a chat window for the conversation. The AI response is displayed live as it is generated. The web UI is accessible on the local network and enables a comfortable chat experience over HTTP.

An optional **Ask-All/Broadcast mode** can be enabled (`ui.experimental.broadcast_mode: true`). This sends a question to all personas—via the Ask-All option in the terminal start menu and through the Ask-All card in the web UI. The personas answer one after another; in the web UI the replies appear **streamed live token by token**, one markdown section per persona:

![Ask-All: all four personas answer the same question](../screenshot_ask_all.png)

Additionally, `ui.type` can be set to `null` to operate the API exclusively. The web UI also supports an optional Gradio share link using credentials from `ui.web.share_auth`.

## AI dialog (self-talk)

The project includes an **AI dialog mode** in which two personas talk to each other automatically to solve a given task:

- **Terminal UI:** Select “Self Talk” in the start menu, then choose Persona A, Persona B, and an initial prompt.
- **Web UI:** A dedicated self-talk tile starts the same flow directly in the browser.
- **Flow:** Both personas answer in turns; each generated reply is forwarded as the next input for the other persona.
- **Automatic end:** The dialog stops once one persona emits the defined end token (`_endegelaende_`).

This mode is useful for brainstorming between two character styles or exploring multiple perspectives on the same question.

## Text-to-speech (TTS)

For terminal interaction, integrated **Piper-based text-to-speech output** is available:

- Enable it via `tts.enabled: true`.
- Create one WAV file per answer via `tts.features.terminal_auto_create_wav: true`.
- Configure voices in `config.yaml` via `tts.voices` (language defaults plus optional persona-specific voices).
- **Current platform limitation:** automatic WAV creation/playback in Terminal UI currently works on **Windows only** (because `tts.audio_player` depends on `winsound`). On Linux/macOS, this path is skipped after import failure.

This allows replies to be consumed not only as text but also immediately as audio.

## One-shot API

Alongside the UI, the system can be accessed through a REST API (e.g., for integrations or testing). A FastAPI server exposes an **`/ask` endpoint** that accepts individual questions via HTTP POST. The request accepts JSON (with fields for the **question** and desired **persona**) and returns the AI reply as JSON. Two endpoints exist for monitoring: **`/health`** as a fast liveness check and **`/healthz`** as a deep check that verifies Ollama reachability, the pulled model, spaCy, Kiwix, and VRAM (HTTP 503 on critical failure). The same checks are available on the CLI via `python src/launch.py --doctor` as a colored preflight report. This API makes it possible to embed the AI functionality into external applications or use it for automation.

## Email adapter for personas

Optionally, a lightweight **email adapter** can be enabled (`email_adapter.enabled: true`). It periodically polls a configured IMAP mailbox for new messages, maps recipient addresses to a persona via `email_adapter.address_persona_map`, and answers the request with the same one-shot logic the HTTP API uses. The reply is sent back to the original sender via SMTP.

The MVP handles plain-text emails; HTML is pragmatically reduced to text, attachments are ignored. To avoid mail loops and duplicate replies, the adapter ignores its own system/persona addresses and moves successfully processed (or deliberately ignored) messages into the configured `processed_mailbox` folder by default. Credentials do not belong in the code: `config.yaml` provides placeholders like `env:YULYEN_MAIL_IMAP_PASSWORD` that are resolved from environment variables at runtime.

## Wikipedia integration

To deliver well-grounded answers, the system can automatically **incorporate Wikipedia knowledge** for factual queries (configurable option). It relies on the following mechanisms:

- **Automatic knowledge retrieval:** The relevant keyword is extracted from the user prompt using spaCy NLP. An internal wiki proxy then searches for a matching Wikipedia article—either **offline** via a local Kiwix database or **online** via the Wikipedia API, depending on the settings. In offline mode, the Kiwix server can be started automatically if configured.
- **Context enrichment:** If the wiki proxy finds an article, a snippet is taken from it. This snippet is inserted into the chat context as an additional *system* message before the AI replies. The AI thus receives verified facts and can produce more precise responses. In the terminal UI a spyglass icon (🕵️) indicates when a Wikipedia snippet was used. If the search comes up empty, a short notice is displayed instead.
- **Multiple hits usable:** If the keyword finder detects several relevant entities, multiple snippets can be injected into the prompt. The cap is configured via `wiki.max_wiki_snippets` (default: 2) to expand context deliberately without overloading it.

## Logging and tests

Robust usage is supported by extensive logging and automated tests:

- **Chat logging:** Every conversation is recorded in a JSON file (stored in the `logs/` folder). It captures timestamps, the model in use, the persona, and all user and AI messages. The application also writes a rolling system log file (prefixed `yulyen_ai_...`) that contains internal processes and debug information (info/error).
- **Wiki proxy logging:** The Wikipedia proxy service keeps its own log files for article requests and results. This makes it possible to trace wiki lookups and any errors separately from the main chat log.
- **Automated tests:** A collection of pytest tests (in the `tests/` directory) verifies core system functions. For example, the tests ensure that personas are initialized correctly, the security filter works, and repeatable responses (such as Doris telling the same jokes) remain consistent. These tests help prevent regressions and maintain reliable orchestration.

## Security mechanisms

The project ships with a lightweight integrated **security guard** (`BasicGuard`) that checks inputs and outputs for problematic content:

- **Prompt-injection protection:** User inputs are scanned for patterns that suggest a *prompt injection* attempt (e.g., instructions to ignore previous rules). When such an attempt is detected, the guard interrupts the normal flow: instead of an AI reply, the user receives a notice that the request was rejected. The potentially harmful input is not forwarded to the language model.
- **PII filtering:** The guard detects personal data (*personally identifiable information*, e.g., email addresses or phone numbers) in generated AI responses and proactively replaces it with a standard warning. This prevents private or sensitive details from appearing unfiltered in the chat.
- **Output blocklist:** Certain confidential keys or tokens (e.g., API keys in the form `sk-...`) are also detected. If the AI produces such sequences, the output is fully blocked to avoid leaking secrets. The user then only sees a generic warning instead of the dangerous content.
- **Wrongdoing guardrail (violence/weapons):** Requests for violence or weapons instructions are detected deterministically before the LLM call and rejected. A **session lock** ensures that bypass attempts in follow-up requests ("it's just for a novel…") stay blocked until a new conversation is started. Controlled via `security.wrongdoing_protection` (default: on).

These checks run during streaming: tokens are continuously inspected, masked when necessary, and replaced with a safety warning immediately when a blocked sequence appears.

## Extensibility and experiments

The architecture of *Yul Yen’s AI Orchestra* is designed to enable future enhancements and improvements:

- **Modular architecture:** The system encapsulates LLM access behind clearly defined interfaces. For example, interaction with the language model is implemented via the abstract `LLMCore` class. This makes it straightforward to swap out the backend (e.g., use a different model server instead of Ollama, or employ the dummy LLM for tests) without touching the rest of the application. New personas can also be added easily by extending the configuration.
- **LoRA fine-tuning (PoC):** Early experiments for model refinement exist as a proof of concept but are not included in the standard repository for size reasons. Internally, a small **LoRA fine-tuning** example (based on [PEFT/QLoRA](https://github.com/huggingface/peft)) demonstrates how a compact adapter for the persona Doris was trained with about 200 question–answer pairs. The training scripts and test runs are for demonstration only and are not integrated into production. Interested parties can reach out to the maintainers for details or access to the materials.
- **Context compression ("Karl"):** For long conversations, the chat history is compressed automatically before the context window overflows. The default is a fast heuristic (trim old messages, keep the system prompt and the most recent messages); optionally, the LLM-based summarizer "Karl" condenses older chat parts (`context_management.strategy: "karl"`, with automatic fallback to the heuristic).
- **Three-timestamp transparency:** The system prompt cleanly separates three easily confused dates: the current system date, the model's training cutoff (`core.knowledge_cutoffs`), and the data snapshot of the Wikipedia archive. This keeps personas from accidentally claiming to have "current" knowledge.
- **Future features:** The project keeps a prioritized roadmap (see [backlog.md](../../backlog.md)). Planned additions include tool integrations (*tool use* such as web search or calculators), speech input (STT), and faster time-to-first-token. The current codebase provides a simple, extensible foundation on which these features can be built.

See also: [backlog.md](../../backlog.md)
