"""Der Standard-Fragensatz der Stoppuhr (#42).

Er steht im Repo und nicht in der Config, weil er ein **Maßstab** ist: zwei
Läufe sind nur vergleichbar, wenn sie dieselben Fragen gestellt haben. Eine
Frage zu ändern heißt, die Vergleichbarkeit mit allen früheren Läufen
aufzugeben — das soll ein Commit sein, keine Config-Zeile.

Die fünf decken bewusst verschiedene Formen ab: sehr kurze Antwort, Erklärung,
freies Schreiben, Aufzählung — und einen langen Prompt bei kurzer Antwort.
Der letzte ist der interessanteste, weil er als einziger die *Prefill*-Zeit
sichtbar macht: alles vor dem ersten Token hängt an der Prompt-Länge, alles
danach am Durchsatz.
"""

from __future__ import annotations

from bench.harness import Question

# Der Wirt für die Prefill-Messung: sachlicher Fließtext, keine Wiederholung
# desselben Satzes. Wiederholter Text ist für ein Modell billiger zu
# verarbeiten als echter, und der Prefill sähe dann schneller aus, als er ist.
_LANGER_TEXT = (
    "Ein Segelschiff wird von der Kraft des Windes angetrieben, die über die "
    "Segelflächen auf den Rumpf übertragen wird. Die Form eines Segels erzeugt "
    "dabei einen Druckunterschied, ähnlich wie bei einer Tragfläche. Der Kiel "
    "unter dem Rumpf verhindert, dass das Schiff seitlich abgetrieben wird, "
    "und wandelt einen Teil der seitlichen Kraft in Vortrieb um. Das Ruder am "
    "Heck hält den Kurs und gleicht Abweichungen aus. Die Besatzung stellt die "
    "Segel je nach Windrichtung unterschiedlich: bei Wind von hinten stehen "
    "sie weit offen, bei Wind von schräg vorn dicht am Rumpf. Ein Segelschiff "
    "kann nicht direkt gegen den Wind fahren, wohl aber in einem Winkel dazu; "
    "durch abwechselnde Schläge nach links und rechts arbeitet es sich "
    "trotzdem gegen den Wind voran. Diese Technik heißt Kreuzen und verlängert "
    "den zurückgelegten Weg deutlich. Große Frachtsegler des neunzehnten "
    "Jahrhunderts trugen mehrere tausend Quadratmeter Segelfläche an drei oder "
    "vier Masten. Ihre Fahrtzeiten hingen stark von den vorherrschenden "
    "Windsystemen ab, weshalb die Routen über die Ozeane keineswegs den "
    "kürzesten Linien folgten. Mit dem Aufkommen der Dampfmaschine verloren "
    "sie ihre wirtschaftliche Bedeutung, blieben auf einigen Strecken aber "
    "noch lange konkurrenzfähig."
)

DEFAULT_QUESTIONS: tuple[Question, ...] = (
    Question("q1_kurz", "Nenne drei Farben."),
    Question(
        "q2_erklaerung",
        "Erkläre in drei Sätzen, was ein Betriebssystem macht.",
    ),
    Question(
        "q3_frei",
        "Schreibe eine kurze Geschichte über einen Roboter, der Kaffee kocht.",
    ),
    Question(
        "q4_liste",
        "Zähle fünf Gemüsesorten auf und schreibe je einen Satz dazu.",
    ),
    Question(
        "q5_prefill",
        f"{_LANGER_TEXT}\n\nFasse den Text in einem Satz zusammen.",
    ),
)


def load_questions(path: str) -> tuple[Question, ...]:
    """Liest einen eigenen Fragensatz: eine Frage je Zeile, `#` ist Kommentar.

    Die IDs werden durchnummeriert (`f01`, `f02`, …) und hängen damit an der
    Zeilennummer. Wer eine Zeile in der Mitte einfügt, verschiebt alle
    folgenden IDs — das ist gewollt sichtbar, weil danach auch die Zeilen im
    CSV nicht mehr dieselben Fragen meinen.
    """
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]

    texts = [line for line in lines if line and not line.startswith("#")]
    if not texts:
        raise ValueError(f"Kein einziger Fragetext in {path}.")
    return tuple(
        Question(f"f{index:02d}", text) for index, text in enumerate(texts, start=1)
    )
