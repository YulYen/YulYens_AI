from unittest.mock import Mock

from ui import self_talk
from ui.self_talk import SelfTalkRunner, is_end_of_self_talk

from tests.doubles import factory_double, streamer_double


def test_is_end_of_self_talk_recognizes_tokens():
    assert is_end_of_self_talk("... _endegelaende_")
    assert is_end_of_self_talk("done _ende_")
    assert not is_end_of_self_talk("weiter")


def test_self_talk_runner_alternates_histories():
    factory = factory_double()
    streamer_a = streamer_double()
    streamer_b = streamer_double()
    streamer_a.stream.return_value = iter(["Antwort A"])
    streamer_b.stream.return_value = iter(["Antwort B _endegelaende_"])
    factory.get_streamer_for_orchestra.side_effect = [streamer_a, streamer_b]

    class _Texts:
        @staticmethod
        def format(_key, **kwargs):
            return f"{kwargs['persona_self']}:{kwargs['task']}"

    runner = SelfTalkRunner(factory, _Texts(), "Karl", "Yul", "Start")

    p1, r1, stop1, _ = runner.run_turn()
    p2, r2, stop2, _ = runner.run_turn()

    assert p1 == "Karl"
    assert r1 == "Antwort A"
    assert not stop1
    assert p2 == "Yul"
    assert r2 == "Antwort B _endegelaende_"
    assert stop2
    assert runner.history_a[-1] == {
        "role": "user",
        "content": "Antwort B _endegelaende_",
    }


class _Catalog(dict):
    """Minimal stand-in for the Texts catalog (mapping + .format)."""

    def format(self, _key, **kwargs):
        return f"Guardrail für {kwargs['persona_self']}: {kwargs['task']}"


def _terminal_run_fixture(monkeypatch, replies_b):
    texts = _Catalog(terminal_self_talk_title="== AI Dialog ==")
    config = Mock(texts=texts)

    factory = factory_double()
    streamer_a = streamer_double()
    streamer_b = streamer_double()
    streamer_a.stream.side_effect = lambda messages: iter(["Hallo von A"])
    streamer_b.stream.side_effect = lambda messages: iter(replies_b)
    factory.get_streamer_for_orchestra.side_effect = [streamer_a, streamer_b]

    personas = iter(["Karl", "Yul"])
    monkeypatch.setattr(self_talk, "_choose_persona", lambda t, key: next(personas))
    monkeypatch.setattr(self_talk, "_prompt_initial", lambda t: "Startthema")

    terminal_ui = Mock()
    return config, factory, terminal_ui


def test_terminal_self_talk_run_stops_on_end_token(monkeypatch, capsys):
    config, factory, terminal_ui = _terminal_run_fixture(
        monkeypatch, replies_b=["Tschüss _ende_"]
    )

    self_talk.run(factory, config, terminal_ui)

    out = capsys.readouterr().out
    assert "== AI Dialog ==" in out
    assert "Hallo von A" in out
    assert "Tschüss _ende_" in out
    # One TTS call per completed turn
    assert terminal_ui._maybe_create_tts_wav.call_count == 2


def test_terminal_self_talk_run_handles_keyboard_interrupt(monkeypatch, capsys):
    config, factory, terminal_ui = _terminal_run_fixture(monkeypatch, replies_b=[])

    def _interrupt(messages):
        raise KeyboardInterrupt

    factory.get_streamer_for_orchestra.side_effect = None
    streamer = streamer_double()
    streamer.stream.side_effect = _interrupt
    factory.get_streamer_for_orchestra.return_value = streamer

    self_talk.run(factory, config, terminal_ui)

    out = capsys.readouterr().out
    assert "Stopping AI Dialog." in out


def test_self_talk_leaves_no_trace_in_the_store(tmp_path):
    """Der AI-Dialog zeichnet nicht auf — entschieden am 2026-11-10 (#77).

    Er erzeugt ein Artefakt, kein Nutzergespräch: der Nutzer steuert nur den
    Startprompt bei. Wer ihn behalten will, nimmt den Datei-Export.
    """
    from core.dummy_llm_core import DummyLLMCore
    from core.streaming_provider import YulYenStreamingProvider
    from storage import SqliteStore

    store = SqliteStore(tmp_path / "conversations.sqlite3")

    def _streamer(persona):
        provider = YulYenStreamingProvider(
            base_url="",
            persona=persona,
            persona_prompt="",
            persona_options={},
            model_name="dummy",
            llm_core=DummyLLMCore(),
            store=store,
        )
        return provider

    factory = factory_double()
    factory.get_streamer_for_orchestra.side_effect = lambda p: _streamer(p)
    factory.open_conversation.side_effect = lambda persona, app, user="local": (
        store.start(user=user, persona=persona, model="dummy", app=app)
    )

    class _StoreTexts:
        @staticmethod
        def format(_key, **kwargs):
            return f"{kwargs['persona_self']}:{kwargs['task']}"

    runner = SelfTalkRunner(factory, _StoreTexts(), "Karl", "Yul", "Start")
    runner.run_turn()

    assert runner.history_a[-1]["role"] == "assistant"
    assert store.list_conversations() == []
    factory.open_conversation.assert_not_called()
