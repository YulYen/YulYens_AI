import logging
from enum import Enum

import spacy

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT", "GPE"]


BLOCKWORDS = {
    "hallo",
    "hübsche",
    "hi",
    "na",
    "servus",
    "moin",
    "schatz",
    "liebling",
    "guten",
    "grüß",
    "tag",
    "huhu",
    "toll",
    "danke",
    "bitte",
    "super",
    "cool",
    "prima",
    "jo",
    "gern",
    "okay",
    "schreib",
    "hey",
}

W_TOKENS = {
    "wer",
    "was",
    "welches",
    "welcher",
    "welche",
    "wann",
    "wo",
    "wie",
    "warum",
    "wieso",
}
GENERIC_NOUNS = {"amt", "funktion", "rolle", "posten", "thema", "frage"}



def resolve_spacy_model(cfg: dict) -> str:
    """
    Determine the correct spaCy model name based on language and variant
    defined in config.yaml. Raises a clear error if configuration is incomplete.
    """
    wiki_cfg = cfg.wiki
    if not wiki_cfg:
        raise ValueError("Missing 'wiki' section in configuration.")

    if not cfg.language:
        raise ValueError("Missing top-level key 'language' in configuration.")

    if "spacy_model_variant" not in wiki_cfg:
        raise ValueError("Missing 'spacy_model_variant' in wiki section.")

    if "spacy_model_map" not in wiki_cfg:
        raise ValueError("Missing 'spacy_model_map' in wiki section.")

    lang = cfg.language
    variant = wiki_cfg["spacy_model_variant"]
    model_map = wiki_cfg["spacy_model_map"]

    try:
        return model_map[lang][variant]
    except KeyError as e:
        raise ValueError(
            f"No spaCy model mapping for language='{lang}', variant='{variant}'."
        ) from e


class SpacyKeywordFinder:
    """Finds relevant keywords in German text for the Wikipedia search."""

    def __init__(self, variant):
        self.model_name = variant
        logging.info(f"Loading spaCy model: {self.model_name}")
        self.nlp = spacy.load(self.model_name)

    def _normalize_keyword(self, text: str) -> str:
        """Helper method: normalizes spaces, ß, and similar details."""
        return text.strip().replace(" ", "_").replace("\u00df", "ss")

    def is_valid_keyword(self, ent):
        keyword = ent.text.strip().replace(" ", "_").replace("\u00df", "ss")

        # Filter by entity type
        if ent.label_ not in RELEVANT_LABELS:
            return False

        # Must contain at least one letter
        if not any(c.isalpha() for c in keyword):
            return False

        # Reject items that are too short or purely numeric
        if len(keyword) < 3:
            return False

        # Blocklist check per word (e.g. "Hallo_Schatz" blocks both parts)
        if any(w in BLOCKWORDS for w in keyword.lower().split("_")):
            return False

        # Accept only proper nouns or nouns
        if ent.root.pos_ not in ("PROPN", "NOUN"):
            return False

        # Ensure imperatives such as "Schreib" do not slip through
        if ent.root.lemma_.lower() in BLOCKWORDS:
            return False

        # No trailing exclamation marks
        if keyword.endswith("!"):
            return False

        # New heuristic 1: drop entities containing W-question words
        ent_lemmas = [t.lemma_.lower() for t in ent]
        if any(lemma in W_TOKENS for lemma in ent_lemmas):
            return False

        # New heuristic 2: allow generic nouns only when paired with a proper noun
        if any(lemma in GENERIC_NOUNS for lemma in ent_lemmas):
            if not any(t.pos_ == "PROPN" for t in ent):
                return False

        return True

    def find_keywords(self, text):
        doc = self.nlp(text)
        matches = []

        # (1) Standard spaCy entities
        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                keyword = self._normalize_keyword(ent.text)
                logging.info(f"{ent.label_} match: {keyword}")
                if keyword not in matches:
                    matches.append(keyword)

        return matches

    def find_top_keyword(self, text: str):
        doc = self.nlp(text)
        candidates = []

        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                # Score: earlier in the text plus span length
                pos_score = 1.0 - (ent.start_char / max(1, len(text)))  # 0..1
                len_score = min(len(ent.text) / 10.0, 1.0)  # max 1.0
                score = pos_score + len_score
                candidates.append((score, ent))

        if not candidates:
            return None

        # Highest score first
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_ent = candidates[0][1]
        return self._normalize_keyword(best_ent.text)
