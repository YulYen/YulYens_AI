import spacy
import logging

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT"]

BLOCKWORDS = {
    "hallo", "hübsche", "hi", "na", "servus", "moin", "schatz",
    "liebling", "guten", "grüß", "tag", "huhu", "toll", "danke", "bitte",
    "super", "cool", "prima", "jo", "gern", "okay", "schreib"
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

        # Sicherstellen, dass keine Imperative wie "Schreib" durchrutschen
        if ent.root.lemma_.lower() in BLOCKWORDS:
            return False

        # Kein Ausrufezeichen am Ende
        if keyword.endswith("!"):
            return False

        return True

    def find_keywords(self, text):
        doc = self.nlp(text)
        treffer = []

        # (1) normale spaCy-Entitäten
        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                keyword = ent.text.strip().replace(" ", "_").replace("\u00df", "ss")
                logging.info(f"{ent.label_} Treffer: {keyword}")
                if keyword not in treffer:
                    treffer.append(keyword)

        return treffer
    

    def find_top_keyword(self, text: str):
        doc = self.nlp(text)
        candidates = []

        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                # Score: früher im Text + Länge
                pos_score = 1.0 - (ent.start_char / max(1, len(text)))  # 0..1
                len_score = min(len(ent.text) / 10.0, 1.0)              # max 1.0
                score = pos_score + len_score
                candidates.append((score, ent))

        if not candidates:
            return None

        # Bester Score zuerst
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_ent = candidates[0][1]
        return best_ent.text.strip().replace(" ", "_").replace("\u00df", "ss")
