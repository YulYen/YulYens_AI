from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from core.context_summarizer import KarlSummarizationError
from core.context_utils import (
    apply_heuristic_context_trim,
    apply_karl_context_summary,
    require_context_management_config,
    shrink_history_for_context,
)

HISTORY = [
    {"role": "system", "content": "Regeln"},
    {"role": "user", "content": "Alte Frage"},
    {"role": "assistant", "content": "Antwort"},
    {"role": "user", "content": "Neue Frage"},
]


def _cfg(strategy="heuristic", karl=None):
    karl_cfg = {
        "model": "same_as_chat",
        "summary_max_tokens": 512,
        "keep_last_messages": 2,
        "log_dir": "logs",
    }
    if karl:
        karl_cfg.update(karl)
    return SimpleNamespace(context_management={"strategy": strategy, "karl": karl_cfg})


def test_require_config_rejects_missing_section():
    with pytest.raises(ValueError, match="context_management"):
        require_context_management_config(SimpleNamespace())


def test_require_config_rejects_unknown_strategy():
    cfg = SimpleNamespace(context_management={"strategy": "yolo"})
    with pytest.raises(ValueError, match="heuristic.*karl"):
        require_context_management_config(cfg)


def test_require_config_rejects_incomplete_karl_section():
    cfg = SimpleNamespace(
        context_management={"strategy": "karl", "karl": {"model": "x"}}
    )
    with pytest.raises(ValueError, match="keep_last_messages"):
        require_context_management_config(cfg)


def test_heuristic_trim_uses_num_ctx():
    with patch(
        "core.context_utils.karl_prepare_quick_and_dirty",
        side_effect=lambda history, limit: history[1:],
    ) as mock_prepare:
        result = apply_heuristic_context_trim(
            HISTORY, {"num_ctx": "128"}, persona_name="LEAH"
        )

    assert mock_prepare.call_args[0][1] == 128
    assert result == HISTORY[1:]


def test_heuristic_trim_skips_without_num_ctx(caplog):
    caplog.set_level("WARNING")
    result = apply_heuristic_context_trim(HISTORY, {}, persona_name="LEAH")
    assert result == HISTORY
    assert "Skipping 'karl_prepare_quick_and_dirty'" in caplog.text


def test_heuristic_trim_skips_on_invalid_num_ctx(caplog):
    caplog.set_level("WARNING")
    result = apply_heuristic_context_trim(
        HISTORY, {"num_ctx": "viele"}, persona_name="LEAH"
    )
    assert result == HISTORY
    assert "Invalid 'num_ctx'" in caplog.text


def test_karl_summary_falls_back_to_heuristic_when_configured():
    karl_cfg = {
        "model": "same_as_chat",
        "summary_max_tokens": 512,
        "keep_last_messages": 2,
        "log_dir": "logs",
        "fallback_strategy": "heuristic",
    }
    with (
        patch("core.context_utils.KarlSummarizer") as mock_karl,
        patch(
            "core.context_utils.karl_prepare_quick_and_dirty",
            side_effect=lambda history, limit: history[1:],
        ),
    ):
        mock_karl.return_value.summarize.side_effect = KarlSummarizationError("boom")
        result = apply_karl_context_summary(
            HISTORY,
            karl_cfg,
            {"num_ctx": 128},
            llm_core=Mock(),
            chat_model_name="chat-model",
        )

    assert result == HISTORY[1:]


def test_karl_summary_reraises_without_fallback():
    karl_cfg = {
        "model": "same_as_chat",
        "summary_max_tokens": 512,
        "keep_last_messages": 2,
        "log_dir": "logs",
    }
    with patch("core.context_utils.KarlSummarizer") as mock_karl:
        mock_karl.return_value.summarize.side_effect = KarlSummarizationError("boom")
        with pytest.raises(KarlSummarizationError):
            apply_karl_context_summary(
                HISTORY,
                karl_cfg,
                {"num_ctx": 128},
                llm_core=Mock(),
                chat_model_name="chat-model",
            )


def test_shrink_dispatches_to_heuristic():
    with patch(
        "core.context_utils.apply_heuristic_context_trim",
        return_value=HISTORY[1:],
    ) as mock_trim:
        result = shrink_history_for_context(
            HISTORY,
            _cfg("heuristic"),
            {"num_ctx": 128},
            llm_core=None,
            chat_model_name="",
        )
    mock_trim.assert_called_once()
    assert result == HISTORY[1:]


def test_shrink_dispatches_to_karl():
    summary = [{"role": "system", "content": "Kurzfassung"}]
    with patch("core.context_utils.KarlSummarizer") as mock_karl:
        mock_karl.return_value.summarize.return_value = summary
        result = shrink_history_for_context(
            HISTORY,
            _cfg("karl"),
            {"num_ctx": 128},
            llm_core=Mock(),
            chat_model_name="chat-model",
        )
    mock_karl.assert_called_once()
    assert result == summary
