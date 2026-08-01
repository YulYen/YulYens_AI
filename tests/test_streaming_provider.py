import json
import os
from datetime import datetime
from typing import Any

import pytest
from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider, _StreamModerator
from security.tinyguard import BasicGuard


class FakeTokenCore:
    """LLM core stub that emits a predefined sequence of tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    def stream_chat(self, **_kwargs: Any):
        for token in self._tokens:
            yield {"message": {"content": token}}

    def warm_up(self, *_args: Any, **_kwargs: Any) -> None:
        pass


class AllowAllGuard:
    """Minimal guard that allows every input and output."""

    def check_input(self, text: str) -> dict[str, Any]:
        return {"ok": True}

    def process_output(self, text: str) -> dict[str, Any]:
        return {"blocked": False, "text": text}

    def check_output(self, text: str) -> dict[str, Any]:
        return {"ok": True}

    def output_match_crossing(self, text: str, offset: int) -> int | None:
        # Nichts trifft zu, also läuft auch kein Treffer über die Freigabegrenze.
        return None


def create_streaming_provider(
    *, llm_core: DummyLLMCore | None = None, **overrides: Any
) -> YulYenStreamingProvider:
    """Helper to construct consistently configured provider instances."""

    params: dict[str, Any] = {
        "base_url": "http://dummy",
        "persona": "TEST",
        "persona_prompt": "Dies ist ein System-Prompt.",
        "persona_options": {},
        "model_name": "dummy-model",
    }
    params.update(overrides)

    if llm_core is not None:
        params["llm_core"] = llm_core
    else:
        params["llm_core"] = DummyLLMCore()

    return YulYenStreamingProvider(**params)


def test_dummy_llm_core_echoes_input() -> None:
    """The DummyLLMCore should deterministically echo the latest user input."""

    llm = DummyLLMCore()
    messages = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "Hallo Welt"},
    ]

    chunks = list(llm.stream_chat(model_name="any", messages=messages))

    assert len(chunks) == 1
    assert chunks[0]["message"]["content"] == "ECHO: Hallo Welt"


def test_streaming_provider_with_dummy_llm() -> None:
    """The StreamingProvider should work with an injected DummyLLMCore."""

    llm = DummyLLMCore()
    provider = create_streaming_provider(llm_core=llm)

    messages = [{"role": "user", "content": "Ping"}]
    out = list(provider.stream(messages))

    assert len(out) == 1
    assert "ECHO: Ping" in out[0]


class RecordingCore(FakeTokenCore):
    """FakeTokenCore that additionally records the stream_chat kwargs."""

    def __init__(self, tokens: list[str]) -> None:
        super().__init__(tokens)
        self.last_kwargs: dict[str, Any] = {}

    def stream_chat(self, **kwargs: Any):
        self.last_kwargs = kwargs
        return super().stream_chat(**kwargs)


def test_stream_forwards_configured_keep_alive() -> None:
    core = RecordingCore(["Hi"])
    provider = create_streaming_provider(llm_core=core, keep_alive=42)

    list(provider.stream([{"role": "user", "content": "Hallo"}]))

    assert core.last_kwargs["keep_alive"] == 42


def test_stream_defaults_keep_alive_to_600() -> None:
    core = RecordingCore(["Hi"])
    provider = create_streaming_provider(llm_core=core)

    list(provider.stream([{"role": "user", "content": "Hallo"}]))

    assert core.last_kwargs["keep_alive"] == 600


def test_streaming_writes_conversation_json_log(tmp_path) -> None:
    """Der JSONL-Mitschnitt ist seit #54 ein opt-in Debug-Artefakt."""
    log_file = tmp_path / f"conv_{datetime.now().strftime('%H%M%S')}.json"

    core = DummyLLMCore()
    provider = create_streaming_provider(
        llm_core=core,
        model_name="LEAH13B",
        persona="DORIS",
        persona_prompt="Du bist DORIS.",
        persona_options={"temperature": 0.2},
        log_file=log_file.name,
        guard=AllowAllGuard(),
        jsonl_log=True,
    )

    provider._logs_dir = str(tmp_path)
    provider.conversation_log_path = str(tmp_path / log_file.name)

    messages = [{"role": "user", "content": "Sag etwas Nettes."}]
    out = "".join(list(provider.stream(messages)))

    assert out == "ECHO: Sag etwas Nettes."
    assert os.path.exists(provider.conversation_log_path)

    rows = [
        json.loads(line)
        for line in open(provider.conversation_log_path, encoding="utf-8")
    ]
    roles = [row["role"] for row in rows]

    assert "user" in roles and "assistant" in roles
    assert any(
        row.get("bot") == "DORIS" and row.get("model") == "LEAH13B" for row in rows
    )


def test_secret_split_across_tokens_is_blocked() -> None:
    """A secret straddling token boundaries must never leak its prefix."""

    guard = BasicGuard(True, True, True, True)
    # "sk-" arrives first, the key body only completes two tokens later.
    core = FakeTokenCore(["Here is the key: sk-", "SECRETTOBLOCK", "123456789", " ok"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "key?"}]))

    assert "sk-" not in out
    assert "SECRETTOBLOCK" not in out
    # Der harmlose Text vor dem Secret darf beim Default-Holdback schon
    # sichtbar sein — entscheidend ist, dass vom Schlüssel nichts durchkommt
    # und die Blockmeldung erscheint.
    assert out.endswith(guard.texts["security_blocked_keyword"])


def test_email_split_across_tokens_is_masked() -> None:
    """An email split across token boundaries must be fully masked."""

    guard = BasicGuard(True, True, True, True)
    core = FakeTokenCore(["Contact: max.mustermann", "@example", ".org please"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "mail?"}]))

    assert "max.mustermann@example.org" not in out
    assert guard.mask_text in out
    assert out.startswith("Contact: ")


def test_email_after_long_prefix_still_masked() -> None:
    """Even with text beyond the holdback window, a later email is masked."""

    guard = BasicGuard(True, True, True, True)
    padding = "A" * 150
    core = FakeTokenCore(
        [f"{padding} contact ", "max.mustermann", "@example", ".org end"]
    )
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "mail?"}]))

    assert "max.mustermann@example.org" not in out
    assert guard.mask_text in out
    # The safe prefix is still delivered to the user.
    assert padding in out


def test_plain_text_streams_through_with_guard() -> None:
    """Benign multi-token output is delivered unchanged."""

    guard = BasicGuard(True, True, True, True)
    core = FakeTokenCore(["Hello ", "there, ", "how are ", "you?"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "hi"}]))

    assert out == "Hello there, how are you?"


# ---- Holdback vs. wahrgenommene Latenz (#51) --------------------------------


class CountingTokenCore(FakeTokenCore):
    """Zählt mit, wie viele Tokens das Modell bis jetzt geliefert hat."""

    def __init__(self, tokens: list[str]) -> None:
        super().__init__(tokens)
        self.consumed = 0

    def stream_chat(self, **_kwargs: Any):
        for token in self._tokens:
            self.consumed += 1
            yield {"message": {"content": token}}


def _tokens_until_first_output(provider, core) -> int:
    for chunk in provider.stream([{"role": "user", "content": "frage?"}]):
        if chunk:
            return core.consumed
    return -1


def test_holdback_delays_the_first_visible_output() -> None:
    """Belegt die Ursache aus #51: vor `holdback` Zeichen geht nichts raus.

    Mit 6-Zeichen-Tokens braucht es 96/6 = 16 Tokens, bis überhaupt etwas an die
    Anzeige geht. Bei den 4 Tokens/s des Messaufbaus waren das die gemessenen
    ~4 s bis zum ersten sichtbaren Wort im Browser.
    """
    core = CountingTokenCore(["Wort%d " % i for i in range(1, 40)])
    provider = create_streaming_provider(
        llm_core=core, guard=BasicGuard(True, True, True, True)
    )

    # Default-Holdback 32, Tokens à 6 Zeichen -> rund 6 Tokens Vorlauf.
    assert _tokens_until_first_output(provider, core) >= 5


def test_without_holdback_the_first_token_goes_out_at_once() -> None:
    core = CountingTokenCore(["Wort%d " % i for i in range(1, 40)])
    provider = create_streaming_provider(
        llm_core=core, guard=BasicGuard(True, True, True, True)
    )
    provider.set_stream_holdback(0)

    assert _tokens_until_first_output(provider, core) == 1


def test_holdback_override_lets_the_first_token_through_immediately() -> None:
    guard = BasicGuard(True, True, True, True)
    core = FakeTokenCore(["Hallo ", "Welt ", "und ", "so"])
    provider = create_streaming_provider(llm_core=core, guard=guard)
    provider.set_stream_holdback(0)

    chunks = [c for c in provider.stream([{"role": "user", "content": "f?"}]) if c]

    assert chunks[0] == "Hallo "


def test_holdback_override_rejects_garbage_and_keeps_the_default() -> None:
    provider = create_streaming_provider(llm_core=FakeTokenCore(["x"]))

    provider.set_stream_holdback("keine Zahl")

    assert provider.stream_holdback == 32
    provider.set_stream_holdback(-5)
    assert provider.stream_holdback == 0


def test_no_holdback_when_no_output_check_is_active() -> None:
    """Ohne PII-Maskierung und ohne Blocklist gibt es nichts zurückzuhalten.

    Der Straddle-Schutz kostete in dieser Konstellation nur Latenz.
    """
    guard = BasicGuard(
        enabled=True,
        prompt_injection_protection=True,
        pii_protection=False,
        output_blocklist=False,
        wrongdoing_protection=True,
    )
    core = FakeTokenCore(["Hallo ", "Welt"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    chunks = [c for c in provider.stream([{"role": "user", "content": "f?"}]) if c]

    assert chunks[0] == "Hallo "


def test_output_blocklist_alone_keeps_the_holdback() -> None:
    """Umkehrprobe: ist die Blocklist an, bleibt der Schutz aktiv."""
    guard = BasicGuard(
        enabled=True,
        prompt_injection_protection=True,
        pii_protection=False,
        output_blocklist=True,
        wrongdoing_protection=True,
    )
    core = FakeTokenCore(["Hier: sk-", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", " fertig"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "key?"}]))

    assert "sk-" not in out


def test_default_holdback_keeps_key_material_hidden() -> None:
    """Warum der Default 32 ist und nicht kleiner.

    Das längste Muster der Blocklist (AWS-Secret-Heuristik) schlägt erst an,
    wenn Label plus 30 Zeichen Schlüsselmaterial da sind. Bis dahin gibt der
    Moderator alles frei, was weiter als `holdback` zurückliegt. Erst ab einem
    Holdback von 30 bleibt das Schlüsselmaterial selbst vollständig verdeckt —
    32 liegt knapp darüber. Wird der Default je darunter gesetzt, schlägt dieser
    Test an.
    """
    guard = BasicGuard(True, True, True, True)
    block_message = guard.texts["security_blocked_keyword"]
    label = "aws_secret_access_key = "
    key_material = "aB3/xY9+" * 5

    core = FakeTokenCore(
        [
            (label + key_material)[i : i + 4]
            for i in range(0, len(label + key_material), 4)
        ]
    )
    provider = create_streaming_provider(llm_core=core, guard=guard)

    emitted = [
        chunk
        for chunk in provider.stream([{"role": "user", "content": "key?"}])
        if chunk != block_message
    ]
    leaked = "".join(emitted)

    # Vom Label darf beim schnellen Default etwas sichtbar werden …
    assert len(leaked) <= len(label)
    # … vom Schlüssel selbst nichts.
    assert not any(part in leaked for part in (key_material[:8], key_material[8:16]))


def test_raising_the_holdback_hides_even_the_label() -> None:
    """Gegenprobe: 96 verdeckt auch den Kontext um das Secret herum."""
    guard = BasicGuard(True, True, True, True)
    block_message = guard.texts["security_blocked_keyword"]
    secret = "aws_secret_access_key = " + "aB3/xY9+" * 5

    core = FakeTokenCore([secret[i : i + 4] for i in range(0, len(secret), 4)])
    provider = create_streaming_provider(llm_core=core, guard=guard)
    provider.set_stream_holdback(96)

    leaked = "".join(
        chunk
        for chunk in provider.stream([{"role": "user", "content": "key?"}])
        if chunk != block_message
    )

    assert leaked == ""


def test_conversation_log_carries_the_user(tmp_path, monkeypatch):
    """#53: der Nutzer steht in jeder Zeile — hier über den Debug-Mitschnitt."""
    from core.streaming_provider import YulYenStreamingProvider

    provider = YulYenStreamingProvider(
        base_url="",
        model_name="m",
        persona="LEAH",
        persona_prompt="p",
        persona_options={},
        log_file="conv.json",
        llm_core=None,
        jsonl_log=True,
    )
    monkeypatch.setattr(provider, "conversation_log_path", str(tmp_path / "conv.json"))

    # Ohne Anmeldung (Terminal, API) ist der lokale Nutzer die ehrliche Antwort.
    provider._append_jsonl("user", "erste")
    provider.set_user("yulyen")
    provider._append_jsonl("user", "zweite")

    lines = [
        json.loads(line)
        for line in (tmp_path / "conv.json").read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["user"] for entry in lines] == ["local", "yulyen"]


def test_set_user_falls_back_instead_of_writing_an_empty_name(tmp_path, monkeypatch):
    from core.streaming_provider import YulYenStreamingProvider

    provider = YulYenStreamingProvider(
        base_url="",
        model_name="m",
        persona="LEAH",
        persona_prompt="p",
        persona_options={},
        log_file="conv.json",
        llm_core=None,
    )
    provider.set_user("   ")

    assert provider.user == "local"


# ---- Der Eingangs-Check des Guards steht nur noch einmal --------------------


class _BlockAllGuard:
    """Guard, der jede Eingabe ablehnt — mit dem Vertrag von BasicGuard."""

    texts = {"security_blocked_keyword": "Nö."}

    def check_input(self, text: str) -> dict[str, Any]:
        return {"ok": False, "reason": "blocked_keyword", "detail": text[:10]}

    def process_output(self, text: str) -> dict[str, Any]:
        return {"blocked": False, "text": text}

    def check_output(self, text: str) -> dict[str, Any]:
        return {"ok": True}


def test_stream_and_one_shot_refuse_the_same_way() -> None:
    """Beide Pfade prüften die Eingabe getrennt — jetzt über dieselbe Methode.

    Der Test hält fest, was daran zählt: dieselbe Eingabe führt in beiden
    Einstiegen zur identischen Absage, statt dass eine Änderung nur an einer
    Stelle ankommt.
    """
    from wiki.lookup import WikiLookup

    provider = create_streaming_provider(guard=_BlockAllGuard())

    streamed = "".join(
        provider.stream(messages=[{"role": "user", "content": "verbotene Frage"}])
    )
    one_shot = provider.respond_one_shot(
        "verbotene Frage", persona="TEST", wiki=WikiLookup()
    )

    assert streamed == one_shot
    assert "Nö." in streamed


def test_without_a_guard_nothing_is_refused() -> None:
    provider = create_streaming_provider()

    assert provider._input_refusal("beliebige Frage", "TEST") is None


# ---- Maskierung *während* des Streams (#58) ---------------------------------
#
# Das Gerüst, das bisher fehlte. `test_default_holdback_keeps_key_material_hidden`
# deckt nur den Blocklist-Pfad ab — der blockt ganz oder gar nicht und ändert
# deshalb nie die Textlänge. Die Maskierung tut genau das, und daran zerbrach die
# Index-Rechnung im Moderator.

_MASK_TEXTS = {
    "security_mask_text": "[PII]",
    "security_prompt_injection": "inj {detail}",
    "security_pii_detected": "pii",
    "security_blocked_keyword": "SECRET-BLOCKED",
    "security_wrongdoing": "no",
    "security_all_clear": "ok",
}
_MASK = "[PII]"


def _masking_guard():
    return BasicGuard(
        enabled=True,
        prompt_injection_protection=True,
        pii_protection=True,
        output_blocklist=True,
        wrongdoing_protection=True,
        texts=_MASK_TEXTS,
    )


def _stream_through(text, *, chunk, holdback):
    """Fährt den Text in Häppchen durch den Moderator und sammelt die Ausgabe."""
    moderator = _StreamModerator(_masking_guard(), _MASK_TEXTS, holdback=holdback)
    out = []
    for i in range(0, len(text), chunk):
        out.extend(moderator.feed(text[i : i + chunk]))
    out.extend(moderator.flush())
    return "".join(out), moderator


def _assert_nothing_lost_or_duplicated(served, raw):
    """Der Kern: außer Maskiertem darf nichts fehlen und nichts doppelt sein.

    Geprüft wird, dass sich die ausgelieferten Teilstücke der Reihe nach und
    überschneidungsfrei im Originaltext wiederfinden — von vorn beginnend, bis
    ans Ende. Genau das war kaputt: `_emitted` zeigte in den *maskierten* Text,
    und nach einem Treffer sprang der Index, sodass „und dann noch" verschwand.
    """
    cursor = 0
    parts = served.split(_MASK)
    for index, part in enumerate(parts):
        if not part:
            continue
        found = raw.find(part, cursor)
        assert found >= 0, f"{part!r} steht so gar nicht im Modelltext"
        if index == 0:
            assert found == 0, f"Der Anfang fehlt: {served!r}"
        cursor = found + len(part)
    if not served.endswith(_MASK):
        assert cursor == len(raw), f"Das Ende fehlt: {served!r}"


# (Text, Länge des längsten Ausgangs-Treffers darin)
_MASKING_TEXTS = [
    ("Melde dich bei max.mustermann@example.com und dann noch viel Text danach.", 26),
    ("Kurz: a@b.de ENDE", 6),
    ("Zwei: erste.person@example.org und zweite.person@example.org, fertig.", 25),
    (
        "Sehr lange Adresse vorname.nachname.abteilung@sehr-lange-firmendomain."
        "example.com und dann noch viel Text hinterher damit es reicht.",
        62,
    ),
    ("Ruf an unter 0151 23456789 bitte.", 13),
    ("Gar nichts Besonderes hier, nur Fließtext ohne jeden Treffer.", 0),
    ("PII ganz am Ende: kontakt@example.com", 19),
]


@pytest.mark.parametrize("text, longest_match", _MASKING_TEXTS)
@pytest.mark.parametrize("chunk", [1, 3, 4, 7, 50])
@pytest.mark.parametrize("holdback", [0, 8, 32, 96])
def test_streaming_never_loses_or_duplicates_model_text(
    text, longest_match, chunk, holdback
):
    """Gilt immer — unabhängig davon, wie das Modell die Tokens schneidet."""
    served, _moderator = _stream_through(text, chunk=chunk, holdback=holdback)

    _assert_nothing_lost_or_duplicated(served, text)


@pytest.mark.parametrize("text, longest_match", _MASKING_TEXTS)
@pytest.mark.parametrize("chunk", [1, 3, 4, 7, 50])
@pytest.mark.parametrize("holdback", [32, 96])
def test_streaming_masks_exactly_like_one_shot_when_the_holdback_covers_it(
    text, longest_match, chunk, holdback
):
    """Deckt der Holdback das Muster ab, muss gestreamt dasselbe herauskommen.

    Die Einschränkung ist der dokumentierte Vertrag: „patterns longer than this
    window can still leak their prefix" (siehe `_STREAM_HOLDBACK_CHARS`). Für
    alles, was hineinpasst, gibt es dafür keine Ausrede.
    """
    if longest_match > holdback:
        pytest.skip(f"Muster ({longest_match}) länger als der Holdback ({holdback})")

    served, _moderator = _stream_through(text, chunk=chunk, holdback=holdback)

    assert served == _masking_guard().process_output(text)["text"]


def test_masked_flag_is_reported_to_the_caller():
    _served, moderator = _stream_through("Kurz: a@b.de ENDE", chunk=2, holdback=8)

    assert moderator.masked is True


def test_secret_still_blocks_and_hides_the_key_material():
    """Die Blocklist blockt weiterhin — und das Schlüsselmaterial bleibt verdeckt.

    Bewusst nicht „gar nichts wurde ausgeliefert": Text *vor* dem Treffer darf
    schon draußen sein, das ist seit jeher so (siehe
    `test_default_holdback_keeps_key_material_hidden`).
    """
    label = "aws_secret_access_key = "
    key_material = "aB3/xY9+" * 5
    served, moderator = _stream_through(label + key_material, chunk=4, holdback=32)

    assert moderator.blocked is True
    assert served.endswith("SECRET-BLOCKED")
    assert key_material[:8] not in served


def test_moderation_cost_stays_linear_in_the_answer_length():
    """Der Guard darf nicht mit dem Quadrat der Antwortlänge wachsen.

    Vorher lief `process_output` pro Token über den *gesamten* bisherigen Text:
    4× so viele Tokens kosteten 15,7× so viel Zeit — mit der ausgelieferten
    Config 1.605 ms reine CPU auf 16.000 Zeichen, auf dem yieldenden Thread und
    im parallelen Broadcast viermal gleichzeitig gegen dieselbe GIL.

    Gemessen wird bewusst das *Verhältnis* und nicht die absolute Zeit: absolute
    Schranken flackern auf unterschiedlich schnellen Runnern, das Wachstum nicht.
    """
    import time

    def _cpu_for(n_tokens):
        satz = "Das ist ein ganz normaler Satz ohne jeden Treffer darin. "
        text = (satz * ((n_tokens * 4) // len(satz) + 2))[: n_tokens * 4]
        tokens = [text[i : i + 4] for i in range(0, len(text), 4)]
        moderator = _StreamModerator(_masking_guard(), _MASK_TEXTS, holdback=32)
        started = time.perf_counter()
        for token in tokens:
            moderator.feed(token)
        moderator.flush()
        return time.perf_counter() - started

    klein = _cpu_for(500)
    gross = _cpu_for(4000)  # 8× so viele Tokens

    # Linear wäre Faktor 8, quadratisch ~64. Großzügige Schranke gegen Rauschen,
    # aber weit unter dem alten Verhalten.
    assert gross < klein * 20, (
        f"Moderation wächst überproportional: {klein * 1000:.0f} ms → "
        f"{gross * 1000:.0f} ms bei 8× Tokens"
    )
