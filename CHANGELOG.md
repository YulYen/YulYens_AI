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
in `config.yaml`, the command line of `src/launch.py`, the HTTP endpoints
(`/ask`, `/v1/…`, `/health`, `/healthz`), and the ensemble YAML format. Break
any of those and the number on the left goes up. So does a change that
*silently* alters what an unchanged, running installation does — that is the
most expensive kind, because nothing forces the operator to notice.

Released entries are a dated record and are not edited afterwards. If something
in them turns out to be wrong, it gets corrected in a later entry.

## [Unreleased]

### Added

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

- **The start page is split into two sections**, in the web UI and the
  terminal: **Solo** (chat with one persona, plus the guest persona) and
  **Orchestra** (AI dialog and Ask-All, plus the history card in the web UI).
  Every persona of the ensemble appears in both. In the terminal menu the
  numbers stay the same (`1`–`4`); the Ask-All entry now reads `[4] Ask-All`.

- **The default model is now `ministral-3:14b`** (previously
  `ministral-3:8b`). It needs about 9 GB and is meant for a 16 GB graphics
  card. **Before updating, run `ollama pull ministral-3:14b`.** Without it,
  `--doctor` reports the model as missing and the personas cannot answer.
  **On an 8 GB card**, keep the old model by setting
  `core.model_name: "ministral-3:8b"` in `config.local.yaml`. Both models
  share the same knowledge cutoff (2023-10), so the date the personas are
  told about their knowledge stays the same.

- **Python 3.12 or newer is now required** (previously 3.10). Python 3.10
  reached its end of life in October 2026, and the libraries this project
  depends on no longer ship fixes for it — security fixes for two of them
  could not even be installed there. On 3.10 or 3.11, `pip install -r
  requirements.txt` now fails with "no matching distribution"; create a new
  virtual environment with 3.12+ and install the requirements again. Tested
  in CI on 3.12 (Linux and Windows) and 3.14. 3.15 is not supported yet,
  because the speech output (Piper) has no build for it.

- The feedback vote log moved from `logs/feedback_votes.jsonl` to
  `data/feedback_votes.jsonl`, next to the conversation store it refers to.
  `logs/` holds diagnostics you may delete at any time; these votes are
  collected human judgement and cannot be reproduced. An existing file is
  **moved automatically** on first use. If both locations somehow hold a file,
  neither is touched and a warning names both — merging them would be guesswork.
  The location follows the directory of `storage.path`, so moving the store
  moves the votes with it.

- The default Kiwix location in `config.yaml` moved from
  `C:\wikipedia-de-offline\` to `C:\Develop\wikipedia-de-offline\`
  (`wiki.offline.kiwix_exe` and `wiki.offline.zim_path`). **If your Kiwix
  folder is still in the old place**, either move it or set both paths in
  `config.local.yaml`. Otherwise kiwix-serve does not start, `--doctor`
  reports Kiwix as unreachable, and answers come without Wikipedia snippets.
  Everything else keeps working. The default dump is now
  `wikipedia_de_all_nopic_2026-10` (previously `2026-01`). If you keep the
  older file, set `wiki.offline.zim_prefix` and `zim_path` to it as well —
  the personas are told the dump date from `zim_prefix`.

- **The classic personas are tuned for `ministral-3:14b`.** They answer
  shorter and calmer, mention their siblings only when it fits, and are told
  not to invent numbers or sources. In detail: lower temperatures (LEAH 0.55,
  DORIS 0.5, POPCORN 0.7; PETER stays at 0.1), no `repeat_penalty` of their
  own any more (Ollama's default applies), a context window of 16384 tokens
  instead of 8192, and Wikipedia snippets of up to 2400 characters instead of
  1200 (`wiki.snippet_limit`). The conversation summary now keeps the user's
  instructions about language and format. **On an 8 GB card with the 8B
  model**, set `num_ctx` back to 8192 in `ensembles/classic/personas_base.yaml`
  and `wiki.snippet_limit` to 1200 in `config.local.yaml`: at 16384 the 8B
  needs about 7.5 GB and no longer fits next to the desktop.

### Fixed

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

[Unreleased]: https://github.com/YulYen/YulYens_AI/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/YulYen/YulYens_AI/compare/v1.1.0...v2.0.0
