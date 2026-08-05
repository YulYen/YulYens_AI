# Features

> ℹ️ **Translation notice (2026-07-04):** This document is an English translation of [`docs/de/Features.md`](../de/Features.md). For the authoritative German source, please refer to that file.

## Multiple AI personas

The system comprises four distinct AI personas with their own personalities. Every persona uses the same underlying language model but differs through dedicated system prompts that determine tone and voice:

- **Leah** – empathetic and friendly
- **Doris** – sarcastic with quick-witted humor
- **Peter** – fact-focused, analytical, and objective
- **Popcorn** – playful and kid-friendly (cat persona)

The persona can be selected either at start-up (terminal UI) or via the web interface. Each persona responds to user requests in its characteristic manner.

These four belong to the `classic` ensemble — the default cast. Which personas answer depends on the selected ensemble (see the next section).

## Persona ensembles

An ensemble bundles personas together with their system prompts, LLM options (temperature, `repeat_penalty`, `num_ctx`) and avatars. Which one is loaded at start-up is decided by `--ensemble` / `-e`. Two ensembles ship with the repo:

- **`classic`** — LEAH, DORIS, PETER, POPCORN (default, `python src/launch.py -e classic`)
- **`examples/spaceship_crew`** — the crew of the starship *Aurora-One*: CAPTAIN_SELINA (composed commander), ZETA_FLUX (sarcastic chief engineer), ELIAS_MOREL (poetic navigator) and LYRA_VEX (alien diplomat). Start with `python src/launch.py -e examples/spaceship_crew`

![Spaceship crew: persona selection showing the crew of the Aurora-One](../screenshot_spaceship_crew.png)

`python src/launch.py --list-ensembles` lists the available ensembles — with personas, bundled locales and the exact name `-e` expects. The ensemble name is a path below `ensembles/` and is always written with forward slashes. Building your own takes no code, just YAML and images: see [Adding a custom ensemble](Adding_an_ensemble.md).

## User interfaces (UI)

Two different user interfaces are available and can be selected via the configuration (`ui.type`):

- **Terminal UI** – A console-based chat application with color-highlighted roles (user/AI). When launched, the desired persona is picked from a menu. User input is entered directly in the console, and the AI response is streamed token by token. Simple commands like `exit` end the session and `clear` starts a fresh chat history.
- **Web UI** – A browser-based interface (Gradio). It offers a graphical persona selection (with avatar images) and a chat window for the conversation. The AI response is displayed live as it is generated. By default it listens on `127.0.0.1` only, so it is reachable from your own machine alone; network access requires deliberately changing `ui.web.host` (and then please with a login, see below).

An optional **Ask-All/Broadcast mode** can be enabled (`ui.experimental.broadcast_mode: true`). This sends a question to all personas—via the Ask-All option in the terminal start menu and through the Ask-All card in the web UI. In the terminal the personas answer one after another; in the web UI they run **concurrently** and appear **streamed live token by token**, one markdown section per persona. A real speed-up does require Ollama to serve requests in parallel (`OLLAMA_NUM_PARALLEL` ≥ number of personas) — otherwise it queues them up again. Fall back with `ui.experimental.broadcast_parallel: false`:

![Ask-All: all four personas answer the same question](../screenshot_ask_all.png)

Additionally, `ui.type` can be set to `null` to operate the API exclusively. The web UI also supports an optional Gradio share link (`ui.web.share: true`). Its credentials come from the `ui.web.auth` section — which applies **whether or not a share link is active** (see "Sign-in"). The former `ui.web.share_auth` is deprecated and only acts as a fallback when no `auth` section exists.

### Stream control: stop and retry

While a reply is being generated, a **“Stop ⏹”** button takes the place of the send
button in the web UI. Clicking it ends generation immediately and **keeps the partial
answer** in the history, marked with `…[stopped]` — you usually stop precisely
because the opening already tells you where this is going. Stop is token-accurate in
the single chat and for the briefing; in the AI dialog it takes effect between
speaker turns, because each reply there is fetched in one go.

**“Retry 🔄”** discards the last answer and has the same question answered again.
The context stays untouched — the variation comes purely from the persona's
temperature, so POPCORN (0.8) varies far more than PETER (0.1). Wiki and briefing
hints above the answer stay in place.

## AI dialog (self-talk)

The project includes an **AI dialog mode** in which two personas talk to each other automatically to solve a given task:

- **Terminal UI:** Select “Self Talk” in the start menu, then choose Persona A, Persona B, and an initial prompt.
- **Web UI:** A dedicated self-talk tile starts the same flow directly in the browser.
- **Flow:** Both personas answer in turns; each generated reply is forwarded as the next input for the other persona.
- **Automatic end:** The dialog stops once one persona emits the defined end token (`_endegelaende_`). To be forgiving with small models, a reply ending in `_ende_` also counts.

This mode is useful for brainstorming between two character styles or exploring multiple perspectives on the same question.

## Text-to-speech (TTS)

Integrated **Piper-based text-to-speech output** is available in both interfaces:

- Enable it via `tts.enabled: true`.
- **Terminal:** create and play one WAV file per answer via `tts.features.terminal_auto_create_wav: true`.
- **Web UI:** the "Read aloud 🔊" button in the persona chat plays the latest reply with the persona's voice **in the browser** rather than through a system player. It only appears once `pip install piper-tts` is done and voices exist in the `voices/` folder; disable it via `tts.features.web_read_aloud: false`.
- Configure voices in `config.yaml` via `tts.voices` (language defaults plus optional persona-specific voices).
- **Platforms:** automatic WAV creation and playback in the terminal UI works on all three platforms. Windows uses `winsound` from the standard library; Linux and macOS dispatch to the usual command-line players (`paplay`, `aplay` or `ffplay` on Linux, `afplay` on macOS) — no extra dependency. If no player is found, playback is skipped silently and the WAV still lands in `out/`.

This allows replies to be consumed not only as text but also immediately as audio.

## Speech input (STT)

The other direction works too: in the web UI you can **speak** instead of typing. With `stt.enabled: true` and `faster-whisper` installed (`pip install faster-whisper`), a microphone appears next to the input field. Record → stop → the transcript is appended to the input field and can still be edited before sending — recognition does not replace sending, it only fills the field. The first recording loads the Whisper model (once, including a download) and therefore takes noticeably longer than the ones after it. Size and language live under `stt.model` and `stt.language`; details in [src/stt/ReadMe.md](../../src/stt/ReadMe.md).

## One-shot API

Alongside the UI, the system can be accessed through a REST API (e.g., for integrations or testing). A FastAPI server exposes an **`/ask` endpoint** that accepts individual questions via HTTP POST. The request accepts JSON (with fields for the **question** and desired **persona**) and returns the AI reply as JSON. Two endpoints exist for monitoring: **`/health`** as a fast liveness check and **`/healthz`** as a deep check that verifies Ollama reachability, the pulled model, spaCy, Kiwix, and VRAM (HTTP 503 on critical failure). The same checks are available on the CLI via `python src/launch.py --doctor` as a colored preflight report. This API makes it possible to embed the AI functionality into external applications or use it for automation.

## OpenAI-compatible API

The personas also speak the **OpenAI protocol**. That means any client built for
OpenAI works — Open WebUI, phone apps, editor plugins — just with LEAH, DORIS,
PETER and POPCORN instead of a cloud model. Unlike raw Ollama, everything still
goes through the guard, the wiki injection and the conversation store, because it is
the same streamer the UI uses.

The mapping is the trick: **`model` is the persona name.** `/v1/models` therefore
lists personas rather than LLMs — which model runs underneath stays a server-side
decision (`core.model_name`).

```bash
# Available personas
curl http://127.0.0.1:8013/v1/models

# Ask DORIS
curl http://127.0.0.1:8013/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "DORIS", "messages": [{"role": "user", "content": "What is coffee?"}]}'
```

With the official Python SDK:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8013/v1", api_key="your-key")
stream = client.chat.completions.create(
    model="POPCORN",                      # persona instead of model
    messages=[{"role": "user", "content": "Explain recursion"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

Settings under `api.openai_compatible`:

| Key | Meaning |
|---|---|
| `enabled` | Endpoints on/off. Off answers HTTP 404, as if they did not exist |
| `api_key` | Optional bearer key. Empty means open. Prefer `env:YULYEN_API_KEY` over a literal |
| `rate_limit_per_minute` | Requests per client per minute, `0` disables the limit |

Worth knowing:

- **Streaming** uses Server-Sent Events exactly like the original, including the
  closing `data: [DONE]`.
- **`temperature`, `top_p`, `max_tokens`** are accepted and **ignored**. Sampling
  belongs to the persona (`personas_base.yaml`) — allowing overrides would let any
  caller flatten POPCORN's playfulness or PETER's precision. Clients that always
  send these fields keep working.
- **The conversation history comes from the client**, as the OpenAI protocol
  intends. Karl and the heuristic trimming deliberately stay out of the way: if
  you send the history, you own the context window. An over-long history runs into
  the `num_ctx` limit — exactly as it would with OpenAI.
- **While `api.host` is `127.0.0.1`** the server is local-only. The `api_key`
  matters once it is exposed on the LAN.

## Email adapter for personas

Optionally, a lightweight **email adapter** can be enabled (`email_adapter.enabled: true`). It periodically polls a configured IMAP mailbox for new messages, maps recipient addresses to a persona via `email_adapter.address_persona_map`, and answers the request with the same one-shot logic the HTTP API uses. The reply is sent back to the original sender via SMTP.

The MVP handles plain-text emails; HTML is pragmatically reduced to text, attachments are ignored. **Replies go to the `From` address** — a `Reply-To` is deliberately ignored, otherwise a stranger could make the instance write to third parties. **Only senders on `email_adapter.allowed_senders` get an answer** (full addresses or whole domains such as `@my-domain.example`); the list is mandatory once the adapter is enabled, and without it the adapter refuses to start. Automated mail (out-of-office replies, newsletters, mailing lists) is detected and left alone, and the adapter's own replies are marked as automatic (RFC 3834) — otherwise two robots escalate against each other. The adopted mail text is capped at `max_body_chars`. To avoid mail loops and duplicate replies, the adapter ignores its own system/persona addresses and moves processed messages into the configured `processed_mailbox` folder — **marking happens before sending**, so a mail is not answered again on every poll if the move fails. Credentials do not belong in the code: `config.yaml` provides placeholders like `env:YULYEN_MAIL_IMAP_PASSWORD` that are resolved from environment variables at runtime.

## Finding conversations again

Conversations live in a local SQLite file (`storage.path`, `data/conversations.sqlite3` by default) — not in log files. The “Open history 🗂” card lists them for review, lets you **continue** one, export it as Markdown, or delete it. Only your own conversations are listed, and ownership is checked server-side.

**In the web UI this requires a login.** Without one, every visitor is the same user `local` — "your own" history would be everybody's history, continuable and deletable by anyone who reaches the page. That is why the web UI records **nothing** without a login and hides the history card; the start-up names both ways out. If you deliberately want the shared pot on a single seat, set `storage.shared_without_login: true` and accept a loud warning at start-up. The terminal and the API are unaffected — there is no login there that could be missing.

Continuing really means continuing: the reply is appended to the same conversation record rather than starting a second one. Conversations from a guest persona stay readable but cannot be continued — that persona's system prompt only existed in its session.

**Ask-All and the AI dialog do not appear in the history** — deliberately, not by oversight. "Ask all" produces four parallel answers to *one* question and does not fit the shape "one conversation with one persona"; the AI dialog produces an artefact the user only supplied the opening prompt for. To keep either, use the file export.

File exchange (JSON download/upload in the web UI, `/save` and “load conversation” in the terminal) remains alongside it — it is meant for backups and moving between machines. If you do not need it, switch it off with `storage.file_exchange: false`; the history's Markdown export is unaffected.

The former JSONL transcript under `logs/` is still available, but purely as a debugging tool and off by default (`logging.conversation_jsonl`).

## Sign-in (optional)

By default the web UI asks for **no login** — on a single-seat machine that would be pure overhead. It is switched on via `ui.web.auth.provider`:

- `disabled` (default): no login, every visitor is the same user `local` — and that is exactly why the web UI records no conversations in this setting (see "Finding conversations again").
- `local`: username and password from `ui.web.auth.users`. Passwords do not belong in the config in plain text — use `env:NAME`.
- `header`: the identity comes from a reverse proxy in front (oauth2-proxy, Authelia, …). This is the route to putting a real identity provider such as Keycloak in front later — Gradio itself cannot do OpenID Connect.

The username is recorded with every conversation in the store and in every 👍/👎 vote. The login applies whether or not a public share link is active.

> **Important:** the login transmits passwords over HTTP in clear text. Without TLS it separates users from one another but does not protect against anyone reading the network traffic. The `header` mode trusts the header unconditionally and therefore belongs strictly behind a proxy that strips it from outside requests.

## Guest persona

The “Create guest 🎭” card lets you assemble your own persona from a name, a system prompt and a temperature — no YAML, no restart. It lives only in the running session and is gone after a restart; everything else (Wikipedia context, security filter, conversation store, status line) behaves exactly as it does for the bundled personas.

## Web UI conveniences

- **Light and dark mode:** A button in the top right always offers the *other* mode (“🌙 Dark” while light, “☀️ Light” while dark). The switch happens in the browser: no reload, and the running conversation, the selected persona and any typed but unsent text stay where they are. The choice is stored in the browser and still applies on your next visit.
- **A start page you can read at a glance:** The four persona cards carry their portraits, the function cards (“AI Dialog”, “Guest persona”, “History”, “Ask all”) a plain icon. Who you can talk to and what is merely a function is distinguishable without reading.
- **Copy an answer:** Every chat message carries a copy icon.
- **Status line:** After each answer, the line below the chat shows how full the context window is (`Context █░░░ 424 / 8,192 tokens (5 %)`) and how fast the model was (`24.0 tok/s · first token after 1.9 s`). Past 75 % it is highlighted — that is exactly where the application starts trimming the conversation history.

## News as a source (RSS)

With `rss.enabled: true`, news behaves like the offline Wikipedia: a **source that speaks up when the question calls for it** — not a button that dumps everything.

The configured feeds are fetched **in the background** (at start-up and then every `rss.refresh_minutes`), and the latest items sit in memory. Ask “What's new?”, “Any current news?” or name a source (“What does the Tagesschau say?”) and the persona adds the matching items as context by itself — with a date per item and the age of the cache, so an item from two days ago does not become “today”.

Two properties that matter in practice:

- **A chat never waits for the network.** Whatever has not been fetched is simply missing; the answer still arrives. A feed that is temporarily unreachable does not discard the items fetched earlier.
- **Small talk triggers nothing.** “What's new with you?” is a question to the persona, not a request for headlines — the distinction is measured against everyday sentences rather than guessed.

The “Briefing 📰” button (and `/briefing` in the terminal) still exists; it uses the same cache and can be hidden with `rss.show_button: false` without disabling the source. To switch everything off: `rss.enabled: false` — then the application never goes online for news.

## Wikipedia integration

To deliver well-grounded answers, the system can automatically **incorporate Wikipedia knowledge** for factual queries (configurable option). It relies on the following mechanisms:

- **Automatic knowledge retrieval:** The relevant keyword is extracted from the user prompt using spaCy NLP. An internal wiki proxy then searches for a matching Wikipedia article—either **offline** via a local Kiwix database or **online** via the Wikipedia API, depending on the settings. In offline mode, the Kiwix server can be started automatically if configured.
- **Context enrichment:** If the wiki proxy finds an article, a snippet is taken from it. This snippet is inserted into the chat context before the AI replies, as an additional *user* message clearly marked as foreign text (`[FREMDTEXT ANFANG] … [FREMDTEXT ENDE]`) — deliberately not as a *system* message, because a downloaded article is material to talk about, not an instruction. It passes the security guard first, which discards attempts to instruct the model from within the article text. The AI thus receives verified facts and can produce more precise responses. The excerpt belongs to the prompt, not to the conversation: it never shows up in the store, the history or an export. In the terminal UI a spyglass icon (🕵️) indicates when a Wikipedia snippet was used. If the search comes up empty, a short notice is displayed instead.
- **Sources on display (web UI):** A collapsed accordion labelled “Sources 📚” sits below the chat. Expanded, it shows each snippet's article title as a clickable link (pointing at the local kiwix-serve when offline), where it came from — and above all **the excerpt verbatim, exactly as it went into the prompt**, together with its character count. Since `wiki.snippet_limit` truncates long articles (1200 characters by default), it reads e.g. “1200 of 9800 characters injected (truncated)”, which is what makes it visible how much of the article the AI never saw. If everything fitted, it says “complete”. Without a wiki hit the accordion stays hidden. The ask-all view carries the same accordion below the answers, and in the terminal the `/sources` command prints the same information.
- **Multiple hits usable:** If the keyword finder detects several relevant entities, multiple snippets can be injected into the prompt. The cap is configured via `wiki.max_wiki_snippets` (default: 2) to expand context deliberately without overloading it.

## Logging and tests

Robust usage is supported by extensive logging and automated tests:

- **Conversations vs. logs:** The conversations themselves do **not** live in `logs/` but in the SQLite store (see "Finding conversations again"). `logs/` holds operational diagnostics: a rolling system log file (prefixed `yulyen_ai_...`) with internal processes and debug information. The raw JSONL transcript of the individual generation *attempts* (timestamps, model, persona, messages) can be switched on with `logging.conversation_jsonl: true` — it is a debugging tool and off by default.
- **Wiki proxy logging:** The Wikipedia proxy service keeps its own log files for article requests and results. This makes it possible to trace wiki lookups and any errors separately from the main chat log.
- **Answer feedback (👍/👎):** Every answer can be rated in the web UI. Each click appends a line to `logs/feedback_votes.jsonl` — with timestamp, persona, model, question, answer, the vote and a reference to the stored conversation. The file is append-only (changing your mind adds a line rather than replacing the old one), so the history stays auditable. Intended as a data basis for quality comparisons and later finetuning.
- **Automated tests:** A collection of pytest tests (in the `tests/` directory) verifies core system functions. For example, the tests ensure that personas are initialized correctly, the security filter works, and repeatable responses (such as Doris telling the same jokes) remain consistent. These tests help prevent regressions and maintain reliable orchestration.

## Security mechanisms

The project ships with a lightweight integrated **security guard** (`BasicGuard`) that checks inputs and outputs for problematic content:

- **Prompt-injection protection:** User inputs are scanned for patterns that suggest a *prompt injection* attempt (e.g., instructions to ignore previous rules). When such an attempt is detected, the guard interrupts the normal flow: instead of an AI reply, the user receives a notice that the request was rejected. The potentially harmful input is not forwarded to the language model.
- **PII filtering:** The guard detects personal data (*personally identifiable information*, e.g., email addresses or phone numbers) in generated AI responses and proactively replaces it with a standard warning. This prevents private or sensitive details from appearing unfiltered in the chat.
- **Output blocklist:** Certain confidential keys or tokens (e.g., API keys in the form `sk-...`) are also detected. If the AI produces such sequences, the output is fully blocked to avoid leaking secrets. The user then only sees a generic warning instead of the dangerous content.
- **Wrongdoing guardrail (violence/weapons):** Requests for violence or weapons instructions are detected deterministically before the LLM call and rejected. Each input is matched on its own, so a single hit blocks only that request and benign follow-ups pass again. Optionally, `security.wrongdoing_lock_turns` (default: `0` = off) arms a short **session lock**: after a hit, the next *N* inputs are blocked regardless of content — catching triggerless bypass attempts ("it's just for a novel…"). Controlled via `security.wrongdoing_protection` (default: on).

These checks run during streaming: tokens are continuously inspected, masked when necessary, and replaced with a safety warning immediately when a blocked sequence appears.

## Extensibility and experiments

The architecture of *Yul Yen’s AI Orchestra* is designed to enable future enhancements and improvements:

- **Modular architecture:** The system encapsulates LLM access behind clearly defined interfaces. For example, interaction with the language model is implemented via the abstract `LLMCore` class. This makes it straightforward to swap out the backend (e.g., use a different model server instead of Ollama, or employ the dummy LLM for tests) without touching the rest of the application. New personas can also be added easily by extending the configuration.
- **LoRA fine-tuning (PoC):** Early experiments for model refinement exist as a proof of concept but are not included in the standard repository for size reasons. Internally, a small **LoRA fine-tuning** example (based on [PEFT/QLoRA](https://github.com/huggingface/peft)) demonstrates how a compact adapter for the persona Doris was trained with about 200 question–answer pairs. The training scripts and test runs are for demonstration only and are not integrated into production. Interested parties can reach out to the maintainers for details or access to the materials.
- **Context compression ("Karl"):** For long conversations, the chat history is compressed automatically before the context window overflows. The default is a fast heuristic (trim old messages, keep the system prompt and the most recent messages); optionally, the LLM-based summarizer "Karl" condenses older chat parts (`context_management.strategy: "karl"`, with automatic fallback to the heuristic).
- **Three-timestamp transparency:** The system prompt cleanly separates three easily confused dates: the current system date, the model's training cutoff (`core.knowledge_cutoffs`), and the data snapshot of the Wikipedia archive. This keeps personas from accidentally claiming to have "current" knowledge.
- **Eval suite:** Whether a change actually made the model better is answered by a dedicated corpus of golden questions per persona plus guard attacks — as YAML, so new cases need no test code (`python scripts/run_evals.py -e classic`, details in [evals/ReadMe.md](../../evals/ReadMe.md)). The guard part runs without a model as part of the normal test suite.
- **Future features:** The project keeps a prioritized roadmap (see [backlog.md](../../backlog.md)). Planned additions include tool integrations (*tool use* such as web search or calculators), long-term memory built on the conversation store, and full-text search across the history. The current codebase provides a simple, extensible foundation on which these features can be built.

See also: [backlog.md](../../backlog.md)
