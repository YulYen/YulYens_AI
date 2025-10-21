"""Test utilities for conditional spaCy model checks."""

import importlib.util
from functools import lru_cache


@lru_cache
def has_spacy_model(name: str) -> bool:
    """Return True if the specified spaCy language model is installed."""
    return importlib.util.find_spec(name) is not None
