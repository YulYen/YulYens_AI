# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Auf Deutsch:** dieses Changelog ist bewusst englisch, obwohl Code, Backlog
> und `CLAUDE.md` deutsch sind. Die deutschen Dateien richten sich an den
> Entwickler, diese hier an den Betreiber — und der ist im Zweifel jemand
> anderes. Die Begründung steht in `CLAUDE.md`, Abschnitt „Versionierung".

**What belongs in here: only what someone running this notices.** A new switch
in `config.yaml`, a changed default, a new button, a removed option, a required
field. Internal work does not — a rewritten moderator or a split-up module
changes nothing for the person starting the app. The development history,
including the reasoning behind each decision, lives in
[`backlog_archiv.md`](backlog_archiv.md); that is the developer-facing record
and it is not duplicated here. (It sat in the archive section of
[`backlog.md`](backlog.md) until 2026-08-06 — older entries below still point
there, and that link keeps working: the backlog links on to the archive.)

**What a MAJOR bump means.** The public contract of this project is: the keys
in `config.yaml`, the command line of `python -m yulyen_ai`, the HTTP endpoints
(`/ask`, `/v1/…`, `/health`, `/healthz`), and the ensemble YAML format. Break
any of those and the number on the left goes up. So does a change that
*silently* alters what an unchanged, running installation does — that is the
most expensive kind, because nothing forces the operator to notice.

Released entries are a dated record and are not edited afterwards. If something
in them turns out to be wrong, it gets corrected in a later entry.

## [Unreleased]

### Breaking

- **The app is now an installable package and starts with
  `python -m yulyen_ai`.** `python src/launch.py` no longer exists. After
  pulling, run **`pip install -e .`** once in your virtual environment (it
  installs the same pinned requirements as before, plus the package itself),
  then start with `python -m yulyen_ai -e classic`; `--doctor`,
  `--list-ensembles`, `--version` and `-c` work as before. Update shortcuts,
  autostart entries and the VS Code task that call `src/launch.py`. The
  scripts in `scripts/` (`mcp_server.py`, `warmup_ping.py`, …) also need the
  installed package now — an MCP client registered with
  `python <path>/scripts/mcp_server.py` keeps working once it is installed.
  Only editable installs are supported: `config.yaml`, `ensembles/`, `locales/`
  and `static/` stay next to the code. A non-editable `pip install .` now stops
  at import with a message naming the right command.

- **The measuring tools have left this repository.** `scripts/run_evals.py`,
  `scripts/run_bench.py`, `scripts/blind_tasting.py` and
  `scripts/probe_injection.py`, the eval corpora under `evals/`, the
  `make evals`, `make evals-full`, `make bench` and `make test-all` targets
  and the `ollama` test marker are gone; they live on in the project's
  separate lab repository. What you run — the app, the API, the mail adapter,
  the MCP server, `warmup_ping.py` — is unchanged. **If your
  `config.local.yaml` has an `evals:` section, delete it:** the key is no
  longer known, so the start logs a warning and `--doctor` and `/healthz`
  report it as a configuration problem. The model reports that the README
  linked for choosing a model are in release
  [`v3.0.0`](https://github.com/YulYen/YulYens_AI/tree/v3.0.0/docs); the
  README now carries the short answer as a table (VRAM → model → ensemble).

- **A `share_auth` block in the config now stops the start** (exit code 4).
  `ui.web.share_auth` used to be read as a fallback login when no
  `ui.web.auth` section existed. Simply dropping it would have left such an
  installation **running without a login** after the update, so the start
  refuses instead and names the replacement. **Move the user to
  `ui.web.auth`** (`provider: local`, `users: {name: "env:VARIABLE"}`) and
  delete the `share_auth` block — also an empty one.

- **The `briefing:` section is no longer read.** It has been called `rss:`
  since 2.0.0 and was kept as an alias with a warning. **If your config still says
  `briefing:`, rename it to `rss:`** — otherwise the feeds are off, the start
  logs an unknown section and `--doctor` reports it.

### Removed

- `modelfiles/` (Ollama Modelfiles for models the project no longer uses) and
  `examples/` (a terminal config for a 7B model and an image helper). Neither
  was referenced anywhere; both remain in release `v3.0.0`.

### Fixed

- **Voice input no longer fails on a machine with an NVIDIA card but without
  the CUDA libraries.** With `stt.device: auto` (the default) every recording
  failed with `Library cublas64_12.dll is not found`; it now falls back to the
  CPU on the first recording, logs a warning once and stays there. An explicit
  `stt.device: cuda` still reports the error instead of switching silently.
- **Install voice input with `pip install faster-whisper "av<19"`.** PyAV 19
  breaks faster-whisper 1.2.1 (`unexpected keyword argument
  'metadata_errors'`), and faster-whisper does not cap it, so a plain
  `pip install faster-whisper` gets the broken pair. If you already have it,
  run `pip install "av<19"`. The web UI's error message now says exactly that
  instead of showing the raw error.

## [3.0.0] - 2026-11-24

**Read "Breaking" before you update.** This release needs Python 3.12 and a
new default model, and an installation that relied on a few lenient defaults
may no longer start. Each entry below says what to do.

What is new for the person using it: Gemma 4 (`gemma4:26b`) as the default
model with the classic personas tuned for it, full-text search across your own
conversations, a verdict that closes an Ask-All round, an optional own model
per persona for one-on-one chats, and an MCP server that makes the personas
available as tools in Claude Code and other MCP clients. Retrieved Wikipedia
and news text is checked against more injection patterns, and a number of
fixes concern what ends up in the conversation store.

### Breaking

- **Python 3.12 or newer is now required** (previously 3.10). Python 3.10
  reached its end of life in October 2026, and the libraries this project
  depends on no longer ship fixes for it — security fixes for two of them
  could not even be installed there. On 3.10 or 3.11, `pip install -r
  requirements.txt` now fails with "no matching distribution"; create a new
  virtual environment with 3.12+ and install the requirements again. Tested
  in CI on 3.12 (Linux and Windows) and 3.14. 3.15 is not supported yet,
  because the speech output (Piper) has no build for it.

- **The default model is now `gemma4:26b`** (previously `ministral-3:8b`).
  It is 18 GB and meant for a 16 GB graphics card plus system RAM: part of the
  model sits in RAM, so the first answer after a start (or after `keep_alive`
  ran out) takes about 25 seconds; after that it writes nearly twice as fast
  as `ministral-3:14b`. **Before updating, run `ollama pull gemma4:26b`.**
  Without it, `--doctor` reports the model as missing and the personas cannot
  answer. **On a 12–16 GB card** use `ministral-3:14b` together with the new
  ensemble `examples/classic_ministral14b`, which keeps the persona settings
  tuned for that model; **on an 8 GB card** keep `ministral-3:8b`. Either way,
  set `core.model_name` in `config.local.yaml`. The personas are told that
  their knowledge reaches January 2025 (Gemma, per Google's model card) or
  October 2023 (Ministral).

- **The default Kiwix location in `config.yaml` moved** from
  `C:\wikipedia-de-offline\` to `C:\Develop\wikipedia-de-offline\`
  (`wiki.offline.kiwix_exe` and `wiki.offline.zim_path`). **If your Kiwix
  folder is still in the old place**, either move it or set both paths in
  `config.local.yaml`. Otherwise kiwix-serve does not start, `--doctor`
  reports Kiwix as unreachable, and answers come without Wikipedia snippets.
  Everything else keeps working. The default dump is now
  `wikipedia_de_all_nopic_2026-10` (previously `2026-01`). If you keep the
  older file, set `wiki.offline.zim_prefix` and `zim_path` to it as well —
  the personas are told the dump date from `zim_prefix`.

- **An unknown `ui.web.auth.provider` now stops the start** (exit code 4)
  instead of silently running without login. A typo such as `provider: lokal`
  used to log a warning and open the web UI to everyone who could reach it.
  **If your installation starts with a warning about an unknown provider
  today, it will no longer start** — correct the value to `local`, `header`
  or `disabled`.

- **`/healthz` requires the API key once one is configured.** The deep check
  names models, paths and configuration problems and queries Ollama and Kiwix
  on every call, so it now sits behind `api.openai_compatible.api_key` and the
  rate limit, like `/ask` and `/v1`. **If a monitor polls `/healthz` and you
  have set a key**, give it the `Authorization: Bearer …` header or point it at
  `/health`, which stays open. Without a configured key nothing changes.

### Added

- **MCP server: the personas as tools for Claude Code and other MCP
  clients.** Opt-in: `pip install 'mcp>=2.3,<3'`, then for example
  `claude mcp add yulyen -- python <path>/scripts/mcp_server.py -e classic`.
  Three tools: `list_personas`, `ask_persona(persona, question)` and
  `ask_all(question)`. Answers go through the same guard and wiki as `/ask`.
  `ask_persona` is recorded in the conversation store under the channel `mcp`,
  also on an installation without login, like the terminal and the API;
  `ask_all` is not recorded, like every ask-all round.

- **`scripts/blind_tasting.py` runs a blind tasting.** Two states of an
  ensemble (`classic@main` from git against `classic` in the working tree) or
  two models answer the same 14 probes from `evals/tasting_probes.yaml`. The
  script writes `blatt.md` without names and `schluessel.json` with the key;
  `tally` counts your verdicts per persona. Both sides get the same `seed`,
  so a tasting can be repeated. It needs Ollama.

- **`scripts/warmup_ping.py` loads the chat model ahead of time.** A model
  that does not fully fit into VRAM (the new default `gemma4:26b` on a 16 GB
  card) takes well over a minute to load from disk on its first use. Run the
  script at Windows startup or when opening VS Code, and the app finds a warm
  model. It keeps the model loaded for an hour (`--keep-alive`, `-1` =
  forever) and uses the same context size as the app, so Ollama does not
  reload it on the first question. It never fails loudly: if Ollama is not
  running, it logs that and exits normally.

- **`run_evals.py --rejudge <answers.json>`** grades the answers of an
  earlier run again, with another `--judge-model`, without asking the chat
  model a second time. Every run now writes its answers to `answers.json`
  next to the report. The suite also answers every case first and judges
  afterwards: with a judge that does not fit into VRAM next to the chat model,
  Ollama no longer reloads both for every case. `duration_ms` in
  `report.csv` now covers the answer only, no longer answer plus verdict.

- **`run_evals.py --model <name>`** runs the eval suite against another model
  without editing the config, as `run_bench.py --model` already did. Pass
  `--judge-model` too when comparing models — by default the judge is the chat
  model, so two runs would be graded by two different judges.

- **A persona can have its own model for one-on-one chats.** Add an optional
  `model:` to a persona in `personas_base.yaml` (for example
  `model: "qwen3:15b"` for PETER). That persona then answers with this model
  whenever you talk to it alone — in the web UI, the terminal, the API and the
  mail adapter. In **Ask-All, the verdict and the AI dialog** every persona
  still plays on the shared `core.model_name`, so PETER answers with Qwen alone
  and with the default model in the group. The start page shows the own model
  on the persona's card (terminal: next to its name), and the greeting names
  the model actually in use. Guest personas always use the default model.
  `--doctor` and `/healthz` check every configured model, so **run
  `ollama pull` for it first**. Switching between a persona's own model and the
  group can mean Ollama has to load a model, which makes the first answer
  slower. Without any `model:` entry nothing changes except the start page
  layout (see below).

- **Full-text search across your own conversations.** A search box above the
  picker in the history card, and `/suche <term>` in the terminal. It searches
  every stored message and shows the matching passage with persona and date;
  an empty box lists everything again. Several words mean AND, and special
  characters are treated as text rather than query syntax. The same ownership
  check as the rest of the history applies. The index (SQLite FTS5) is built on
  the first start after this update, existing conversations included — there is
  nothing to configure. If your SQLite was built without FTS5, the database
  stays at its previous version, **recording keeps working unchanged**, and only
  search returns nothing.

- Ask-All can now close a round with a **verdict**: one more model run that
  summarises the personas' answers, says where they agree and differ, and
  names the strongest one. It appears as its own section below the personas.
  It is **off by default** and costs a full extra model run, so you opt in per
  question — a checkbox under the input field in the web UI, a single yes/no
  question in the terminal (empty answer means no). Very long answers are
  trimmed for this run so a verbose round cannot exhaust the context window.
  There is no config switch: the checkbox is the decision. The verdict itself is
  not written to the conversation store.

### Changed

- **The classic personas are tuned for `gemma4:26b`.** LEAH runs warmer
  (temperature 0.8, previously 0.55): Gemma's own default is 1.0, so the value
  carried over from `ministral-3:14b` made her sound flat. DORIS no longer answers as one of her siblings ("PETER: …"),
  and PETER no longer picks the well-known German palindrome that contains a
  racial slur as his example. The context window stays at 16384 tokens —
  8192 was measured and is not faster with Gemma. The previous settings for
  `ministral-3:14b` remain available as `examples/classic_ministral14b`.

- **Reasoning models answer without their thinking phase.** Every request to
  Ollama is now sent with thinking switched off (Qwen 3.x, Gemma 4 and
  similar). The app only ever displayed the answer, never the reasoning, so
  such a model used to stay silent for a long time before the first character.
  This applies to every model, including those that do not report the
  `thinking` capability: Google's QAT build of Gemma 4 does not report it but
  thinks anyway, and returned empty answers. Models that cannot think
  (`ministral-3` among them) accept the switch and answer as before.

- **The web UI no longer sends Gradio telemetry.** Gradio's version check
  and its usage analytics (sent to Hugging Face) are switched off, so starting
  the app makes no outside request of its own. On a machine with a broken
  network this also fixes a start that printed its error after three seconds
  but kept the process alive for minutes.

- **kiwix-serve is started on the configured address only.** With
  `wiki.offline.autostart`, the server used to listen on every network
  interface, so the offline Wikipedia was readable from the whole LAN although
  `wiki.offline.host` said `127.0.0.1`. It is now started with `--address`.
  If `host` is a name rather than an IP address (e.g. `localhost`), the
  argument is left out and a warning says so.

- **The start page is split into two sections**, in the web UI and the
  terminal: **Solo** (chat with one persona, plus the guest persona) and
  **Orchestra** (AI dialog and Ask-All, plus the history card in the web UI).
  Every persona of the ensemble appears in both. In the terminal menu the
  numbers stay the same (`1`–`4`); the Ask-All entry now reads `[4] Ask-All`.

- The feedback vote log moved from `logs/feedback_votes.jsonl` to
  `data/feedback_votes.jsonl`, next to the conversation store it refers to.
  `logs/` holds diagnostics you may delete at any time; these votes are
  collected human judgement and cannot be reproduced. An existing file is
  **moved automatically** on first use. If both locations somehow hold a file,
  neither is touched and a warning names both — merging them would be guesswork.
  The location follows the directory of `storage.path`, so moving the store
  moves the votes with it.

- **`examples/classic_ministral14b`: the personas tuned for `ministral-3:14b`.**
  Before the switch to Gemma this was the tuning of `classic`; it now lives on
  unchanged in this example ensemble. The personas answer shorter and calmer, mention their siblings only when it fits, and are told
  not to invent numbers or sources. In detail: lower temperatures (LEAH 0.55,
  DORIS 0.5, POPCORN 0.7; PETER stays at 0.1), no `repeat_penalty` of their
  own any more (Ollama's default applies), and a context window of 16384
  tokens instead of 8192. **For every ensemble:** Wikipedia snippets of up to 2400 characters instead of
  1200 (`wiki.snippet_limit`). The conversation summary now keeps the user's
  instructions about language and format. **On an 8 GB card with the 8B
  model**, set `num_ctx` back to 8192 in `ensembles/classic/personas_base.yaml`
  and `wiki.snippet_limit` to 1200 in `config.local.yaml`: at 16384 the 8B
  needs about 7.5 GB and no longer fits next to the desktop.

### Fixed

- **`--doctor` and `/healthz` no longer warn about the default model on a
  16 GB card.** `model_vram` now recognises mixture-of-experts models such as
  `gemma4:26b`: if one does not fit entirely into free VRAM, that is reported
  as information, since part of it may sit in system RAM (slower first start,
  barely slower afterwards). Dense models still get the warning. The check
  also no longer warns against itself when the model is already loaded: the
  VRAM that model occupies counts as free.
- **A search term with `#` no longer fetches the wrong Wikipedia article.**
  The wiki proxy put the term into the Kiwix URL unencoded, so everything
  after a `#` was dropped: a question about C# brought the article about the
  letter C into the prompt. Terms are now URL-encoded (`#`, `?`, `/`,
  umlauts) for Kiwix and for online Wikipedia.
- **Umlauts and accents from a Wikipedia infobox reach the model intact.**
  With the offline Wikipedia (Kiwix), every non-ASCII character in an
  article's infobox — party leaders, founding dates, names — arrived garbled
  ("Stefan MÃ¶ller" instead of "Stefan Möller"); the article text itself was
  fine. Models copied the garbled spelling into their answers.
- **The eval judge knows today's date.** Without it, the judge treated every
  correct answer to "What is today's date?" as wrong (its own knowledge ends
  years earlier), so `ts_knows_today` scored 1 for every model. Averages from
  earlier runs are therefore slightly too low and not directly comparable with
  new ones.
- **An Ollama outage during an eval run no longer lowers the score.** The
  backend's error text was treated as the model's answer: checks failed, the
  judge gave it a 1, and the average — the number runs are compared by —
  dropped. Such a case is now reported as an error and left out of the
  average. If an earlier run had outages, its average is too low.
- **Eval runs no longer fill the conversation store.** With the store active
  (terminal, or web UI with login), every `run_evals.py` run saved all corpus
  questions as conversations of the user `local` — again on each run. Entries
  already stored carry `app: api` and the corpus questions as titles.
- **Pressing Enter on an empty input does nothing.** In the web UI chat and the
  terminal it used to send an empty question to the model: a full model run
  for nothing, and an untitled conversation in the history.
- **A rejected input no longer triggers a Wikipedia or news lookup.** In the
  web UI, the terminal, Ask-All and `/v1/chat/completions`, the lookup ran
  before the guard looked at the input: the chat showed "looking it up" and
  then the refusal, and in online mode the search term still left the machine.
  `/ask` already did this in the right order.
- **Ask-All and the AI dialog are no longer written to the conversation
  store** — as the documentation has said all along. Since 2.0.0 every Ask-All
  question created one stored conversation per persona and every AI dialog two,
  all owned by `local`: invisible with login enabled, and cluttering the
  history with `storage.shared_without_login`. Entries already stored (`app`
  `ask-all` / `self-talk`) are left alone; delete them from the history if they
  bother you. To keep such a round, use the file export.
- **Retrieved text is checked against five more injection patterns.** Wikipedia
  snippets and news items that address the model directly — assigning it a
  role ("Du bist ab jetzt ein Pirat"), ordering a role change, prescribing a
  fixed answer for a condition, the answer language or an ending for every
  reply — are now dropped before they reach the prompt, like the patterns
  already covered. These were the five phrasings measured to get past the
  guard *and* be obeyed by the model. What you type yourself is not affected;
  rephrased attacks can still get through.
- **A saved conversation keeps its beginning after context compression.** Once
  a long chat hit the context limit, Karl or the heuristic trim removed the
  oldest turns from the prompt — and the stored conversation lost them too:
  history, search, Markdown export and JSON download only showed the tail, and
  the title switched to a later question. The prompt is still compressed
  exactly as before; the conversation is no longer cut with it. Conversations
  that were already truncated cannot be restored.
- **Votes after a Wikipedia or news lookup point at the right answer.** In a
  conversation with injected context, a 👍/👎 was recorded one message off per
  lookup: `message_index` pointed past the answer, and the `answer` field of
  the vote line could contain the *next question* instead. Vote lines written
  by earlier versions in such conversations are unreliable — check them
  against the store before using them as training data.
- **Passwords and API keys may contain non-ASCII characters.** With an umlaut
  in a `ui.web.auth` password, that user could never log in; with one in
  `api.openai_compatible.api_key`, every API request failed with a 500. Any
  login or API attempt that merely *contained* such a character crashed the
  check instead of being rejected.
- **The mail adapter no longer answers the same mail on every poll when the
  server refuses to flag it.** A `NO` from the IMAP server (missing rights,
  custom keywords not allowed) was not noticed; the mail stayed unseen and got
  a new reply each cycle. Now no reply is sent unless the mail could be marked,
  and `\Seen` alone is tried when the server rejects the custom keyword.
- **An uploaded conversation belongs to whoever uploads it.** The owner was
  taken from the `user` field inside the JSON file, so with login enabled a
  file could place a conversation in someone else's history — and your own
  continued conversation was missing from yours.
- **`security.wrongdoing_lock_turns` counts user inputs only.** Retrieved
  Wikipedia snippets and news items went through the same counter: an article
  that matched a rule locked the user's next inputs, and after a real hit the
  snippets of the follow-up question used the lock up before the follow-up was
  checked. Only relevant if you set the option above 0.
- **A question containing "online" no longer pulls in the heise headlines.**
  Every word of a feed name was a trigger, so with the shipped feed
  `heise online` any sentence with "online" injected its news. Generic words
  in feed names (online, news, magazin, …) are no longer triggers; the proper
  name ("heise") and the full name still are.
- **A mail with a line break hidden in its subject gets its reply**, a guest
  persona whose name contains `&` or `#` is named correctly in the Wikipedia
  hint, and the status line no longer shows the speed of the previous answer
  after pressing Stop.
- **Self-talk in the web UI starts again.** Since 2.0.0, pressing start on the
  self-talk card failed with "Data incompatible with messages format" in the
  console instead of opening the conversation. The opening prompt was still
  sent to the chat window in the format of the previous Gradio version. The
  terminal self-talk was not affected.

## [2.0.0] - 2026-08-05

Baseline. Changelog-keeping starts here; this entry deliberately does not
summarise the development that came before it. For that history, see the
archive in [`backlog.md`](backlog.md).

**Why 2.0.0 and not 1.2.0.** The previous tag, `v1.1.0`, is from January 2026.
The public contract changed several times since — among them a changed default
for `ui.web.host`, a new required `email_adapter.allowed_senders`, and a web UI
without login no longer recording conversations. Those changes are real and
they are the reason the major digit moves; they are not itemised here, because
this file starts recording from this release onwards.

For what the project is and does, see the [README](README.md); for the
features in detail, [`docs/en/Features.md`](docs/en/Features.md).

[Unreleased]: https://github.com/YulYen/YulYens_AI/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/YulYen/YulYens_AI/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/YulYen/YulYens_AI/compare/v1.1.0...v2.0.0
