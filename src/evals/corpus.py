"""Loading and strict validation of the YAML corpora under ``evals/``.

Strict on purpose: an unknown key is almost always a typo, and a corpus that
silently ignores half its expectations is worse than no corpus at all. Every
error names the file and the case id so a broken corpus is fixable without
reading this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Anchored on the project root so the corpora are found no matter the cwd.
EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"

_CHECK_KEYS = {"must_match", "must_not_match", "max_chars", "min_chars"}
_PERSONA_CASE_KEYS = {"id", "question", "expect_traits", "checks", "note"}
_BEHAVIOUR_CASE_KEYS = _PERSONA_CASE_KEYS
_GUARD_CASE_KEYS = {"id", "stage", "text", "expect", "note", "known_gap"}
_GUARD_EXPECT_KEYS = {"ok", "reason", "rule", "blocked", "masked", "injected"}
# "context" ist der dritte Kanal: abgerufener Fremdtext (Wikipedia-Snippet,
# RSS-Meldung), der als system-Nachricht in den Prompt geht. Er hat eigene
# Regeln — nur prompt_injection und wrongdoing verwerfen, PII ist erlaubt —
# und braucht deshalb eine eigene Stufe, statt in "input" mitgemeint zu sein.
_GUARD_STAGES = {"input", "output", "context"}

# Placeholders substituted into check patterns at run time. Needed for the
# three-timestamp behaviour eval (#19), where the expected answer depends on
# the day the eval runs.
_PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


class CorpusError(ValueError):
    """Raised when a corpus file is missing fields, malformed or has typos."""


@dataclass(frozen=True)
class Checks:
    """Deterministic expectations that need no judge."""

    must_match: tuple[str, ...] = ()
    must_not_match: tuple[str, ...] = ()
    max_chars: int | None = None
    min_chars: int | None = None

    def is_empty(self) -> bool:
        return not (
            self.must_match
            or self.must_not_match
            or self.max_chars is not None
            or self.min_chars is not None
        )


@dataclass(frozen=True)
class PersonaCase:
    id: str
    question: str
    expect_traits: tuple[str, ...]
    checks: Checks
    source: str


@dataclass(frozen=True)
class PersonaCorpus:
    persona: str
    cases: tuple[PersonaCase, ...]
    source: str


@dataclass(frozen=True)
class BehaviourCorpus:
    """Persona-independent behaviour probes (e.g. the three timestamps)."""

    name: str
    persona: str
    description: str
    cases: tuple[PersonaCase, ...]
    source: str


@dataclass(frozen=True)
class KarlCase:
    """A history to compress plus expectations about the summary (#12)."""

    id: str
    history: tuple[dict[str, str], ...]
    expect_traits: tuple[str, ...]
    checks: Checks
    source: str


@dataclass(frozen=True)
class KarlCorpus:
    name: str
    description: str
    cases: tuple[KarlCase, ...]
    source: str


@dataclass(frozen=True)
class GuardCase:
    id: str
    stage: str  # "input" | "output"
    text: str
    expect: dict[str, Any]
    source: str
    # A documented weakness: the case states what the guard *should* do, but
    # today it does not. Reported, never asserted — so the corpus can stay
    # honest about gaps instead of pretending they do not exist.
    known_gap: bool = False
    note: str = ""


@dataclass(frozen=True)
class GuardCorpus:
    description: str
    cases: tuple[GuardCase, ...]
    source: str


# ---- Helpers --------------------------------------------------------------


def _read_yaml(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise CorpusError(f"{path.name}: invalid YAML ({exc}).") from exc
    if not isinstance(data, dict):
        raise CorpusError(f"{path.name}: top level must be a mapping.")
    return data


def _reject_unknown(where: str, data: dict, allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CorpusError(
            f"{where}: unknown key(s) {', '.join(unknown)} "
            f"(allowed: {', '.join(sorted(allowed))})."
        )


def _require_str(where: str, data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CorpusError(f"{where}: '{key}' must be a non-empty string.")
    return value.strip()


def _str_tuple(where: str, value: Any, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list):
        raise CorpusError(f"{where}: '{key}' must be a list of strings.")
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CorpusError(f"{where}: '{key}' entries must be non-empty strings.")
        out.append(item.strip())
    return tuple(out)


def _positive_int_or_none(where: str, data: dict, key: str) -> int | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CorpusError(f"{where}: '{key}' must be a positive integer.")
    return value


def _validate_regex(where: str, patterns: tuple[str, ...], key: str) -> None:
    """Compile patterns eagerly so a broken regex fails at load, not mid-run.

    Placeholders like ``{today_iso}`` are replaced by a harmless token first —
    they are filled in at run time, but the rest of the pattern must be valid.
    """
    for pattern in patterns:
        probe = _PLACEHOLDER_PATTERN.sub("x", pattern)
        try:
            re.compile(probe)
        except re.error as exc:
            raise CorpusError(
                f"{where}: '{key}' entry {pattern!r} is not a valid regex ({exc})."
            ) from exc


def _parse_checks(where: str, raw: Any) -> Checks:
    if raw is None:
        return Checks()
    if not isinstance(raw, dict):
        raise CorpusError(f"{where}: 'checks' must be a mapping.")
    _reject_unknown(f"{where} checks", raw, _CHECK_KEYS)

    must_match = _str_tuple(where, raw.get("must_match"), "must_match")
    must_not_match = _str_tuple(where, raw.get("must_not_match"), "must_not_match")
    _validate_regex(where, must_match, "must_match")
    _validate_regex(where, must_not_match, "must_not_match")

    max_chars = _positive_int_or_none(where, raw, "max_chars")
    min_chars = _positive_int_or_none(where, raw, "min_chars")
    if max_chars is not None and min_chars is not None and min_chars > max_chars:
        raise CorpusError(f"{where}: 'min_chars' must not exceed 'max_chars'.")

    return Checks(
        must_match=must_match,
        must_not_match=must_not_match,
        max_chars=max_chars,
        min_chars=min_chars,
    )


def _parse_question_cases(
    path: Path, raw_cases: Any, allowed_keys: set[str]
) -> tuple[PersonaCase, ...]:
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CorpusError(f"{path.name}: 'cases' must be a non-empty list.")

    cases: list[PersonaCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise CorpusError(f"{path.name}: case #{index + 1} must be a mapping.")
        where = f"{path.name}: case #{index + 1}"
        _reject_unknown(where, raw, allowed_keys)

        case_id = _require_str(where, raw, "id")
        if case_id in seen:
            raise CorpusError(f"{path.name}: duplicate case id {case_id!r}.")
        seen.add(case_id)

        where = f"{path.name}:{case_id}"
        question = _require_str(where, raw, "question")
        traits = _str_tuple(where, raw.get("expect_traits"), "expect_traits")
        checks = _parse_checks(where, raw.get("checks"))

        # A case that expects nothing would always pass and give false comfort.
        if not traits and checks.is_empty():
            raise CorpusError(
                f"{where}: needs at least one 'expect_traits' entry or one check."
            )

        cases.append(
            PersonaCase(
                id=case_id,
                question=question,
                expect_traits=traits,
                checks=checks,
                source=path.name,
            )
        )
    return tuple(cases)


# ---- Public loaders -------------------------------------------------------


def load_persona_corpus(path: Path) -> PersonaCorpus:
    data = _read_yaml(path)
    _reject_unknown(path.name, data, {"persona", "description", "cases"})
    persona = _require_str(path.name, data, "persona")
    cases = _parse_question_cases(path, data.get("cases"), _PERSONA_CASE_KEYS)
    return PersonaCorpus(persona=persona, cases=cases, source=path.name)


def load_persona_corpora(base_dir: Path | None = None) -> tuple[PersonaCorpus, ...]:
    directory = (base_dir or EVALS_DIR) / "personas"
    if not directory.is_dir():
        raise CorpusError(f"Persona corpus directory not found: {directory}")
    corpora = [load_persona_corpus(p) for p in sorted(directory.glob("*.yaml"))]
    if not corpora:
        raise CorpusError(f"No persona corpora (*.yaml) found in {directory}")

    personas = [c.persona for c in corpora]
    duplicates = sorted({p for p in personas if personas.count(p) > 1})
    if duplicates:
        raise CorpusError(
            f"Persona(s) {', '.join(duplicates)} covered by more than one corpus file."
        )
    return tuple(corpora)


def load_behaviour_corpus(path: Path) -> BehaviourCorpus:
    data = _read_yaml(path)
    _reject_unknown(path.name, data, {"name", "persona", "description", "cases"})
    name = _require_str(path.name, data, "name")
    persona = _require_str(path.name, data, "persona")
    description = str(data.get("description") or "").strip()
    cases = _parse_question_cases(path, data.get("cases"), _BEHAVIOUR_CASE_KEYS)
    return BehaviourCorpus(
        name=name,
        persona=persona,
        description=description,
        cases=cases,
        source=path.name,
    )


def load_behaviour_corpora(base_dir: Path | None = None) -> tuple[BehaviourCorpus, ...]:
    directory = (base_dir or EVALS_DIR) / "behaviour"
    if not directory.is_dir():
        return ()
    return tuple(load_behaviour_corpus(p) for p in sorted(directory.glob("*.yaml")))


def load_karl_corpus(base_dir: Path | None = None) -> KarlCorpus | None:
    """Load the Karl summary corpus, or None when the file is absent."""
    path = (base_dir or EVALS_DIR) / "karl_summary.yaml"
    if not path.is_file():
        return None

    data = _read_yaml(path)
    _reject_unknown(path.name, data, {"name", "description", "cases"})
    name = _require_str(path.name, data, "name")
    description = str(data.get("description") or "").strip()

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CorpusError(f"{path.name}: 'cases' must be a non-empty list.")

    cases: list[KarlCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise CorpusError(f"{path.name}: case #{index + 1} must be a mapping.")
        where = f"{path.name}: case #{index + 1}"
        _reject_unknown(
            where, raw, {"id", "history", "expect_traits", "checks", "note"}
        )

        case_id = _require_str(where, raw, "id")
        if case_id in seen:
            raise CorpusError(f"{path.name}: duplicate case id {case_id!r}.")
        seen.add(case_id)

        where = f"{path.name}:{case_id}"
        raw_history = raw.get("history")
        if not isinstance(raw_history, list) or not raw_history:
            raise CorpusError(f"{where}: 'history' must be a non-empty list.")
        history: list[dict[str, str]] = []
        for message in raw_history:
            if not isinstance(message, dict):
                raise CorpusError(f"{where}: history entries must be mappings.")
            _reject_unknown(f"{where} history", message, {"role", "content"})
            role = _require_str(f"{where} history", message, "role")
            if role not in {"user", "assistant", "system"}:
                raise CorpusError(
                    f"{where}: history role {role!r} must be user, assistant or system."
                )
            content = _require_str(f"{where} history", message, "content")
            history.append({"role": role, "content": content})

        traits = _str_tuple(where, raw.get("expect_traits"), "expect_traits")
        checks = _parse_checks(where, raw.get("checks"))
        if not traits and checks.is_empty():
            raise CorpusError(
                f"{where}: needs at least one 'expect_traits' entry or one check."
            )

        cases.append(
            KarlCase(
                id=case_id,
                history=tuple(history),
                expect_traits=traits,
                checks=checks,
                source=path.name,
            )
        )

    return KarlCorpus(
        name=name, description=description, cases=tuple(cases), source=path.name
    )


def load_guard_corpus(base_dir: Path | None = None) -> GuardCorpus:
    path = (base_dir or EVALS_DIR) / "guard_redteam.yaml"
    if not path.is_file():
        raise CorpusError(f"Guard corpus not found: {path}")

    data = _read_yaml(path)
    _reject_unknown(path.name, data, {"description", "cases"})
    description = str(data.get("description") or "").strip()

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CorpusError(f"{path.name}: 'cases' must be a non-empty list.")

    cases: list[GuardCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise CorpusError(f"{path.name}: case #{index + 1} must be a mapping.")
        where = f"{path.name}: case #{index + 1}"
        _reject_unknown(where, raw, _GUARD_CASE_KEYS)

        case_id = _require_str(where, raw, "id")
        if case_id in seen:
            raise CorpusError(f"{path.name}: duplicate case id {case_id!r}.")
        seen.add(case_id)

        where = f"{path.name}:{case_id}"
        stage = _require_str(where, raw, "stage")
        if stage not in _GUARD_STAGES:
            raise CorpusError(
                f"{where}: 'stage' must be one of {', '.join(sorted(_GUARD_STAGES))}."
            )
        text = _require_str(where, raw, "text")

        expect = raw.get("expect")
        if not isinstance(expect, dict) or not expect:
            raise CorpusError(f"{where}: 'expect' must be a non-empty mapping.")
        _reject_unknown(f"{where} expect", expect, _GUARD_EXPECT_KEYS)
        for key, value in expect.items():
            if key in ("reason", "rule"):
                if not isinstance(value, str) or not value.strip():
                    raise CorpusError(f"{where}: '{key}' must be a non-empty string.")
            elif not isinstance(value, bool):
                raise CorpusError(f"{where}: '{key}' must be a boolean.")
        # `rule` haelt fest, *welche* Regel den Fall fangen soll (#62). Ein Fall,
        # der aus dem falschen Grund gruen ist, sieht sonst aus wie ein Erfolg —
        # und die eigentlich gemeinte Regel darf verrotten, ohne dass es auffaellt.
        if "rule" in expect and expect.get("reason") in (None, "ok"):
            raise CorpusError(
                f"{where}: 'rule' only makes sense together with a blocking "
                "'reason' — a case that passes cleanly has no rule."
            )
        if stage != "output" and ("blocked" in expect or "masked" in expect):
            raise CorpusError(
                f"{where}: 'blocked'/'masked' apply to output cases only "
                "(input cases use 'ok' and 'reason')."
            )
        if stage == "context" and "injected" not in expect:
            raise CorpusError(
                f"{where}: a context case must say whether the text ends up in "
                "the prompt ('injected: true|false')."
            )
        if stage != "context" and "injected" in expect:
            raise CorpusError(f"{where}: 'injected' applies to context cases only.")

        known_gap = raw.get("known_gap", False)
        if not isinstance(known_gap, bool):
            raise CorpusError(f"{where}: 'known_gap' must be a boolean.")
        note = str(raw.get("note") or "").strip()
        if known_gap and not note:
            raise CorpusError(
                f"{where}: a case marked 'known_gap' needs a 'note' explaining "
                "why the gap is accepted."
            )

        cases.append(
            GuardCase(
                id=case_id,
                stage=stage,
                text=text,
                expect=dict(expect),
                source=path.name,
                known_gap=known_gap,
                note=note,
            )
        )

    return GuardCorpus(description=description, cases=tuple(cases), source=path.name)
