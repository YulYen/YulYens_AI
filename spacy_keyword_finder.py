import spacy

RELEVANT_LABELS = ["PER", "ORG", "LOC", "EVENT", "PRODUCT", "LAW"]

class SpacyKeywordFinder:
    def __init__(self, model_name="de_core_news_md"):
        self.nlp = spacy.load(model_name)

    def find_keywords(self, text):
        doc = self.nlp(text)
        treffer = []
        for ent in doc.ents:
            if ent.label_ in RELEVANT_LABELS:
                keyword = ent.text.replace(" ", "_").replace("ß", "ss")
                if keyword not in treffer:
                    treffer.append(keyword)
        return treffer