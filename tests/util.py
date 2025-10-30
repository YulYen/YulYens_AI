"""Test utilities e.g. for conditional spaCy model checks."""

import importlib.util
from functools import lru_cache
from config.config_singleton import Config



@lru_cache
def has_spacy_model(name: str) -> bool:
    """Return True if the specified spaCy language model is installed."""
    return importlib.util.find_spec(name) is not None

def is_model(name: str) -> bool:
    """
    Returns True if the current configured model matches `name`.
    Safe and minimal — reads from config.yaml via Config.
    """
    try:
        cfg = Config("config.yaml")
        current = cfg.core.get("model_name")
        return current == name
    except Exception:
        # Never break test collection if config is missing
        return False
