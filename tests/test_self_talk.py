from unittest.mock import Mock

from ui.self_talk import SelfTalkRunner, is_end_of_self_talk


def test_is_end_of_self_talk_recognizes_tokens():
    assert is_end_of_self_talk("... _endegelaende_")
    assert is_end_of_self_talk("done _ende_")
    assert not is_end_of_self_talk("weiter")


def test_self_talk_runner_alternates_histories():
    factory = Mock()
    streamer_a = Mock()
    streamer_b = Mock()
    streamer_a.stream.return_value = iter(["Antwort A"])
    streamer_b.stream.return_value = iter(["Antwort B _endegelaende_"])
    factory.get_streamer_for_persona.side_effect = [streamer_a, streamer_b]

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
    assert runner.history_a[-1] == {"role": "user", "content": "Antwort B _endegelaende_"}
