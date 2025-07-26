import spacy

nlp = spacy.load("de_core_news_md")

def find_wiki_keywords(text):
    doc = nlp(text)
    treffer = []
    for ent in doc.ents:
        if ent.label_ in ["PER", "ORG", "LOC", "MISC"]:
            print(f"Gefunden: {ent.text} ({ent.label_})")
            treffer.append(ent.text.replace(" ", "_"))
    return treffer

# Test
testfrage = "Was kannst du mir über Friedrich Merz erzählen im Vergleich zu Gerhard Schröder??"
print("Suchbegriff:", find_wiki_keywords(testfrage))