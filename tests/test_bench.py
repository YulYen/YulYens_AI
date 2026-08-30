"""Tests der Stoppuhr (#42) — alle ohne Modell.

Ein Messwerkzeug hat ein eigenes Versagensmuster: es liefert immer eine Zahl.
Die Tests hier richten sich deshalb weniger gegen Abstürze als gegen *stille
Falschmessung* — eine Fehlermeldung, die als schneller Lauf durchgeht; ein
Aufwärmlauf, der in den Median rutscht; ein Ausreißer, der den Vergleich kippt.
"""

from __future__ import annotations

import time

import pytest
from bench.cli import _holdback_note, _quietest_persona
from bench.drivers import HttpDriver, InProcessDriver
from bench.harness import (
    BenchAborted,
    BenchRun,
    Question,
    Sample,
    aggregate,
    measure,
    measured,
    run_bench,
)
from bench.questions import DEFAULT_QUESTIONS, load_questions
from bench.report import CSV_COLUMNS, render_csv, render_markdown
from core.streaming_provider import LLM_ERROR_MESSAGE

from tests.doubles import factory_double, streamer_double

Q1 = Question("q1", "Erste Frage?")
Q2 = Question("q2", "Zweite Frage?")


class _FakeDriver:
    """Ein Backend, dessen Zeitverhalten der Test vorgibt.

    Kein ``create_autospec``-Double: ``Driver`` ist ein Protocol ohne
    Implementierung, es gäbe also kein Original, von dem das Double abdriften
    könnte. Die drei echten Kollaborateure (Streamer, Guard, Factory) kommen
    weiterhin aus ``tests/doubles.py`` — siehe den InProcess-Test unten.
    """

    mode = "fake"

    def __init__(
        self,
        chunks: list[str] | None = None,
        *,
        first_delay: float | list[float] = 0.0,
        model_first_ms: int | None = None,
        tokens: int | None = None,
        raise_on_call: int | None = None,
    ) -> None:
        self.chunks = chunks if chunks is not None else ["Hallo ", "Welt"]
        self.first_delay = first_delay
        self.model_first_ms = model_first_ms
        self.tokens = tokens
        self.raise_on_call = raise_on_call
        self.calls = 0
        self.asked: list[tuple[str, str]] = []

    def _delay(self) -> float:
        if isinstance(self.first_delay, list):
            index = min(self.calls - 1, len(self.first_delay) - 1)
            return self.first_delay[index]
        return self.first_delay

    def stream(self, persona: str, question: str):
        self.calls += 1
        self.asked.append((persona, question))
        if self.raise_on_call == self.calls:
            raise RuntimeError("Backend weg")
        delay = self._delay()

        def _gen():
            if delay:
                time.sleep(delay)
            yield from self.chunks

        return _gen()

    def model_stats(self) -> tuple[int | None, int | None]:
        return self.model_first_ms, self.tokens


def _sample(**overrides) -> Sample:
    base = dict(
        persona="PETER",
        question_id="q1",
        repeat=1,
        warmup=False,
        t_first_ms=100,
        t_total_ms=200,
        chars=50,
        t_model_first_ms=None,
        tokens=None,
        error=None,
    )
    base.update(overrides)
    return Sample(**base)  # type: ignore[arg-type]


# ---- Was gemessen wird -----------------------------------------------------


def test_the_stopwatch_times_the_delivered_character_not_the_models_token():
    """Der Kern des Tickets.

    Zwischen dem ersten Token des Modells und dem ersten Zeichen beim Aufrufer
    liegt der Guard-Holdback (#51). Wer nur die Modellzeit misst, sieht ihn
    nicht — und genau davor warnt CLAUDE.md für dieses Ticket.
    """
    driver = _FakeDriver(first_delay=0.08, model_first_ms=10)

    sample = measure(driver, "PETER", Q1, repeat=1)

    assert sample.t_first_ms is not None and sample.t_first_ms >= 70
    assert sample.holdback_ms == sample.t_first_ms - 10


def test_without_model_stats_there_is_no_holdback_column():
    """Über HTTP ist die Modellzeit nicht zu haben — dann bleibt die Spalte leer.

    Sie zu schätzen wäre schlimmer als sie wegzulassen: eine erfundene Zahl
    steht neben lauter gemessenen und sieht genauso aus.
    """
    sample = measure(_FakeDriver(), "PETER", Q1, repeat=1)

    assert sample.t_model_first_ms is None
    assert sample.holdback_ms is None


def test_throughput_starts_at_the_first_character_not_at_the_request():
    """Sonst steckte die Anlaufzeit im Durchsatz.

    Ein Modell mit langer Anlaufzeit und schnellem Schreiben sähe dann aus wie
    ein langsam schreibendes — und das sind zwei verschiedene Befunde mit zwei
    verschiedenen Ursachen.
    """
    sample = _sample(t_first_ms=1000, t_total_ms=2000, chars=1000)

    assert sample.chars_per_second == pytest.approx(1000.0)


def test_a_backend_error_delivered_as_text_is_not_a_fast_measurement():
    """`stream()` fängt Backend-Fehler ab und liefert sie als Text aus.

    Ohne diese Erkennung wäre ein nicht erreichbares Ollama die schnellste
    Messung des Laufs — und der Report meldete eine Bestzeit.
    """
    driver = _FakeDriver(chunks=[LLM_ERROR_MESSAGE])

    sample = measure(driver, "PETER", Q1, repeat=1, error_marker=LLM_ERROR_MESSAGE)

    assert not sample.ok
    assert sample not in measured([sample])


def test_an_exception_becomes_a_recorded_failure_not_a_crash():
    driver = _FakeDriver(raise_on_call=1)

    sample = measure(driver, "PETER", Q1, repeat=1)

    assert sample.error is not None and "RuntimeError" in sample.error


def test_the_stream_is_closed_after_every_measurement():
    """Projektregel: Generatoren werden geschlossen, nicht dem GC überlassen.

    Sonst läuft der Backend-Stream weiter — genau der Befund aus der
    `cancels`-Stolperfalle, nur an anderer Stelle.
    """

    class _ClosableStream:
        def __init__(self) -> None:
            self.closed = False

        def __iter__(self):
            return iter(["a", "b"])

        def close(self) -> None:
            self.closed = True

    stream = _ClosableStream()

    class _Driver:
        mode = "fake"

        def stream(self, persona, question):
            return stream

        def model_stats(self):
            return None, None

    measure(_Driver(), "PETER", Q1, repeat=1)

    assert stream.closed


# ---- Der Messplan ----------------------------------------------------------


def test_the_plan_interleaves_the_questions_round_by_round():
    """Die Reihenfolge ist Teil der Methode, nicht Geschmack.

    Zwei Gründe, beide unabhängig: eine Maschine, die im Lauf warm wird, würde
    fragenweise genau die Frage benachteiligen, die hinten steht — und
    dieselbe Frage direkt hintereinander zu wiederholen trifft den
    Prompt-Cache des Backends, was die zweite Runde grundlos schneller macht.
    """
    driver = _FakeDriver()

    samples = run_bench(driver, ["PETER"], [Q1, Q2], repeats=2, warmup=0)

    order = [(s.repeat, s.question_id) for s in samples]
    assert order == [(1, "q1"), (1, "q2"), (2, "q1"), (2, "q2")]


def test_warmup_runs_are_reported_but_stay_out_of_the_medians():
    """Der Kaltstart ist eine eigene Zahl, kein Ausreißer.

    Er lädt das Modell in den VRAM und ist deshalb um Größenordnungen
    langsamer. Weggeworfen gehört er trotzdem nicht — nur getrennt.
    """
    driver = _FakeDriver(first_delay=[0.12, 0.0, 0.0, 0.0])
    run = BenchRun(
        started_at="jetzt",
        mode="fake",
        backend="fake",
        model="m",
        repeats=3,
        warmup=1,
    )

    run.samples = run_bench(driver, ["PETER"], [Q1], repeats=3, warmup=1)

    assert len(run.samples) == 4
    assert run.cold_start.runs == 1
    assert run.overall.runs == 3
    assert run.cold_start.t_first_ms >= 100
    assert run.overall.t_first_ms < 100


def test_the_very_first_failing_measurement_aborts_the_run():
    """Ein Aufbaufehler ist kein Messergebnis.

    Ohne Abbruch liefe der volle Plan gegen ein totes Backend durch und
    hinterließe einen Report voller Fehlerzeilen — Minuten für nichts.
    """
    driver = _FakeDriver(raise_on_call=1)

    with pytest.raises(BenchAborted):
        run_bench(driver, ["PETER"], [Q1, Q2], repeats=2, warmup=0)


def test_a_failure_in_the_middle_is_recorded_and_the_run_goes_on():
    """Die Gegenrichtung: ein Aussetzer mittendrin ist ein Befund."""
    driver = _FakeDriver(raise_on_call=3)

    samples = run_bench(driver, ["PETER"], [Q1, Q2], repeats=2, warmup=0)

    assert len(samples) == 4
    assert [s.ok for s in samples] == [True, True, False, True]
    assert len(measured(samples)) == 3


# ---- Die Auswertung --------------------------------------------------------


def test_the_aggregate_uses_the_median_so_one_outlier_cannot_move_it():
    """Ein nachladendes Modell oder ein Hintergrundjob kippt den Mittelwert.

    Bei einer Handvoll Läufe ist das keine Theorie: 100/110/5000 ergibt einen
    Mittelwert von 1736 und einen Median von 110.
    """
    samples = [_sample(t_first_ms=value) for value in (100, 110, 5000)]

    assert aggregate(samples, "x").t_first_ms == 110


def test_failed_measurements_never_reach_the_statistics():
    samples = [_sample(t_first_ms=100), _sample(t_first_ms=1, error="kaputt")]

    assert aggregate(samples, "x").runs == 1
    assert aggregate(samples, "x").t_first_ms == 100


def test_the_csv_carries_every_measurement_including_the_warmup():
    """Das Markdown fasst zusammen, das CSV ist die Rohaufzeichnung.

    Wer zwei Läufe vergleicht, braucht die einzelnen Zeilen — auch die
    Aufwärmrunde, deren Kosten man sonst nirgends nachlesen kann.
    """
    run = BenchRun(
        started_at="jetzt",
        mode="fake",
        backend="fake",
        model="m",
        repeats=1,
        warmup=1,
        samples=[_sample(warmup=True), _sample()],
    )

    lines = render_csv(run).strip().splitlines()

    assert lines[0] == ",".join(CSV_COLUMNS)
    assert len(lines) == 3
    assert lines[1].split(",")[5] == "1"  # warmup-Spalte


def test_the_report_repeats_the_warnings_it_was_given():
    """Eine Warnung, die nur im Terminal stand, ist beim Nachlesen weg."""
    run = BenchRun(
        started_at="jetzt",
        mode="fake",
        backend="dummy",
        model="m",
        repeats=1,
        warmup=0,
        samples=[_sample()],
        warnings=["Backend `dummy`: die Zahlen bedeuten nichts."],
    )

    assert "die Zahlen bedeuten nichts" in render_markdown(run)


def test_the_report_survives_a_run_without_a_single_usable_measurement():
    run = BenchRun(
        started_at="jetzt",
        mode="fake",
        backend="fake",
        model="m",
        repeats=1,
        warmup=0,
        samples=[_sample(error="kaputt")],
    )

    text = render_markdown(run)

    assert "Keine verwertbare Messung" in text
    assert "kaputt" in text


# ---- Kopfzeile und Fragensatz ---------------------------------------------


def test_the_header_says_when_the_holdback_does_not_apply():
    """Ohne Ausgangsprüfung setzt der Moderator den Holdback selbst auf 0.

    Zwei Läufe mit derselben Zahl in der Config, aber unterschiedlichen
    Guard-Schaltern, unterscheiden sich dann drastisch in der Latenz — ohne
    dass die Zahl allein es verriete.
    """
    aktiv = {"enabled": True, "stream_holdback_chars": 32, "pii_protection": True}
    aus = {
        "enabled": True,
        "stream_holdback_chars": 32,
        "pii_protection": False,
        "output_blocklist": False,
    }

    assert _holdback_note(aktiv) == "32"
    assert "wirkungslos" in _holdback_note(aus)


def test_the_default_persona_is_the_coolest_one():
    """Abgeleitet statt verdrahtet, damit der Default auch fremden Ensembles gilt.

    Die niedrigste Temperatur bedeutet die ähnlichsten Antworten über mehrere
    Runden — und die Antwortlänge ist der größte Einzeleinfluss auf die
    Gesamtdauer.
    """
    from config import personas

    temperaturen = {"LEAH": 0.65, "PETER": 0.10, "POPCORN": 0.80}
    original = personas.get_options
    personas.get_options = lambda name: {"temperature": temperaturen[name]}
    try:
        assert _quietest_persona(list(temperaturen)) == "PETER"
    finally:
        personas.get_options = original


def test_the_shipped_question_set_has_unique_ids():
    """Die IDs sind der Schlüssel, an dem zwei Läufe zusammenfinden."""
    ids = [question.id for question in DEFAULT_QUESTIONS]

    assert len(ids) == len(set(ids))
    assert all(question.text.strip() for question in DEFAULT_QUESTIONS)


def test_the_prefill_question_is_long_enough_to_show_the_effect():
    """Sie ist der einzige Fall, der die Prompt-Verarbeitung sichtbar macht."""
    prefill = next(q for q in DEFAULT_QUESTIONS if q.id == "q5_prefill")

    assert len(prefill.text) > 1000


def test_a_custom_question_file_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "fragen.txt"
    path.write_text(
        "# ein Kommentar\n\nErste Frage?\n\n  Zweite Frage?  \n", encoding="utf-8"
    )

    questions = load_questions(str(path))

    assert [q.id for q in questions] == ["f01", "f02"]
    assert questions[1].text == "Zweite Frage?"


def test_a_question_file_without_questions_is_an_error(tmp_path):
    """Sonst liefe ein Plan über null Fragen durch und meldete Erfolg."""
    path = tmp_path / "leer.txt"
    path.write_text("# nur Kommentare\n\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_questions(str(path))


# ---- Die beiden Wege -------------------------------------------------------


def test_the_in_process_driver_reuses_one_streamer_per_persona():
    """Ein frischer Streamer je Messung würde seinen Aufbau mitmessen."""
    streamer = streamer_double()
    factory = factory_double()
    factory.get_streamer_for_persona.return_value = streamer

    driver = InProcessDriver(factory)
    driver.stream("PETER", "Frage?")
    driver.stream("PETER", "Andere Frage?")

    assert factory.get_streamer_for_persona.call_count == 1


def test_the_in_process_driver_reads_the_streamers_own_stats():
    """Sie liegen seit #36 nach jedem Stream am Provider — nicht neu erfinden."""

    class _Stats:
        t_first_ms = 1234
        tokens = 42

    streamer = streamer_double(last_stream_stats=_Stats())
    factory = factory_double()
    factory.get_streamer_for_persona.return_value = streamer

    driver = InProcessDriver(factory)
    driver.stream("PETER", "Frage?")

    assert driver.model_stats() == (1234, 42)


def test_the_http_driver_reads_the_sse_stream():
    """Kommentare, Herzschläge und `[DONE]` sind keine Tokens."""

    class _Response:
        def __init__(self) -> None:
            self.closed = False

        def iter_lines(self, decode_unicode=False):
            yield ""
            yield 'data: {"choices":[{"delta":{"content":"Hal"}}]}'
            yield "kein data-Feld"
            yield 'data: {"kaputt'
            yield 'data: {"choices":[{"delta":{"content":"lo"}}]}'
            yield "data: [DONE]"
            yield 'data: {"choices":[{"delta":{"content":"zu spät"}}]}'

        def close(self) -> None:
            self.closed = True

    response = _Response()

    assert list(HttpDriver._iter_sse(response)) == ["Hal", "lo"]
    assert response.closed
