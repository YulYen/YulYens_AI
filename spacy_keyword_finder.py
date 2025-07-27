import spacy
import logging

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT"]

BLOCKWORDS = {
    "hallo", "hübsche", "hi", "na", "servus", "moin", "schatz",
    "liebling", "guten", "grüß", "tag", "huhu", "toll", "danke", "bitte"
}

from enum import Enum

class ModelVariant(str, Enum):
    MEDIUM = "de_core_news_md"
    LARGE = "de_core_news_lg"

class SpacyKeywordFinder:
    def __init__(self, variant):
        self.model_name = variant.value
        logging.info(f"Lade spaCy-Modell: {self.model_name}")
        self.nlp = spacy.load(self.model_name)

    def is_valid_keyword(self, ent):
        keyword = ent.text.strip().replace(" ", "_").replace("\u00df", "ss")

        # Filter nach Entitätentyp
        if ent.label_ not in RELEVANT_LABELS:
            return False

        # Muss mindestens 1 Buchstaben enthalten
        if not any(c.isalpha() for c in keyword):
            return False

        # Nicht zu kurz und keine reinen Zahlen etc.
        if len(keyword) < 3:
            return False

        # Wortweise Blockprüfung (z. B. "Hallo_Schatz" → beide geblockt)
        if any(w in BLOCKWORDS for w in keyword.lower().split("_")):
            return False

        # Nur Eigennamen oder Nomen akzeptieren
        if ent.root.pos_ not in ("PROPN", "NOUN"):
            return False

        return True

    def find_keywords(self, text):
        doc = self.nlp(text)
        treffer = []
        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                keyword = ent.text.strip().replace(" ", "_").replace("\u00df", "ss")
                logging.info(f"{ent.label_} Treffer: {keyword}")
                if keyword not in treffer:
                    treffer.append(keyword)
        return treffer
