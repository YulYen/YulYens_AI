"""CLI der Stoppuhr: ``python scripts/run_bench.py -e classic``.

Getrennt von der Eval-Suite (#41), obwohl beides Batch-Jobs sind: dort geht es
um Antwort*qualität* und der Lauf braucht einen Judge, hier um Antwort*zeit*
und der Lauf muss so wenig wie möglich nebenher tun. Zwei Werkzeuge, zwei
Fragen.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from version import __version__

from bench.drivers import HttpDriver, InProcessDriver
from bench.harness import (
    DEFAULT_REPEATS,
    DEFAULT_WARMUP,
    BenchAborted,
    BenchRun,
    Question,
    run_bench,
)
from bench.questions import DEFAULT_QUESTIONS, load_questions
from bench.report import render_console, render_csv, render_markdown, sample_line

DEFAULT_OUT_DIR = "logs/bench"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench",
        description=(
            "Misst Antwortzeiten des Streaming-Pfads: Zeit bis zum ersten "
            "ausgelieferten Zeichen und Durchsatz (#42)."
        ),
    )
    parser.add_argument("-c", "--config", help="Pfad zur config.yaml.")
    parser.add_argument(
        "-e", "--ensemble", help="Persona-Ensemble (sonst der Wert aus der Config)."
    )
    parser.add_argument(
        "--personas",
        help=(
            "Kommaliste, z. B. 'PETER,DORIS'. Ohne Angabe die Persona mit der "
            "niedrigsten Temperatur — ihre Antwortlänge schwankt am wenigsten."
        ),
    )
    parser.add_argument(
        "--questions",
        help="Eigener Fragensatz: eine Frage je Zeile, '#' ist Kommentar.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help=f"Messrunden je Frage (Default {DEFAULT_REPEATS}).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help=(
            f"Aufwärmläufe je Persona vor der Messung (Default {DEFAULT_WARMUP}). "
            "Sie werden ausgewiesen, zählen aber nicht in die Mediane."
        ),
    )
    parser.add_argument(
        "--model",
        help="Überschreibt core.model_name — der Sinn der ganzen Übung.",
    )
    parser.add_argument(
        "--backend",
        choices=("ollama", "dummy"),
        help=(
            "Überschreibt core.backend. 'dummy' braucht kein Modell und prüft "
            "nur, ob der Harness läuft — die Zahlen bedeuten dann nichts."
        ),
    )
    parser.add_argument(
        "--holdback",
        type=int,
        help=(
            "Überschreibt security.stream_holdback_chars. Damit lässt sich die "
            "Tabelle aus #51 nachfahren, ohne die Config anzufassen."
        ),
    )
    parser.add_argument(
        "--api-url",
        help=(
            "Statt in-process gegen einen laufenden Server messen, z. B. "
            "http://127.0.0.1:8013/v1 — misst dann den vollen Pfad inkl. Wiki."
        ),
    )
    parser.add_argument(
        "--api-key",
        help="Schlüssel für --api-url (api.openai_compatible.api_key).",
    )
    parser.add_argument(
        "--out",
        help=f"Zielverzeichnis für report.md / report.csv (Default {DEFAULT_OUT_DIR}).",
    )
    return parser


def _quietest_persona(names: list[str]) -> str:
    """Die Persona mit der niedrigsten Temperatur.

    Als Default gewählt, weil sie über mehrere Runden die ähnlichsten Antworten
    liefert — und die Antwortlänge ist der größte Einzeleinfluss auf die
    Gesamtdauer. Abgeleitet statt fest verdrahtet, damit der Default auch für
    ein fremdes Ensemble gilt.
    """
    from config import personas

    def _temperature(name: str) -> float:
        options = personas.get_options(name) or {}
        try:
            return float(options.get("temperature", 1.0))
        except (TypeError, ValueError):
            return 1.0

    return min(names, key=lambda name: (_temperature(name), names.index(name)))


def _resolve_personas(parser: argparse.ArgumentParser, raw: str | None) -> list[str]:
    from config.personas import get_all_persona_names

    known = get_all_persona_names()
    if not known:
        parser.error("Das Ensemble enthält keine Persona.")
    if not raw:
        return [_quietest_persona(known)]

    lookup = {name.lower(): name for name in known}
    wanted: list[str] = []
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in lookup:
            parser.error(f"Unbekannte Persona '{part.strip()}'. Bekannt: {known}")
        wanted.append(lookup[key])
    if not wanted:
        parser.error("--personas ist leer.")
    return wanted


def _guard_preflight(
    driver: InProcessDriver, personas: list[str], questions: tuple[Question, ...]
) -> list[str]:
    """Prüft vorab, ob der Guard eine der Fragen abweist.

    Eine abgewiesene Frage kommt als kurze Absage zurück — in Millisekunden und
    ohne Modell. Ohne diese Vorabprüfung stünde sie als beeindruckend schnelle
    Messung im Report. Der Fall ist unwahrscheinlich für den mitgelieferten
    Fragensatz und wahrscheinlich für einen eigenen, und genau dort fällt er
    sonst niemandem auf.
    """
    warnings: list[str] = []
    for persona in personas:
        guard = driver.guard(persona)
        if guard is None:
            continue
        for question in questions:
            result = guard.check_input(question.text)
            if not result.get("ok", True):
                warnings.append(
                    f"Der Guard weist `{question.id}` ab "
                    f"(Regel `{result.get('rule')}`) — diese Frage misst die "
                    f"Absage, nicht das Modell."
                )
        break  # der Guard ist für alle Personas gleich konfiguriert
    return warnings


def _holdback_note(sec_cfg: dict) -> str:
    """Der Holdback-Eintrag der Kopfzeile — Zahl plus die Frage, ob sie wirkt.

    Der Moderator setzt den Holdback selbst auf 0, sobald ausgangsseitig nichts
    geprüft wird (`_output_checks_active`). Zwei Läufe, die sich nur darin
    unterscheiden, unterscheiden sich in der wahrgenommenen Latenz drastisch —
    und der Zahlenwert allein verriete es nicht.
    """
    holdback = sec_cfg.get("stream_holdback_chars")
    note = "Voreinstellung" if holdback is None else str(holdback)
    output_checks = bool(sec_cfg.get("enabled", True)) and (
        bool(sec_cfg.get("pii_protection", True))
        or bool(sec_cfg.get("output_blocklist", True))
    )
    if not output_checks:
        note += " (wirkungslos: keine Ausgangsprüfung aktiv)"
    return note


def _settings(cfg, driver_mode: str) -> list[tuple[str, str]]:
    """Alles, was zwei Läufe unvergleichbar macht, wenn es sich unterscheidet."""
    core_cfg = dict(getattr(cfg, "core", {}) or {})
    sec_cfg = dict(getattr(cfg, "security", {}) or {})
    wiki_cfg = dict(getattr(cfg, "wiki", {}) or {})

    settings = [
        ("Stand", f"`{__version__}`"),
        ("Holdback", _holdback_note(sec_cfg)),
        ("num_ctx", str(_persona_num_ctx(cfg))),
        ("keep_alive", str(core_cfg.get("keep_alive", 600))),
        ("Guard", "an" if sec_cfg.get("enabled", True) else "aus"),
    ]
    if driver_mode == "in-process":
        settings.append(
            (
                "Wiki/RSS",
                f"nicht im Messpfad (Config: `{wiki_cfg.get('mode')}`)",
            )
        )
    else:
        settings.append(("Wiki/RSS", "was der laufende Server tut"))
    return settings


def _persona_num_ctx(cfg) -> str:
    """Das Kontextfenster, wie es in der Ensemble-YAML steht."""
    from config import personas

    sizes = set()
    for name in personas.get_all_persona_names():
        options = personas.get_options(name) or {}
        if "num_ctx" in options:
            sizes.add(str(options["num_ctx"]))
    return ", ".join(sorted(sizes)) if sizes else "—"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from config.config_singleton import Config

    cfg = Config(path=os.path.abspath(args.config or "config.yaml"))
    cfg.ensemble = args.ensemble or getattr(cfg, "ensemble", None)
    if not cfg.ensemble:
        parser.error(
            "Fehlender Parameter: --ensemble / -e "
            "(z. B. 'python scripts/run_bench.py -e classic')."
        )

    if args.model:
        cfg.override("core", {"model_name": args.model})
    if args.backend:
        cfg.override("core", {"backend": args.backend})
    if args.holdback is not None:
        cfg.override("security", {"stream_holdback_chars": args.holdback})
    # Die Stoppuhr zeichnet keine Gespräche auf: sie stellt dieselbe Frage
    # mehrfach und hätte in der Ablage nichts zu suchen. `stream()` schreibt
    # ohnehin nichts dorthin — das hier verhindert nur, dass der Lauf die
    # Datenbankdatei überhaupt anfasst.
    cfg.override("storage", {"enabled": False})

    if args.repeats < 1:
        parser.error("--repeats muss mindestens 1 sein.")
    if args.warmup < 0:
        parser.error("--warmup darf nicht negativ sein.")

    try:
        questions = (
            load_questions(args.questions) if args.questions else DEFAULT_QUESTIONS
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    personas = _resolve_personas(parser, args.personas)

    warnings: list[str] = []
    error_marker: str | None = None
    if args.api_url:
        driver: object = HttpDriver(args.api_url, args.api_key)
        backend = f"HTTP {args.api_url}"
    else:
        from core.factory import AppFactory
        from core.streaming_provider import LLM_ERROR_MESSAGE

        factory = AppFactory()
        driver = InProcessDriver(factory)
        error_marker = LLM_ERROR_MESSAGE
        backend = str(cfg.core.get("backend", "ollama"))
        if backend == "dummy":
            # Der Report sieht sonst aus wie jeder andere — mit Zahlen, die
            # nichts messen. Ein Wert ohne Herkunft wird geglaubt, und dieser
            # hier ist ein Selbsttest des Harness, kein Messergebnis.
            warnings.append(
                "Backend `dummy`: das Echo antwortet ohne Modell und in einem "
                "Stück. Dieser Lauf zeigt, dass der Harness funktioniert — die "
                "Zahlen darin bedeuten nichts."
            )
        warnings.extend(_guard_preflight(driver, personas, questions))

    if len(questions) == 1 and args.repeats > 1:
        warnings.append(
            "Nur eine Frage bei mehreren Runden: die Wiederholungen treffen "
            "denselben Prompt und damit den Prompt-Cache des Backends. Die "
            "zweite Runde ist dann schneller als die erste, ohne dass etwas "
            "schneller geworden wäre."
        )

    run = BenchRun(
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        mode=getattr(driver, "mode", "?"),
        backend=backend,
        model=str(cfg.core.get("model_name", "unknown")),
        repeats=args.repeats,
        warmup=args.warmup,
        settings=_settings(cfg, getattr(driver, "mode", "?")),
        warnings=warnings,
    )

    total = args.warmup * len(personas) + args.repeats * len(personas) * len(questions)
    print(
        f"{total} Messungen: {len(personas)} Persona(s) x {len(questions)} Frage(n) "
        f"x {args.repeats} Runde(n), Modell {run.model}"
    )

    try:
        run.samples = run_bench(
            driver,  # type: ignore[arg-type]
            personas,
            questions,
            repeats=args.repeats,
            warmup=args.warmup,
            error_marker=error_marker,
            on_sample=lambda sample: print(sample_line(sample), flush=True),
        )
    except BenchAborted as exc:
        print(f"\nAbgebrochen: {exc}", file=sys.stderr)
        print(
            "Die allererste Messung schlug fehl — das ist ein Aufbaufehler "
            "(Backend nicht erreichbar, Modell nicht geladen, falscher Port) "
            "und kein Messergebnis.",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130

    out_dir = Path(args.out or DEFAULT_OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render_markdown(run), encoding="utf-8")
    (out_dir / "report.csv").write_text(render_csv(run), encoding="utf-8")

    print()
    print(render_console(run))
    if run.errors:
        print(f"{len(run.errors)} Messung(en) fehlgeschlagen, siehe Report.")
    print(f"Report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":  # pragma: no cover - dünner CLI-Shim
    sys.exit(main())
