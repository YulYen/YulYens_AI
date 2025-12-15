from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


_REQUIRED_META_KEYS: set[str] = {"created_at", "model", "persona", "app"}


def load_conversation(path: str):
    target = Path(path).expanduser()
    try:
        raw_content = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - trivial branch
        raise FileNotFoundError(f"Conversation file '{target}' not found.") from exc
    except OSError as exc:  # pragma: no cover - trivial branch
        detail = exc.strerror or str(exc)
        raise OSError(f"Could not read conversation file '{target}': {detail}") from exc

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Conversation file '{target}' contains invalid JSON: {exc.msg}."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Conversation file must contain an object with 'meta' and 'messages'.")

    meta = data.get("meta")
    messages = data.get("messages")

    _validate_meta(meta)
    validated_messages = _validate_messages(messages)

    return meta, validated_messages


def save_conversation(path: str, meta: dict, messages: list[dict]) -> None:
    if not isinstance(meta, dict):
        raise ValueError("meta must be a dictionary with conversation metadata.")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list of message objects.")

    payload = {"meta": meta, "messages": messages}
    target = Path(path).expanduser()
    try:
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:  # pragma: no cover - trivial branch
        detail = exc.strerror or str(exc)
        raise OSError(f"Could not save conversation to '{target}': {detail}") from exc


def _validate_meta(meta: dict | None) -> None:
    if not isinstance(meta, dict):
        raise ValueError("Conversation file is missing required object 'meta'.")

    missing_keys = [key for key in _REQUIRED_META_KEYS if key not in meta]
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Conversation metadata is missing required fields: {missing}.")

    for key in _REQUIRED_META_KEYS:
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Conversation metadata field '{key}' must be a non-empty string.")


def _validate_messages(messages: Iterable | None) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        raise ValueError("Conversation file is missing required list 'messages'.")

    validated: list[dict[str, str]] = []
    for idx, item in enumerate(messages, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Message #{idx} must be an object with string fields 'role' and 'content'."
            )

        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ValueError(
                f"Message #{idx} must contain string fields 'role' and 'content'."
            )

        validated.append({"role": role, "content": content})

    return validated
