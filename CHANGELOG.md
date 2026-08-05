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
including the reasoning behind each decision, lives in the archive section of
[`backlog.md`](backlog.md); that is the developer-facing record and it is not
duplicated here.

**What a MAJOR bump means.** The public contract of this project is: the keys
in `config.yaml`, the command line of `src/launch.py`, the HTTP endpoints
(`/ask`, `/v1/…`, `/health`, `/healthz`), and the ensemble YAML format. Break
any of those and the number on the left goes up. So does a change that
*silently* alters what an unchanged, running installation does — that is the
most expensive kind, because nothing forces the operator to notice.

Released entries are a dated record and are not edited afterwards. If something
in them turns out to be wrong, it gets corrected in a later entry.

## [Unreleased]

Nothing yet.

## [1.0.0] - 2026-08-05

Baseline. Changelog-keeping starts here — this entry deliberately does not
summarise the five weeks of development that came before it. For that history,
see the archive in [`backlog.md`](backlog.md).

For what the project is and does, see the [README](README.md); for the
features in detail, [`docs/en/Features.md`](docs/en/Features.md).

[Unreleased]: https://github.com/YulYen/YulYens_AI/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/YulYen/YulYens_AI/releases/tag/v1.0.0
