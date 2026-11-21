"""Blind tasting: two ensemble states, the same probes, a sheet without names.

Every tuning step in #78/#80/#99 was decided by Yul tasting two sides blind —
the eval suite measures whether an answer is *right*, not whether it has charm.
The script for that was rebuilt by hand each time and never landed in the repo;
this module is it.

Three steps, each its own subcommand so the expensive one can be repeated
alone (``scripts/blind_tasting.py``):

1. ``answer`` — one side: an ensemble from the working tree or from a git ref
   (``classic@main``), optionally another model, answers every probe in
   ``evals/tasting_probes.yaml``. Runs in its own process (``run`` starts it
   twice), because Config, persona cache and factory are singletons — two
   ensembles in one process would share them.
2. ``sheet`` — shuffles the two sides per probe (half each way, so neither side
   can be guessed from its position) and writes ``blatt.md`` without names and
   ``schluessel.json`` with them. Open only the sheet before you have judged.
3. ``tally`` — reads the verdicts from the sheet and counts them per persona.

**What differs between the sides is only the ensemble and the model.**
``config.yaml``, the locale texts (wiki guardrail, timestamp block) and the
code come from the working tree on both sides. To taste a change in
``locales/``, check out the other state and run ``answer`` there.

Both sides get the same ``seed`` in their ``llm_options`` (default 0), so a
tasting can be repeated. It does not make the sides comparable sample by
sample — another prompt or temperature draws differently from the same seed.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROBES = REPO_ROOT / "evals" / "tasting_probes.yaml"
SHEET_NAME = "blatt.md"
KEY_NAME = "schluessel.json"
TALLY_NAME = "auswertung.md"

# (persona, messages) -> reply. Production wires it to the one-shot provider.
ReplyFn = Callable[[str, list[dict[str, str]]], str]

_PROBE_MARKER = re.compile(r"^<!-- probe: (?P<id>[\w-]+) -->\s*$")
_VERDICT_LINE = re.compile(r"^Urteil:[ \t]*(?P<value>\S*)", re.IGNORECASE)
_COMMENT_LINE = re.compile(r"^Kommentar:[ \t]*(?P<value>.*)$", re.IGNORECASE)
_VERDICTS = {"1": "1", "2": "2", "=": "=", "gleich": "="}


class TastingError(ValueError):
    """A tasting input that cannot be used as it is."""


@dataclass(frozen=True)
class Probe:
    id: str
    persona: str
    turns: tuple[str, ...]


@dataclass(frozen=True)
class Side:
    """One side of the tasting: ``classic`` or ``classic@main``."""

    ensemble: str
    ref: str | None = None

    @classmethod
    def parse(cls, spec: str) -> Side:
        ensemble, at, ref = spec.strip().partition("@")
        if not ensemble or (at and not ref):
            raise TastingError(f"cannot read side {spec!r}; expected ENSEMBLE[@REF]")
        return cls(ensemble=ensemble, ref=ref or None)

    @property
    def label(self) -> str:
        return f"{self.ensemble}@{self.ref}" if self.ref else self.ensemble


# --- probes -----------------------------------------------------------------


def load_probes(path: Path = DEFAULT_PROBES) -> tuple[Probe, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    probes: list[Probe] = []
    seen: set[str] = set()
    for raw in data.get("probes") or []:
        probe_id = str(raw.get("id") or "").strip()
        persona = str(raw.get("persona") or "").strip()
        turns = tuple(str(t).strip() for t in raw.get("turns") or [] if str(t).strip())
        if not probe_id or not persona or not turns:
            raise TastingError(f"{path}: every probe needs id, persona and turns")
        if not re.fullmatch(r"[\w-]+", probe_id):
            raise TastingError(f"{path}: probe id {probe_id!r} is not a plain word")
        if probe_id in seen:
            raise TastingError(f"{path}: probe id {probe_id!r} appears twice")
        seen.add(probe_id)
        probes.append(Probe(id=probe_id, persona=persona, turns=turns))
    if not probes:
        raise TastingError(f"{path}: no probes")
    return tuple(probes)


# --- one side ----------------------------------------------------------------


def materialize_ensemble(
    side: Side, dest: Path, *, seed: int | None, repo_root: Path = REPO_ROOT
) -> Path:
    """Copy the side's ensemble below ``dest`` and return its directory.

    A copy also for the working tree: the seed is written into the copy, never
    into the checked-in ensemble.
    """
    relative = Path("ensembles") / side.ensemble
    if side.ref:
        try:
            archive = subprocess.run(
                ["git", "archive", side.ref, relative.as_posix()],
                cwd=repo_root,
                capture_output=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.decode(errors="replace").strip()
            raise TastingError(f"{side.label}: {message}") from exc
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(dest, filter="data")
    else:
        source = repo_root / relative
        if source.is_dir():
            shutil.copytree(source, dest / relative)

    target = dest / relative
    base_file = target / "personas_base.yaml"
    if not base_file.is_file():
        raise TastingError(f"{side.label}: no personas_base.yaml in {relative}")
    if seed is not None:
        base = yaml.safe_load(base_file.read_text(encoding="utf-8"))
        for persona in base.get("personas") or []:
            persona["llm_options"] = {
                **(persona.get("llm_options") or {}),
                "seed": seed,
            }
        base_file.write_text(
            yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    return target


def collect_answers(
    probes: Sequence[Probe], reply_fn: ReplyFn, *, error_marker: str = ""
) -> list[dict[str, Any]]:
    """Play every probe, turn by turn; the side's own replies stay in the history.

    A failed turn ends that probe: the following turns would build on a
    conversation that did not happen.
    """
    results: list[dict[str, Any]] = []
    for probe in probes:
        messages: list[dict[str, str]] = []
        turns: list[dict[str, str]] = []
        error = ""
        for question in probe.turns:
            messages.append({"role": "user", "content": question})
            try:
                reply = reply_fn(probe.persona, list(messages)).strip()
            except Exception as exc:  # one broken probe must not end the tasting
                error = f"{type(exc).__name__}: {exc}"
                break
            if error_marker and reply.startswith(error_marker):
                # Ein Backend-Ausfall kommt als Text (#95) — keine Antwort.
                error = f"backend error — {reply}"
                break
            messages.append({"role": "assistant", "content": reply})
            turns.append({"user": question, "assistant": reply})
        results.append(
            {"id": probe.id, "persona": probe.persona, "turns": turns, "error": error}
        )
    return results


# --- sheet -------------------------------------------------------------------


def _by_id(side: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in side.get("probes") or []}


def _conversation(probe: dict[str, Any]) -> str:
    persona = probe["persona"]
    turns = probe["turns"]
    if len(turns) == 1:
        return turns[0]["assistant"]
    parts = []
    for turn in turns:
        parts.append(f"> **Du:** {turn['user']}\n\n**{persona}:** {turn['assistant']}")
    return "\n\n".join(parts)


def build_sheet(
    side_a: dict[str, Any], side_b: dict[str, Any], rng: random.Random
) -> tuple[str, dict[str, Any]]:
    """Return the blind sheet (Markdown) and the key that resolves it."""
    a_probes, b_probes = _by_id(side_a), _by_id(side_b)
    if list(a_probes) != list(b_probes):
        raise TastingError(
            "the two sides answered different probes — run both with the same probe file"
        )
    usable = [
        pid
        for pid in a_probes
        if not a_probes[pid]["error"] and not b_probes[pid]["error"]
    ]
    skipped = [pid for pid in a_probes if pid not in usable]

    # Genau die Hälfte jeder Richtung: sonst verrät die Position die Seite.
    swapped = [i < len(usable) // 2 for i in range(len(usable))]
    rng.shuffle(swapped)

    lines = [
        f"# Blindverkostung {datetime.now():%Y-%m-%d}",
        "",
        (
            "Pro Probe: welche Seite schmeckt besser? Hinter **Urteil:** `1`, `2` "
            "oder `=` eintragen, ein Kommentar darf dazu. Auswerten mit "
            "`python scripts/blind_tasting.py tally <ordner>`."
        ),
        "",
        "Erst nach dem Urteil in `schluessel.json` schauen.",
    ]
    order: dict[str, dict[str, str]] = {}
    for number, (pid, swap) in enumerate(zip(usable, swapped, strict=True), start=1):
        first, second = (
            (b_probes[pid], a_probes[pid]) if swap else (a_probes[pid], b_probes[pid])
        )
        order[pid] = {"1": "b" if swap else "a", "2": "a" if swap else "b"}
        probe = a_probes[pid]
        question = probe["turns"][0]["user"] if len(probe["turns"]) == 1 else None
        lines += ["", "---", "", f"<!-- probe: {pid} -->"]
        lines += [f"## {number}. {probe['persona']} — {pid}", ""]
        if question:
            lines += [f"> {question}", ""]
        lines += ["### Seite 1", "", _conversation(first), ""]
        lines += ["### Seite 2", "", _conversation(second), ""]
        lines += ["Urteil: ", "", "Kommentar: "]

    key = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "sides": {"a": _side_meta(side_a), "b": _side_meta(side_b)},
        "order": order,
        "skipped": {
            pid: a_probes[pid]["error"] or b_probes[pid]["error"] for pid in skipped
        },
    }
    return "\n".join(lines) + "\n", key


def _side_meta(side: dict[str, Any]) -> dict[str, Any]:
    keys = ("label", "model", "seed", "commit", "warnings")
    return {k: side.get(k) for k in keys}


# --- tally -------------------------------------------------------------------


@dataclass
class Verdict:
    probe_id: str
    value: str  # "1", "2", "=" or "" (not judged)
    comment: str = ""


def read_verdicts(sheet: str) -> list[Verdict]:
    verdicts: list[Verdict] = []
    current: Verdict | None = None
    for line in sheet.splitlines():
        if marker := _PROBE_MARKER.match(line):
            current = Verdict(probe_id=marker["id"], value="")
            verdicts.append(current)
        elif current is None:
            continue
        elif verdict := _VERDICT_LINE.match(line):
            raw = verdict["value"].strip().lower()
            if raw and raw not in _VERDICTS:
                raise TastingError(
                    f"{current.probe_id}: verdict {raw!r} — expected 1, 2 or ="
                )
            current.value = _VERDICTS.get(raw, "")
        elif comment := _COMMENT_LINE.match(line):
            current.comment = comment["value"].strip()
    return verdicts


@dataclass
class Tally:
    labels: dict[str, str]
    rows: dict[str, dict[str, int]] = field(default_factory=dict)
    comments: list[tuple[str, str, str]] = field(default_factory=list)

    def total(self) -> dict[str, int]:
        out = {"a": 0, "b": 0, "=": 0, "": 0}
        for row in self.rows.values():
            for k, v in row.items():
                out[k] += v
        return out


def tally(sheet: str, key: dict[str, Any], personas: dict[str, str]) -> Tally:
    """Resolve the verdicts with the key. ``personas`` maps probe id → persona."""
    labels = {s: str(key["sides"][s]["label"]) for s in ("a", "b")}
    result = Tally(labels=labels)
    for verdict in read_verdicts(sheet):
        order = key["order"].get(verdict.probe_id)
        if order is None:
            raise TastingError(f"{verdict.probe_id}: not in the key — wrong folder?")
        winner = order[verdict.value] if verdict.value in ("1", "2") else verdict.value
        persona = personas.get(verdict.probe_id, "?")
        row = result.rows.setdefault(persona, {"a": 0, "b": 0, "=": 0, "": 0})
        row[winner] += 1
        if verdict.comment:
            side = labels[winner] if winner in ("a", "b") else "gleich"
            result.comments.append((verdict.probe_id, side, verdict.comment))
    return result


def format_tally(result: Tally) -> str:
    a, b = result.labels["a"], result.labels["b"]
    lines = [
        f"| Persona | {a} | {b} | gleich | offen |",
        "|---|---|---|---|---|",
    ]
    for persona, row in result.rows.items():
        lines.append(
            f"| {persona} | {row['a']} | {row['b']} | {row['=']} | {row['']} |"
        )
    t = result.total()
    lines.append(
        f"| **gesamt** | **{t['a']}** | **{t['b']}** | **{t['=']}** | {t['']} |"
    )
    if result.comments:
        lines += ["", "Kommentare:", ""]
        lines += [
            f"- `{pid}` (Urteil: {side}): {text}" for pid, side, text in result.comments
        ]
    return "\n".join(lines) + "\n"


# --- CLI ---------------------------------------------------------------------


@dataclass
class _Warnings:
    """What `ensure_wiki_proxy` writes into — an `EvalRun` would do, too."""

    warnings: list[str] = field(default_factory=list)


def _git_commit(ref: str | None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", ref or "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = out.stdout.strip()
    if ref is None:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "ensembles"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        commit += "+changes" if dirty else ""
    return commit


def _answer_command(args: argparse.Namespace) -> int:
    from config.config_singleton import Config
    from core.streaming_provider import LLM_ERROR_MESSAGE

    from evals.cli import ensure_wiki_proxy

    side = Side.parse(args.side)
    probes = load_probes(Path(args.probes))
    cfg = Config(path=str(Path(args.config or "config.yaml").resolve()))
    if args.model:
        cfg.override("core", {"model_name": args.model})
    # Eine Verkostung ist kein Gespräch — wie beim Eval-Lauf nicht aufzeichnen.
    setattr(cfg, "storage", {**(getattr(cfg, "storage", None) or {}), "enabled": False})

    with tempfile.TemporaryDirectory(prefix="tasting_") as tmp:
        ensemble_dir = materialize_ensemble(side, Path(tmp), seed=args.seed)
        # Ein absoluter Pfad als Ensemble-Name: `ensembles/ / "/tmp/…"` ergibt
        # den absoluten Pfad, so liegt die Kopie nie im Repo.
        cfg.ensemble = str(ensemble_dir)
        notes = _Warnings()
        ensure_wiki_proxy(cfg, notes)

        from core.factory import AppFactory

        provider = AppFactory().get_one_shot_provider()

        def _reply(persona: str, messages: list[dict[str, str]]) -> str:
            return "".join(provider.stream_messages(messages, persona))

        answers = collect_answers(probes, _reply, error_marker=LLM_ERROR_MESSAGE)

    side_data = {
        "label": side.label,
        "model": str(cfg.core.get("model_name", "")),
        "seed": args.seed,
        "commit": _git_commit(side.ref),
        "warnings": notes.warnings,
        "probes": answers,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(side_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    errors = [p["id"] for p in answers if p["error"]]
    print(f"{side.label}: {len(answers) - len(errors)}/{len(answers)} Proben → {out}")
    for pid in errors:
        print(f"  FEHLER {pid}: {next(p['error'] for p in answers if p['id'] == pid)}")
    return 1 if errors else 0


def _sheet_command(args: argparse.Namespace) -> int:
    side_a = json.loads(Path(args.side_a).read_text(encoding="utf-8"))
    side_b = json.loads(Path(args.side_b).read_text(encoding="utf-8"))
    sheet, key = build_sheet(side_a, side_b, random.Random(args.shuffle_seed))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / SHEET_NAME).write_text(sheet, encoding="utf-8")
    key["personas"] = {p["id"]: p["persona"] for p in side_a["probes"]}
    (out / KEY_NAME).write_text(
        json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(key['order'])} Proben → {out / SHEET_NAME} (Schlüssel: {KEY_NAME})")
    for pid, error in key["skipped"].items():
        print(f"  ausgelassen {pid}: {error}")
    for s in ("a", "b"):
        for warning in key["sides"][s].get("warnings") or []:
            print(f"  WARNUNG {key['sides'][s]['label']}: {warning}")
    return 0


def _tally_command(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    key = json.loads((folder / KEY_NAME).read_text(encoding="utf-8"))
    sheet = (folder / SHEET_NAME).read_text(encoding="utf-8")
    report = format_tally(tally(sheet, key, key.get("personas") or {}))
    (folder / TALLY_NAME).write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


def _run_command(args: argparse.Namespace) -> int:
    """Both sides, each in its own process, then the sheet."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    script = REPO_ROOT / "scripts" / "blind_tasting.py"
    status = 0
    for name, spec, model in (("a", args.a, args.model_a), ("b", args.b, args.model_b)):
        cmd = [
            sys.executable,
            str(script),
            "answer",
            spec,
            "-o",
            str(out / f"seite_{name}.json"),
        ]
        cmd += ["--probes", args.probes, "--seed", str(args.seed)]
        cmd += ["--model", model] if model else []
        cmd += ["--config", args.config] if args.config else []
        status |= subprocess.run(cmd, check=False).returncode
    if not all((out / f"seite_{n}.json").is_file() for n in ("a", "b")):
        return 1
    sheet_args = argparse.Namespace(
        side_a=str(out / "seite_a.json"),
        side_b=str(out / "seite_b.json"),
        out=str(out),
        shuffle_seed=args.shuffle_seed,
    )
    return _sheet_command(sheet_args) or status


def _seed(value: str) -> int | None:
    return None if value.lower() == "none" else int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blind_tasting.py",
        description="Blind tasting of two ensemble states (#99).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--probes", default=str(DEFAULT_PROBES))
        p.add_argument(
            "--seed", type=_seed, default=0, help="llm_options.seed; 'none' = off"
        )
        p.add_argument("--config", default=None)

    run = sub.add_parser("run", help="both sides and the sheet in one go")
    run.add_argument("a", help="side A, e.g. classic@main")
    run.add_argument("b", help="side B, e.g. classic (working tree)")
    run.add_argument("-o", "--out", required=True)
    run.add_argument("--model-a", default=None)
    run.add_argument("--model-b", default=None)
    run.add_argument("--shuffle-seed", type=int, default=None)
    _common(run)
    run.set_defaults(func=_run_command)

    answer = sub.add_parser("answer", help="one side answers every probe")
    answer.add_argument("side", help="ENSEMBLE or ENSEMBLE@REF")
    answer.add_argument("-o", "--out", required=True)
    answer.add_argument("--model", default=None)
    _common(answer)
    answer.set_defaults(func=_answer_command)

    sheet = sub.add_parser("sheet", help="blind sheet from two answer files")
    sheet.add_argument("side_a")
    sheet.add_argument("side_b")
    sheet.add_argument("-o", "--out", required=True)
    sheet.add_argument("--shuffle-seed", type=int, default=None)
    sheet.set_defaults(func=_sheet_command)

    count = sub.add_parser("tally", help="count the verdicts in a judged sheet")
    count.add_argument("folder")
    count.set_defaults(func=_tally_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except TastingError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
