from pathlib import Path

from core.context_summarizer import KarlSummarizer


class _FakeLLMCore:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def stream_chat(self, model_name, messages, options=None, keep_alive=600):
        self.calls.append(
            {
                "model_name": model_name,
                "messages": messages,
                "options": options,
                "keep_alive": keep_alive,
            }
        )
        return iter(self.chunks)


def test_karl_summarize_reduces_history_and_keeps_tail(tmp_path):
    fake = _FakeLLMCore([{"message": {"content": "Kurzfassung"}}])
    cfg = {
        "model": "same_as_chat",
        "summary_max_tokens": 512,
        "keep_last_messages": 2,
        "log_dir": str(tmp_path),
    }
    summarizer = KarlSummarizer(fake, cfg, chat_model_name="chat-model")

    original = [
        {"role": "system", "content": "Regeln"},
        {"role": "user", "content": "Frage alt"},
        {"role": "assistant", "content": "Antwort alt"},
        {"role": "user", "content": "Frage neu"},
        {"role": "assistant", "content": "Antwort neu"},
    ]
    frozen = [m.copy() for m in original]

    result = summarizer.summarize(original)

    assert result == [
        {"role": "system", "content": "Kurzfassung"},
        {"role": "user", "content": "Frage neu"},
        {"role": "assistant", "content": "Antwort neu"},
    ]
    assert original == frozen
    assert fake.calls[0]["model_name"] == "chat-model"
    assert fake.calls[0]["options"] == {"num_predict": 512}


def test_karl_summarize_creates_daily_log_file(tmp_path):
    fake = _FakeLLMCore([{"message": {"content": "Zusammenfassung"}}])
    cfg = {
        "model": "karl-model",
        "summary_max_tokens": 256,
        "keep_last_messages": 1,
        "log_dir": str(tmp_path),
    }
    summarizer = KarlSummarizer(fake, cfg, chat_model_name="chat-model")

    result = summarizer.summarize(
        [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
        ]
    )

    assert result[0]["role"] == "system"
    log_files = list(Path(tmp_path).glob("karl_*.log"))
    assert len(log_files) == 1
    log_text = log_files[0].read_text(encoding="utf-8")
    assert "summarized=" in log_text
    assert "summary_chars=" in log_text
    assert "model=karl-model" in log_text
