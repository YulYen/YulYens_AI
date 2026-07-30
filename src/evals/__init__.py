"""Eval suite (#41): golden questions, guard red-team corpus, LLM-as-judge.

The corpora live as YAML under ``evals/`` so they can be edited without
touching code. Everything that needs a real model (answers, judge) is
optional — the loader, the deterministic checks and the guard corpus run
offline and are covered by the normal test suite.
"""

from evals.corpus import (
    BehaviourCorpus,
    Checks,
    CorpusError,
    GuardCase,
    GuardCorpus,
    KarlCase,
    KarlCorpus,
    PersonaCase,
    PersonaCorpus,
    load_behaviour_corpora,
    load_guard_corpus,
    load_karl_corpus,
    load_persona_corpora,
)

__all__ = [
    "BehaviourCorpus",
    "Checks",
    "CorpusError",
    "GuardCase",
    "GuardCorpus",
    "KarlCase",
    "KarlCorpus",
    "PersonaCase",
    "PersonaCorpus",
    "load_behaviour_corpora",
    "load_guard_corpus",
    "load_karl_corpus",
    "load_persona_corpora",
]
