"""Stoppuhr für den Antwortpfad (#42).

Gemessen wird, was ein Aufrufer *erlebt*: die Zeit bis zum ersten Zeichen, das
ihn erreicht — nicht die Zeit bis zum ersten Token des Modells. Zwischen beiden
liegt der Guard-Holdback, und der ist im Projekt der größte Einzelposten der
wahrgenommenen Antwortzeit (#51). CLAUDE.md sagt genau das für dieses Ticket
voraus: eine backendseitige Messung der Zeit bis zum ersten Token sieht diesen
Anteil **nicht** — das Modell liefert längst, die Anzeige wartet.

Deshalb trägt jede Messung beide Zahlen, wo sie zu haben sind, und die Differenz
als eigene Spalte. Eine Stoppuhr, die nur die Modellzeit kennt, hätte #51 nie
gefunden.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from statistics import median
from typing import Protocol

DEFAULT_REPEATS = 3
DEFAULT_WARMUP = 1

# So viel vom Anfang der Antwort wird behalten, um sie gegen die Fehlermeldung
# des Streamers zu halten. `stream()` fängt Backend-Fehler ab und liefert sie
# als Text aus — ein nicht erreichbares Ollama sieht sonst wie ein sehr
# schneller Lauf aus.
_HEAD_CHARS = 120


class BenchAborted(RuntimeError):
    """Der Lauf hat gar nicht erst angefangen — die erste Messung schlug fehl."""


@dataclass(frozen=True)
class Question:
    """Eine Frage mit stabiler ID, damit zwei Läufe zeilenweise vergleichbar sind."""

    id: str
    text: str


@dataclass(frozen=True)
class Sample:
    """Eine einzelne Messung: eine Frage, einmal gestellt."""

    persona: str
    question_id: str
    repeat: int
    warmup: bool
    t_first_ms: int | None
    t_total_ms: int
    chars: int
    t_model_first_ms: int | None
    tokens: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def chars_per_second(self) -> float | None:
        """Durchsatz ab dem ersten ausgelieferten Zeichen.

        Bewusst nicht ab Anfragebeginn gerechnet: sonst steckt die Anlaufzeit
        im Durchsatz, und ein langsamer Start sähe wie ein langsames Modell aus.
        """
        if self.t_first_ms is None or self.chars <= 0:
            return None
        streaming_ms = self.t_total_ms - self.t_first_ms
        if streaming_ms <= 0:
            return None
        return self.chars / (streaming_ms / 1000)

    @property
    def holdback_ms(self) -> int | None:
        """Was der Aufrufer *zusätzlich* zur Modelllatenz wartet."""
        if self.t_first_ms is None or self.t_model_first_ms is None:
            return None
        return self.t_first_ms - self.t_model_first_ms


class Driver(Protocol):
    """Woher die Tokens kommen — in-process oder über HTTP."""

    mode: str

    def stream(self, persona: str, question: str) -> Iterator[str]: ...

    def model_stats(self) -> tuple[int | None, int | None]:
        """(t_first_ms, tokens) des letzten Streams, soweit der Weg sie kennt."""
        ...


def measure(
    driver: Driver,
    persona: str,
    question: Question,
    *,
    repeat: int,
    warmup: bool = False,
    error_marker: str | None = None,
) -> Sample:
    """Stellt eine Frage und stoppt die Zeit bis zum ersten und letzten Zeichen."""
    started = time.perf_counter()
    first_at: float | None = None
    chars = 0
    head = ""
    error: str | None = None

    # Der Aufbau gehört mit in den try: `HttpDriver.stream` schickt die Anfrage
    # bereits ab und prüft den Status, ein 500er käme also, *bevor* das erste
    # Zeichen fällig ist. Draußen gelassen riss er den ganzen Lauf ab, statt
    # eine fehlgeschlagene Messung zu werden.
    stream: Iterator[str] | None = None
    try:
        stream = driver.stream(persona, question.text)
        for piece in stream:
            if not piece:
                continue
            if first_at is None:
                first_at = time.perf_counter()
            chars += len(piece)
            if len(head) < _HEAD_CHARS:
                head += piece
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        # Wie überall im Projekt: Generatoren werden geschlossen, nicht dem GC
        # überlassen — sonst läuft der Backend-Stream weiter.
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    ended = time.perf_counter()

    if error is None and error_marker and head.startswith(error_marker):
        # Der Streamer liefert Backend-Fehler als Text aus. Ohne diese Prüfung
        # wäre ein totes Backend die schnellste Messung des ganzen Laufs.
        error = "Backend lieferte die Fehlermeldung des Streamers"

    t_model_first_ms, tokens = driver.model_stats()
    return Sample(
        persona=persona,
        question_id=question.id,
        repeat=repeat,
        warmup=warmup,
        t_first_ms=None if first_at is None else int((first_at - started) * 1000),
        t_total_ms=int((ended - started) * 1000),
        chars=chars,
        t_model_first_ms=t_model_first_ms,
        tokens=tokens,
        error=error,
    )


def run_bench(
    driver: Driver,
    personas: Sequence[str],
    questions: Sequence[Question],
    *,
    repeats: int = DEFAULT_REPEATS,
    warmup: int = DEFAULT_WARMUP,
    error_marker: str | None = None,
    on_sample: Callable[[Sample], None] | None = None,
) -> list[Sample]:
    """Fährt den Messplan ab und liefert alle Messungen, Aufwärmrunden inklusive.

    **Die Reihenfolge ist Teil der Methode.** Gemessen wird rundenweise
    (Runde 1: alle Fragen, Runde 2: alle Fragen …), nicht fragenweise. Läuft die
    Maschine im Verlauf warm oder kommt Last dazu, verteilt sich das dann
    gleichmäßig über alle Fragen, statt genau die zu treffen, die zufällig
    hinten steht.

    Die Aufwärmrunden bleiben in der Liste und werden nicht stillschweigend
    weggeworfen: der Kaltstart (Modell in den VRAM laden) ist eine eigene,
    interessante Zahl — sie darf nur nicht in den Median rutschen. Ob sie
    *wirklich* einen Kaltstart zeigt, weiß der Harness allerdings nicht: hielt
    `keep_alive` das Modell von einem Lauf davor noch im Speicher, ist die
    Aufwärmrunde eine gewöhnliche Messung. Gemessen am selben Nachmittag:
    30,7 s kalt gegen 0,9 s bei geladenem Modell. Der Report sagt das dazu,
    statt die Zahl als Kaltstart auszugeben.
    """
    if not personas or not questions:
        return []

    samples: list[Sample] = []

    def _record(sample: Sample) -> None:
        samples.append(sample)
        if on_sample is not None:
            on_sample(sample)
        # Nur die allererste Messung bricht ab: schlägt sie fehl, stimmt am
        # Aufbau etwas nicht (kein Modell, falscher Port), und die restlichen
        # Minuten wären vergeudet. Ein Fehler mittendrin ist dagegen ein Befund
        # und wird aufgezeichnet.
        if len(samples) == 1 and not sample.ok:
            raise BenchAborted(sample.error or "erste Messung fehlgeschlagen")

    for persona in personas:
        for round_no in range(warmup):
            _record(
                measure(
                    driver,
                    persona,
                    questions[0],
                    repeat=round_no + 1,
                    warmup=True,
                    error_marker=error_marker,
                )
            )

    for round_no in range(1, repeats + 1):
        for persona in personas:
            for question in questions:
                _record(
                    measure(
                        driver,
                        persona,
                        question,
                        repeat=round_no,
                        error_marker=error_marker,
                    )
                )

    return samples


def measured(samples: Sequence[Sample]) -> list[Sample]:
    """Die Messungen, die in die Statistik dürfen: ohne Aufwärmen, ohne Fehler."""
    return [s for s in samples if not s.warmup and s.ok]


def _median_int(values: Sequence[int | None]) -> int | None:
    usable = [v for v in values if v is not None]
    return int(median(usable)) if usable else None


def _median_float(values: Sequence[float | None]) -> float | None:
    usable = [v for v in values if v is not None]
    return float(median(usable)) if usable else None


@dataclass(frozen=True)
class Aggregate:
    """Zusammenfassung einer Gruppe von Messungen — Mediane, keine Mittelwerte.

    Der Median, weil ein einzelner Ausreißer (ein Hintergrundjob, ein
    nachladendes Modell) den Mittelwert einer Handvoll Läufe kippt, den Median
    aber nicht.
    """

    label: str
    runs: int
    t_first_ms: int | None
    t_total_ms: int | None
    chars: int | None
    chars_per_second: float | None
    holdback_ms: int | None


def aggregate(samples: Sequence[Sample], label: str) -> Aggregate:
    usable = measured(samples)
    return Aggregate(
        label=label,
        runs=len(usable),
        t_first_ms=_median_int([s.t_first_ms for s in usable]),
        t_total_ms=_median_int([s.t_total_ms for s in usable]),
        chars=_median_int([s.chars for s in usable]),
        chars_per_second=_median_float([s.chars_per_second for s in usable]),
        holdback_ms=_median_int([s.holdback_ms for s in usable]),
    )


def aggregate_by(
    samples: Sequence[Sample], key: Callable[[Sample], str]
) -> list[Aggregate]:
    """Gruppiert nach einem Schlüssel, in der Reihenfolge des ersten Auftretens."""
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        groups.setdefault(key(sample), []).append(sample)
    return [aggregate(group, label) for label, group in groups.items()]


@dataclass
class BenchRun:
    """Ein Lauf samt allem, was zwei Läufe vergleichbar macht."""

    started_at: str
    mode: str
    backend: str
    model: str
    repeats: int
    warmup: int
    settings: list[tuple[str, str]] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def overall(self) -> Aggregate:
        return aggregate(self.samples, "gesamt")

    @property
    def cold_start(self) -> Aggregate:
        """Die Aufwärmrunden für sich — der Preis des ersten Aufrufs.

        `aggregate` wirft Aufwärmrunden weg; für diese eine Auswertung werden
        sie deshalb umetikettiert, statt der Statistikfunktion einen Schalter
        zu geben, den sonst niemand benutzt.
        """
        warmups = [replace(s, warmup=False) for s in self.samples if s.warmup]
        return aggregate(warmups, "Kaltstart")

    @property
    def errors(self) -> list[Sample]:
        return [s for s in self.samples if not s.ok]
