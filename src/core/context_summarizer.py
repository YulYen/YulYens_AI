from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class KarlSummarizationError(RuntimeError):
    """Raised when Karl cannot summarize the current conversation."""


class KarlSummarizer:
    """Pure service for context compression via an LLM summary."""

    def __init__(
        self,
        llm_core,
        config: dict[str, Any],
        chat_model_name: str,
    ) -> None:
        self._llm_core = llm_core
        self._chat_model_name = chat_model_name
        self._model_name = self._resolve_model_name(config)
        self._summary_max_tokens = self._require_positive_int(
            config, "summary_max_tokens"
        )
        self._keep_last_messages = self._require_non_negative_int(
            config, "keep_last_messages"
        )
        self._log_dir = self._require_non_empty_str(config, "log_dir")

    def summarize(self, messages: list[dict]) -> list[dict]:
        items = [dict(message) for message in messages]
        if len(items) <= self._keep_last_messages:
            return items

        split_index = len(items) - self._keep_last_messages
        history = items[:split_index]
        tail = items[split_index:]

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Compress the conversation history precisely. "
                    "Preserve facts, open tasks, constraints, decisions, and unresolved questions. "
                    "Do not invent content. Keep it concise and actionable."
                ),
            },
            {
                "role": "user",
                "content": self._format_history(history),
            },
        ]

        try:
            stream = self._llm_core.stream_chat(
                model_name=self._model_name,
                messages=prompt_messages,
                options={"num_predict": self._summary_max_tokens},
                keep_alive=600,
            )
            summary = "".join(
                chunk.get("message", {}).get("content", "") for chunk in stream
            ).strip()
        except Exception as exc:
            raise KarlSummarizationError(
                f"Karl summarization failed with model '{self._model_name}'."
            ) from exc

        if not summary:
            raise KarlSummarizationError(
                f"Karl summarization returned an empty summary with model '{self._model_name}'."
            )

        self._append_log_entry(len(history), len(summary), self._model_name)

        return [{"role": "system", "content": summary}, *tail]

    def _append_log_entry(
        self, summarized_count: int, summary_length: int, model_name: str
    ) -> None:
        Path(self._log_dir).mkdir(parents=True, exist_ok=True)
        log_file = Path(self._log_dir) / f"karl_{datetime.now().strftime('%Y-%m-%d')}.log"
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{timestamp} summarized={summarized_count} summary_chars={summary_length} model={model_name}\n"
            )

    def _resolve_model_name(self, config: dict[str, Any]) -> str:
        model_name = self._require_non_empty_str(config, "model")
        if model_name == "same_as_chat":
            return self._chat_model_name
        return model_name

    @staticmethod
    def _format_history(messages: list[dict]) -> str:
        lines: list[str] = []
        for message in messages:
            role = str(message.get("role", "unknown")).upper()
            content = str(message.get("content", "")).strip()
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _require_non_empty_str(config: dict[str, Any], key: str) -> str:
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"context_management.karl.{key} must be a non-empty string."
            )
        return value.strip()

    @staticmethod
    def _require_positive_int(config: dict[str, Any], key: str) -> int:
        value = config.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"context_management.karl.{key} must be a positive integer."
            )
        return value

    @staticmethod
    def _require_non_negative_int(config: dict[str, Any], key: str) -> int:
        value = config.get(key)
        if not isinstance(value, int) or value < 0:
            raise ValueError(
                f"context_management.karl.{key} must be a non-negative integer."
            )
        return value
