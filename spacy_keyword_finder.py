import spacy
import logging

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT", "PRODUCT", "LAW"]

# Einzelne Wörter, die in keinem sinnvollen Wiki-Suchbegriff vorkommen sollen
BLOCKWORDS = {
    "Hallo", "Hübsche", "Hi", "Na", "Servus", "Moin", "Schatz",
    "Liebling", "Guten", "Grüß", "Tag", "Huhu", "Toll", "Danke", "Bitte"
}

MIN_LENGTH = 3  # mind. 3 Buchstaben
MIN_WORDS = 1   # mind. 2 Wörter (d.h. 1x "_")

class SpacyKeywordFinder:
    def __init__(self, model_name="de_core_news_md"):
        self.nlp = spacy.load(model_name)

    def is_valid_keyword(self, ent_text, ent_label):
        keyword = ent_text.strip().replace(" ", "_").replace("ß", "ss")

        # Schnell rausfiltern
        if ent_label not in RELEVANT_LABELS:
            return False
        if len(keyword) < MIN_LENGTH:
            return False
        if keyword.count("_") < (MIN_WORDS - 1):
            return False

        # Enthält unerwünschte Teile?
        if any(bad.lower() in keyword.lower() for bad in BLOCKWORDS):
            return False

        return True

    def find_keywords(self, text):
        doc = self.nlp(text)
        treffer = []
        for ent in doc.ents:
            if self.is_valid_keyword(ent.text, ent.label_):
                keyword = ent.text.strip().replace(" ", "_").replace("ß", "ss")
                logging.info(f"{ent.label_} Treffer: {keyword}")
                if keyword not in treffer:
                    treffer.append(keyword)
        return treffer