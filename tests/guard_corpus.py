"""Der Guard-Red-Team-Korpus: Lader und Auswertung (#18, #41, #62).

Bis 2026-11-26 lag das in `yulyen_ai.evals` und wurde von der Eval-Suite
mitbenutzt. Die Suite ist ins Lab umgezogen; der Korpus blieb, weil er kein
Modell misst, sondern den Guard prüft — er ist ein Regressionstest wie jeder
andere und gehört neben `tests/test_guard_redteam.py`.

Streng mit Absicht: ein unbekannter Key ist fast immer ein Tippfehler, und ein
Fall, der still die Hälfte seiner Erwartungen verliert, ist schlimmer als kein
Fall.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yulyen_ai.security.tinyguard import context_verdict

HERE = Path(__file__).resolve().parent


class CorpusError(ValueError):
    """Der Korpus ist kaputt: fehlende Felder, falsche Typen, Tippfehler."""


_GUARD_CASE_KEYS = {"id", "stage", "text", "expect", "note", "known_gap"}
_GUARD_EXPECT_KEYS = {"ok", "reason", "rule", "blocked", "masked", "injected"}
# "context" ist der dritte Kanal: abgerufener Fremdtext (Wikipedia-Snippet,
# RSS-Meldung), der als system-Nachricht in den Prompt geht. Er hat eigene
# Regeln — nur prompt_injection und wrongdoing verwerfen, PII ist erlaubt —
# und braucht deshalb eine eigene Stufe, statt in "input" mitgemeint zu sein.
_GUARD_STAGES = {"input", "output", "context"}


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


def load_guard_corpus(base_dir: Path | None = None) -> GuardCorpus:
    path = (base_dir or HERE) / "guard_redteam.yaml"
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


@dataclass(frozen=True)
class GuardOutcome:
    case_id: str
    stage: str
    failures: tuple[str, ...]
    observed: dict
    known_gap: bool = False
    note: str = ""

    @property
    def passed(self) -> bool:
        return not self.failures


def evaluate_guard_case(guard, case: GuardCase) -> GuardOutcome:
    """Check one corpus case against ``guard``.

    The guard carries session state (the wrongdoing lock), so callers must
    hand in a fresh instance per case — otherwise a lock armed by an earlier
    case would block later, unrelated ones.
    """
    expect = case.expect
    observed: dict = {}
    failures: list[str] = []

    if case.stage == "input":
        result = guard.check_input(case.text)
        observed["ok"] = result["ok"]
        observed["reason"] = result["reason"]
        observed["rule"] = result.get("rule")
        observed["detail"] = result.get("detail")
    elif case.stage == "context":
        # Abgerufener Fremdtext: die Frage ist nicht "blockiert der Guard das",
        # sondern "landet es im Prompt". Andere Regel als beim Eingang — ein
        # Artikel darf PII enthalten, eine Injection-Anweisung nicht.
        # `context_verdict` statt `context_rejection`: es trägt den Regelnamen
        # mit. Den Wrongdoing-Lock berührt die Kontextprüfung nicht.
        verdict = context_verdict(guard, case.text)
        observed["injected"] = verdict is None
        observed["reason"] = verdict["reason"] if verdict else "ok"
        observed["rule"] = verdict.get("rule") if verdict else None
    else:
        if "ok" in expect or "reason" in expect:
            result = guard.check_output(case.text)
            observed["ok"] = result["ok"]
            observed["reason"] = result["reason"]
            observed["rule"] = result.get("rule")
            observed["detail"] = result.get("detail")
        if "blocked" in expect or "masked" in expect:
            processed = guard.process_output(case.text)
            observed["blocked"] = processed["blocked"]
            observed["masked"] = processed["masked"]
            observed["text"] = processed["text"]

    for key, expected in expect.items():
        if key not in observed:
            failures.append(f"{key}: nothing observed for this stage")
            continue
        actual = observed[key]
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")

    return GuardOutcome(
        case_id=case.id,
        stage=case.stage,
        failures=tuple(failures),
        observed=observed,
        known_gap=case.known_gap,
        note=case.note,
    )
