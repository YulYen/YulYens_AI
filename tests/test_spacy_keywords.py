import pytest

from tests.util import has_spacy_model
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant

pytestmark = pytest.mark.skipif(
    not has_spacy_model("de_core_news_lg"),
    reason="spaCy model de_core_news_lg not installed",
)

# (1) Einfache positive Fälle
easy_positive = [
    ("Wer war Albert Einstein?", ["Albert_Einstein"]),
    ("Wer ist Elon Musk?", ["Elon_Musk"]),
    ("Erzähl mir etwas über Angela Merkel.", ["Angela_Merkel"]),
    ("Wo steht der Eiffelturm?", ["Eiffelturm"]),
    ("In welchem Land liegt die Sahara?", ["Sahara"]),
    ("Was weißt du über Madeira?", ["Madeira"]),
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
    #("Treibst du Sport?", []),
    ("Wie funktioniert ein Motor?", []),
    ("Lass uns ein Spiel spielen.", []),
    ("Bist du ein Bot?", []),
]

# (3) Knifflige positive Fälle
tricky_positive = [
    ("Was weißt du über die RAF?", ["RAF"]),
    ("Erzähl mir etwas über Saturn.", ["Saturn"]),
    #("Was weißt du über Merkel?", ["Merkel"]),
    ("Kennst Ludwig van Beethoven?", ["Ludwig_van_Beethoven"]),
    ("Was weißt du über NASA?", ["NASA"]),
    ("Erzähl mir etwas über Amazon.", ["Amazon"]),
    #("Kennst du den Film Inception?", ["Inception"]),
    ("Was weißt du über die Olympischen Spiele 2012 in London?", ["London"]),
    #("Erzähl mir von der Titanic.", ["Titanic"]),
    ("Antworte bitte kurz: Welches Amt bekleidet Friedrich Merz ab Mai 2025??", ["Friedrich_Merz"]),
]

top_pick_cases = [
    # 1
    ("Seit wann ist Donald Trump Präsident der USA?", ["Donald_Trump", "USA"]),
    # 2 – zwei ORGs, frühe Position gewinnt
     ("Erzähl mir etwas über Bundesbank und die Amazon.", ["Bundesbank", "Amazon"]),
    # 3 – zwei LOCs
    ("Ist Paris größer als Berlin?", ["Paris", "Berlin"]),
    # 4 – zwei Fußball-ORGs, längerer früher Span bevorzugt
    ("Wie erfolgreich ist der FC Bayern München gegen Borussia Dortmund?", ["FC_Bayern_München", "Borussia_Dortmund"]),
    # 5 – zwei ORGs
    ("Hat die NASA mit SpaceX zusammengearbeitet?", ["NASA", "SpaceX"]),
    # 6 – LOC vs. LOC
    ("Wo liegt der Grand Canyon in den USA?", ["Grand_Canyon", "USA"]),
    # 7 – zwei ORGs, längerer früher Span
    ("Was macht die Europäische Union im Vergleich zur NATO?", ["Europäische_Union", "NATO"]),
    # 8 – PER vs. LOC
    ("Wer war Kaiser Wilhelm II in Deutschland?", ["Kaiser_Wilhelm_II", "Deutschland"]),
    # 9 – mehrere Himmelskörper (LOC)
    ("Ist Saturn weiter von der Erde entfernt als Jupiter?", ["Saturn", "Erde", "Jupiter"]),
    # 10 – PER zuerst, dann ORG
    ("Welche Strategie verfolgt Satya Nadella bei Microsoft?", ["Satya_Nadella", "Microsoft"]),

]

# (4) Knifflige negative Fälle (realistisch erreichbar)
tricky_negative = [
    ("Hallo meine Liebe!", []),
    ("Guten Morgen, Siri!", []),

]


@pytest.fixture(scope="module")
def keyword_finder():
    return SpacyKeywordFinder(variant = ModelVariant.LARGE)

@pytest.mark.parametrize("text,expected", easy_positive + easy_negative + tricky_positive + tricky_negative + top_pick_cases)
def test_keyword_detection(keyword_finder, text, expected):
    result = keyword_finder.find_keywords(text)
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize( "text,expected_list", easy_positive + easy_negative + tricky_positive + tricky_negative + top_pick_cases)
def test_top_keyword_selection(keyword_finder, text, expected_list):
    top = keyword_finder.find_top_keyword(text)

    if expected_list:
        # Konvention: das erste erwartete Keyword gilt als „Top“
        assert top == expected_list[0]
    else:
        assert top is None

