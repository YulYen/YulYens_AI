"""LLM-as-judge for the traits a regex cannot see.

Bias warning, deliberately spelled out because the backlog asks for it: by
default the judge is the same model that produced the answer, and models rate
their own output generously. Absolute scores are therefore only meaningful
*relative* to another run (baseline vs. LoRA adapter) with the same judge and
the same corpus. Configure ``evals.judge_model`` to use a different model when
one is available locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SYSTEM_PROMPT = (
    "Du bist ein strenger, nüchterner Prüfer für Chatbot-Antworten. "
    "Du bewertest ausschließlich, ob die Antwort die genannten Erwartungen "
    "erfüllt — nicht, ob dir die Antwort gefällt. "
    "Antworte ausschließlich im vorgegebenen Format, ohne Vorrede."
)

_SCORE_LINE = re.compile(r"^\s*(\d+)\s*[:.)]\s*([1-5])\b\s*\|?\s*(.*)$", re.MULTILINE)

# Judge answers must be deterministic; creativity is not wanted here.
JUDGE_OPTIONS = {"temperature": 0.0, "num_predict": 400}


@dataclass(frozen=True)
class TraitVerdict:
    trait: str
    score: int | None  # None == judge gave no parsable score
    reason: str

    @property
    def passed(self) -> bool:
        # 4 and 5 count as met; 3 is "partly" and deliberately not a pass.
        return self.score is not None and self.score >= 4


@dataclass(frozen=True)
class JudgeVerdict:
    verdicts: tuple[TraitVerdict, ...]
    raw: str

    @property
    def average(self) -> float | None:
        scored = [v.score for v in self.verdicts if v.score is not None]
        if not scored:
            return None
        return round(sum(scored) / len(scored), 2)

    @property
    def unscored(self) -> tuple[str, ...]:
        return tuple(v.trait for v in self.verdicts if v.score is None)


def build_prompt(question: str, answer: str, traits: tuple[str, ...]) -> list[dict]:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(traits))
    user = (
        f"FRAGE AN DEN CHATBOT:\n{question}\n\n"
        f"ANTWORT DES CHATBOTS:\n{answer}\n\n"
        f"ERWARTUNGEN:\n{numbered}\n\n"
        "Bewerte jede Erwartung einzeln von 1 bis 5 "
        "(1 = klar verfehlt, 3 = teilweise, 5 = vollständig erfüllt).\n"
        "Format, genau eine Zeile pro Erwartung, keine weiteren Zeilen:\n"
        "<Nummer>: <Punktzahl> | <maximal 15 Wörter Begründung>"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_verdict(raw: str, traits: tuple[str, ...]) -> JudgeVerdict:
    """Map the judge's lines back onto the traits.

    Unparsable or missing lines become ``score=None`` instead of a default
    value — a judge that failed to answer must not look like a pass.
    """
    scores: dict[int, tuple[int, str]] = {}
    for match in _SCORE_LINE.finditer(raw or ""):
        index = int(match.group(1)) - 1
        if 0 <= index < len(traits) and index not in scores:
            scores[index] = (int(match.group(2)), match.group(3).strip())

    verdicts = tuple(
        TraitVerdict(
            trait=trait,
            score=scores.get(i, (None, ""))[0],
            reason=scores.get(i, (None, "keine verwertbare Antwort des Judges"))[1],
        )
        for i, trait in enumerate(traits)
    )
    return JudgeVerdict(verdicts=verdicts, raw=raw or "")


class Judge:
    """Scores traits with an LLM. Any LLMCore implementation works."""

    def __init__(self, llm_core, model_name: str, keep_alive: int = 600) -> None:
        self._llm_core = llm_core
        self._model_name = model_name
        self._keep_alive = keep_alive

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(
        self, question: str, answer: str, traits: tuple[str, ...]
    ) -> JudgeVerdict:
        if not traits:
            return JudgeVerdict(verdicts=(), raw="")

        stream = self._llm_core.stream_chat(
            model_name=self._model_name,
            messages=build_prompt(question, answer, traits),
            options=dict(JUDGE_OPTIONS),
            keep_alive=self._keep_alive,
        )
        raw = "".join(
            chunk.get("message", {}).get("content", "") for chunk in stream
        ).strip()
        return parse_verdict(raw, traits)
