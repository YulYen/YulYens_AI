import pytest
from spacy_keyword_finder import SpacyKeywordFinder, ModelVariant

# (1) Einfache positive Fälle
easy_positive = [
    ("Wer war Albert Einstein?", ["Albert_Einstein"]),
    #("Wer ist Elon Musk?", ["Elon_Musk"]),
    ("Erzähl mir etwas über Angela Merkel.", ["Angela_Merkel"]),
    ("Wo steht der Eiffelturm?", ["Eiffelturm"]),
    ("In welchem Land liegt die Sahara?", ["Sahara"]),
    #("Was weißt du über Google?", ["Google"]),
    ("Wer gründete Apple?", ["Apple"]),
    ("Schreib bitte über Napoleon.", ["Napoleon"]),
    #("Was war der Zweite Weltkrieg?", ["Zweiter_Weltkrieg"]),
    #("Kennst du Leonardo da Vinci?", ["Leonardo_da_Vinci"]),
]

# (2) Einfache negative Fälle
easy_negative = [
    ("Wie geht es dir?", []),
    ("Danke!", []),
    ("Toll!", []),
    ("Super!", []),
    ("Danke dir!", []),
    ("Wie geht es dir?", []),
    ("Erzähl mir einen Witz.", []),
    ("Hast du heute Zeit?", []),
    ("Wie ist das Wetter heute?", []),
    ("Was soll ich morgen kochen?", []),
    ("Wo bist du gerade?", []),
    ("Treibst du Sport?", []),
    ("Wie funktioniert ein Motor?", []),
    ("Lass uns ein Spiel spielen.", []),
    ("Bist du ein Bot?", []),
]

# (3) Knifflige positive Fälle
tricky_positive = [
    ("Was weißt du über die RAF?", ["RAF"]),
    ("Erzähl mir etwas über Saturn.", ["Saturn"]),
    ("Was weißt du über Merkel?", ["Merkel"]),
    #("Kennst Ludwig van Beethoven?", ["Ludwig_van_Beethoven"]),
    #("Was weißt du über Google und Facebook?", ["Google", "Facebook"]),
    ("Was weißt du über NASA?", ["NASA"]),
    ("Erzähl mir etwas über Amazon.", ["Amazon"]),
    #("Kennst du den Film Inception?", ["Inception"]),
    ("Was weißt du über die Olympischen Spiele 2012 in London?", ["London"]),
    #("Erzähl mir von der Titanic.", ["Titanic"]),
]

# (4) Knifflige negative Fälle (realistisch erreichbar)
tricky_negative = [
    ("Hallo meine Liebe!", []),
    ("Guten Morgen, Siri!", []),
    #("Fahr nicht wie Schumacher!", []),

]

@pytest.fixture(scope="module")
def keyword_finder():
    return SpacyKeywordFinder(variant = ModelVariant.MEDIUM)

@pytest.mark.parametrize("text,expected", easy_positive + easy_negative + tricky_positive + tricky_negative)
def test_keyword_detection(keyword_finder, text, expected):
    result = keyword_finder.find_keywords(text)
    assert sorted(result) == sorted(expected)

