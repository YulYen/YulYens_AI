"""Deterministic checks on an answer — no LLM judge involved.

These carry the load for anything mechanically verifiable (a fact appears, a
length limit holds, a forbidden phrase stays absent). The judge is only asked
about things a regex cannot see, like whether DORIS actually sounded sarcastic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from evals.corpus import Checks

_PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")

_GERMAN_MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


@dataclass(frozen=True)
class CheckFailure:
    kind: str  # "must_match" | "must_not_match" | "max_chars" | "min_chars"
    detail: str


def placeholders(today: date | None = None) -> dict[str, str]:
    """Runtime values a corpus may reference as ``{name}`` inside patterns.

    Needed by the three-timestamp eval (#19): the expected answer depends on
    the day the eval runs, so the corpus cannot hardcode it.
    """
    day = today or date.today()
    return {
        "today_iso": day.isoformat(),
        "today_de": f"{day.day}. {_GERMAN_MONTHS[day.month - 1]} {day.year}",
        "day": str(day.day),
        "month_de": _GERMAN_MONTHS[day.month - 1],
        "year": str(day.year),
    }


def expand(pattern: str, values: dict[str, str]) -> str:
    """Replace ``{name}`` with its runtime value, escaped for regex use.

    Unknown names are left as-is: that way a literal brace in a pattern does
    not silently turn into an empty string.
    """

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            return match.group(0)
        return re.escape(values[name])

    return _PLACEHOLDER_PATTERN.sub(_sub, pattern)


def run_checks(
    answer: str, checks: Checks, today: date | None = None
) -> tuple[CheckFailure, ...]:
    """Return every violated expectation (empty tuple == all checks passed)."""
    values = placeholders(today)
    failures: list[CheckFailure] = []
    text = answer or ""

    for pattern in checks.must_match:
        expanded = expand(pattern, values)
        if not re.search(expanded, text, re.IGNORECASE | re.DOTALL):
            failures.append(
                CheckFailure("must_match", f"pattern not found: {expanded}")
            )

    for pattern in checks.must_not_match:
        expanded = expand(pattern, values)
        hit = re.search(expanded, text, re.IGNORECASE | re.DOTALL)
        if hit:
            failures.append(
                CheckFailure(
                    "must_not_match",
                    f"forbidden pattern {expanded} matched {hit.group(0)[:60]!r}",
                )
            )

    if checks.max_chars is not None and len(text) > checks.max_chars:
        failures.append(
            CheckFailure("max_chars", f"{len(text)} chars > {checks.max_chars}")
        )

    if checks.min_chars is not None and len(text) < checks.min_chars:
        failures.append(
            CheckFailure("min_chars", f"{len(text)} chars < {checks.min_chars}")
        )

    return tuple(failures)
