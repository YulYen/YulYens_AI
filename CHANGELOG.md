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

- Ask-All can now close a round with a **verdict**: one more model run that
  summarises the personas' answers, says where they agree and differ, and
  names the strongest one. It appears as its own section below the personas.
  It is **off by default** and costs a full extra model run, so you opt in per
  question — a checkbox under the input field in the web UI, a single yes/no
  question in the terminal (empty answer means no). Very long answers are
  trimmed for this run so a verbose round cannot exhaust the context window.
  There is no config switch: the checkbox is the decision. Like the rest of
  Ask-All, the verdict is not written to the conversation store.

### Changed

- The feedback vote log moved from `logs/feedback_votes.jsonl` to
  `data/feedback_votes.jsonl`, next to the conversation store it refers to.
  `logs/` holds diagnostics you may delete at any time; these votes are
  collected human judgement and cannot be reproduced. An existing file is
  **moved automatically** on first use. If both locations somehow hold a file,
  neither is touched and a warning names both — merging them would be guesswork.
  The location follows the directory of `storage.path`, so moving the store
  moves the votes with it.

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
