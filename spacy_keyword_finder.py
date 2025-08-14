import spacy
import logging

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT", "GPE"]


BLOCKWORDS = {
    "hallo", "hübsche", "hi", "na", "servus", "moin", "schatz",
    "liebling", "guten", "grüß", "tag", "huhu", "toll", "danke", "bitte",
    "super", "cool", "prima", "jo", "gern", "okay", "schreib"
}

W_TOKENS = {"wer", "was", "welches", "welcher", "welche", "wann", "wo", "wie", "warum", "wieso"}
GENERIC_NOUNS = {"amt", "funktion", "rolle", "posten", "thema", "frage"}

from enum import Enum

class ModelVariant(str, Enum):
    MEDIUM = "de_core_news_md"
    LARGE = "de_core_news_lg"

class SpacyKeywordFinder:
    def __init__(self, variant):
        self.model_name = variant.value
        logging.info(f"Lade spaCy-Modell: {self.model_name}")
        self.nlp = spacy.load(self.model_name)

    def _normalize_keyword(self, text: str) -> str:
        """Hilfsmethode: Vereinheitlicht Leerzeichen, ß usw."""
        return text.strip().replace(" ", "_").replace("\u00df", "ss")

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
        
         # Neue, kleine Heuristik 1: W‑Fragewörter innerhalb der Entität → verwerfen
        ent_lemmas = [t.lemma_.lower() for t in ent]
        if any(l in W_TOKENS for l in ent_lemmas):
            return False

        # Neue, kleine Heuristik 2: generische Nomen nur mit Eigennamen (PROPN) zulassen
        if any(l in GENERIC_NOUNS for l in ent_lemmas):
            if not any(t.pos_ == "PROPN" for t in ent):
                return False

        return True

    def find_keywords(self, text):
        doc = self.nlp(text)
        treffer = []

        # (1) normale spaCy-Entitäten
        for ent in doc.ents:
            if self.is_valid_keyword(ent):
                keyword = self._normalize_keyword(ent.text) 
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
        return self._normalize_keyword(best_ent.text)
