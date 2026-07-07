"""
Streaming provider with persona handling, logging, and safety checks.

All direct calls to the underlying LLM are abstracted through an
``LLMCore`` (e.g. ``OllamaLLMCore`` or ``DummyLLMCore``).
This class takes care of prompt injection, logging (conversation JSON log),
and optional output moderation via SecurityGuard.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterator, Mapping
from typing import Any

from config.config_singleton import Config
from security.tinyguard import BasicGuard, zeigefinger_message
from wiki.lookup import inject_wiki_context, lookup_wiki_snippet

from core.context_utils import approx_token_count
from core.utils import ensure_dir_exists, is_ollama_module_not_found

# Import the LLM interface
from .llm_core import LLMCore

# Parallel broadcasts can hand several streamers the same second-resolution
# log file name; serialize appends so concurrent entries never interleave.
_conversation_log_lock = threading.Lock()


def _get_config() -> Config:
    """Returns the current config singleton instance."""
    return Config()


def _log_flag(name: str, default: bool = False) -> bool:
    """Reads a boolean switch from the `logging:` config section (best effort)."""
    try:
        return bool(_get_config().logging.get(name, default))
    except (AttributeError, KeyError, TypeError):
        # logging section missing or not a mapping
        return default


def _render_prompt_trace(
    persona: str, model: str, messages: list[dict[str, Any]], max_chars: int = 1200
) -> str:
    """Renders the final message list (incl. injected wiki snippets) human-readably."""
    lines = [f"[PROMPT TRACE] persona={persona} model={model} messages={len(messages)}"]
    for idx, m in enumerate(messages, start=1):
        role = m.get("role", "?")
        content = m.get("content") or ""
        if len(content) > max_chars:
            content = f"{content[:max_chars]}…(+{len(content) - max_chars} chars)"
        lines.append(
            f"  [{idx}] {role} ({len(m.get('content') or '')} chars): {content}"
        )
    return "\n".join(lines)


# Number of trailing characters held back while streaming so that a PII or
# secret pattern split across token boundaries is still detected before any
# part of it reaches the user. Best-effort: patterns longer than this window
# can still leak their prefix, so keep it above the longest blocklist match.
_STREAM_HOLDBACK_CHARS = 96


class _StreamModerator:
    """
    Applies the output guard to a *growing* response instead of to isolated
    token batches.

    The guard masks PII and blocks secrets, but those patterns can straddle
    token boundaries (e.g. ``"jo" + "hn@example" + ".com"``). Checking each
    batch in isolation therefore lets prefixes slip through. This helper keeps
    the full accumulated text, re-runs the guard on it, and only releases the
    portion that lies more than ``holdback`` characters behind the streaming
    frontier — the region a still-forming pattern can no longer reach.
    """

    def __init__(
        self,
        guard: BasicGuard | None,
        guard_texts: Mapping[str, str] | None,
        holdback: int = _STREAM_HOLDBACK_CHARS,
    ) -> None:
        self.guard = guard
        self.guard_texts = guard_texts
        self.holdback = holdback
        self.blocked = False
        self.masked = False
        self._acc = ""
        self._emitted = 0

    def _block_message(self, reason: str | None) -> str:
        self.blocked = True
        return zeigefinger_message(
            {"reason": reason or "blocked_keyword", "detail": ""},
            texts=self.guard_texts,
        )

    def feed(self, token: str) -> list[str]:
        """Consume one token; return the chunks that are now safe to emit."""
        if self.blocked or not token:
            return []
        self._acc += token

        # No guard: nothing to moderate, stream the token straight through.
        if self.guard is None:
            self._emitted += len(token)
            return [token]

        pol = self.guard.process_output(self._acc)
        if pol["blocked"]:
            return [self._block_message(pol.get("reason"))]

        self.masked = self.masked or bool(pol.get("masked"))
        masked = pol["text"]
        safe_upto = len(masked) - self.holdback
        if safe_upto > self._emitted:
            chunk = masked[self._emitted : safe_upto]
            self._emitted = safe_upto
            return [chunk]
        return []

    def flush(self) -> list[str]:
        """Release the held-back tail once the stream has ended."""
        if self.blocked or self.guard is None:
            return []
        pol = self.guard.process_output(self._acc)
        if pol["blocked"]:
            return [self._block_message(pol.get("reason"))]
        self.masked = self.masked or bool(pol.get("masked"))
        masked = pol["text"]
        if len(masked) > self._emitted:
            chunk = masked[self._emitted :]
            self._emitted = len(masked)
            return [chunk]
        return []


class YulYenStreamingProvider:
    """
    Wrapper around the LLM with streaming support.

    The streamer accepts the system prompt, persona name, LLM options,
    and the host URL. The class handles logging (conversation JSON log)
    and optionally output moderation via SecurityGuard. The actual LLM call
    is delegated to an ``LLMCore``.
    """

    def __init__(
        self,
        base_url: str,
        persona: str,
        persona_prompt: str,
        persona_options: dict[str, Any],
        model_name: str = "plain",
        keep_alive: int = 600,
        log_file: str = "conversation.json",
        guard: BasicGuard | None = None,
        *,
        llm_core: LLMCore | None = None,
    ) -> None:
        self.model_name = model_name
        self.keep_alive = keep_alive
        self.persona = persona
        self.persona_prompt = persona_prompt
        self.persona_options = persona_options

        # Initialize the LLM core or use the injected one
        self._llm_core: LLMCore
        if llm_core is not None:
            self._llm_core = llm_core
        else:
            try:
                from .ollama_llm_core import OllamaLLMCore
            except ModuleNotFoundError as exc:
                if is_ollama_module_not_found(exc):
                    raise RuntimeError(
                        "No LLM core was injected and the Python package 'ollama' is missing. "
                        "Install 'ollama' or provide a dummy implementation."
                    ) from exc
                raise

            self._llm_core = OllamaLLMCore(base_url)

        # Configure logging
        self._logs_dir = "logs"
        ensure_dir_exists(self._logs_dir)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
        self.guard: BasicGuard | None = guard

    def set_guard(self, guard: BasicGuard) -> None:
        """Sets the security guard for later checks."""
        self.guard = guard

    def _append_conversation_log(self, role: str, content: str) -> None:
        """Writes an entry to the conversation JSON log."""
        try:
            entry = {
                "ts": datetime.datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
                "model": self.model_name,
                "bot": self.persona,
                "options": self.persona_options,
                "role": role,
                "content": content,
            }
            with _conversation_log_lock:
                with open(self.conversation_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError):
            # Logging must never break the stream; file or serialization issues
            # are reported with a full traceback instead of failing the reply.
            logging.exception(
                "Could not write conversation log %s", self.conversation_log_path
            )

    def _log_generation_start(
        self, messages: list[dict[str, Any]], options: dict[str, Any]
    ) -> None:
        """
        Logs compact metadata before the LLM call.
        KISS principle: minimal error handling — logging must never disrupt execution.
        """

        # 1) Compute a deterministic hash / preview of the payload (best effort).
        # Only when DEBUG is active — canonical JSON + SHA-256 over the full
        # payload is wasted work on the critical path if the log line is dropped.
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            payload = {"messages": messages, "options": options}
            try:
                canon = json.dumps(
                    payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
            except (TypeError, ValueError):
                # Fallback if serialization fails due to non-JSON types
                canon = f"<unserializable payload: messages={type(messages)!r}, options={type(options)!r}>"
            sha = hashlib.sha256(canon.encode("utf-8")).hexdigest()
            logging.debug("[LLM INPUT] sha256=%s payload=%s", sha, canon)

        # 2) Estimate token count (non-critical)
        try:
            estimated_tokens = approx_token_count(messages)
        except (TypeError, ValueError):
            estimated_tokens = None  # best effort; do not warn

        # 3) Extract num_ctx from persona options (try to cast to int if possible)
        num_ctx_raw = getattr(self, "persona_options", {}) or {}
        num_ctx_val: Any = None
        if isinstance(num_ctx_raw, dict) and "num_ctx" in num_ctx_raw:
            val = num_ctx_raw["num_ctx"]
            try:
                num_ctx_val = int(val)
            except (TypeError, ValueError):
                num_ctx_val = val  # keep raw value if conversion fails

        # 4) Final concise log entry for this LLM turn
        ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        log_payload = {
            "ts": ts,
            "estimated_tokens": estimated_tokens,
            "num_ctx": num_ctx_val,
        }
        logging.info("[LLM TURN] %s", json.dumps(log_payload, ensure_ascii=False))

        # 5) Optional human-readable trace of the exact prompt (incl. wiki snippets)
        if _log_flag("trace_prompts"):
            logging.info(
                "%s", _render_prompt_trace(self.persona, self.model_name, messages)
            )

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        """
        Generator that yields the LLM response token by token.
        Includes logging and security checks.
        """
        guard_texts = getattr(self.guard, "texts", None) if self.guard else None
        # Pre-check: validate the latest user message
        if self.guard:
            for m in reversed(messages):
                if m.get("role") == "user":
                    res = self.guard.check_input(m.get("content") or "")
                    if not res["ok"]:
                        logging.info(
                            "[GUARD] input blocked persona=%s reason=%s",
                            self.persona,
                            res.get("reason"),
                        )
                        yield zeigefinger_message(res, texts=guard_texts)
                        return
                    break

        # Prepend the system prompt
        if self.persona_prompt:
            messages = [{"role": "system", "content": self.persona_prompt}] + messages
            logging.debug(messages)

        # Record the most recent user message in the log
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_conversation_log("user", m["content"])
                break

        # Apply LLM options
        options: dict[str, Any] = self.persona_options or {}

        full_reply_parts = []
        try:
            t_start = time.time()
            first_token_time: float | None = None

            self._log_generation_start(messages, options)

            # Delegate to the LLM core
            stream_obj = self._llm_core.stream_chat(
                model_name=self.model_name,
                messages=messages,
                options=options,
                keep_alive=self.keep_alive,
            )

            log_raw_chunks = _log_flag("log_raw_chunks")
            moderator = _StreamModerator(self.guard, guard_texts)
            try:
                for chunk in stream_obj:
                    if log_raw_chunks:
                        logging.debug("[RAW CHUNK] %r", chunk)
                    if first_token_time is None:
                        first_token_time = time.time()
                    token = chunk.get("message", {}).get("content", "")
                    if not token:
                        continue
                    full_reply_parts.append(token)
                    for out in moderator.feed(token):
                        yield out
                    if moderator.blocked:
                        break

                # Release the held-back tail (unless we already blocked).
                for out in moderator.flush():
                    yield out

            finally:
                # Always close the stream when possible
                try:
                    close = getattr(stream_obj, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    logging.debug("Closing the LLM stream failed", exc_info=True)

            # Log performance metrics
            t_end = time.time()
            if first_token_time is not None:
                t_first_ms = int((first_token_time - t_start) * 1000)
            else:
                t_first_ms = None
            logging.info(
                "model %s options: %s t_first_ms: %s t_total_ms: %s",
                self.model_name,
                options,
                t_first_ms,
                int((t_end - t_start) * 1000),
            )

            # Log the final assistant reply. When the guard blocked the output
            # we must not persist the raw (e.g. secret) text to the log.
            if moderator.blocked:
                logging.info("[GUARD] output blocked persona=%s", self.persona)
                self._append_conversation_log("assistant", "[BLOCKED by guard]")
                full_reply = ""
            else:
                if moderator.masked:
                    logging.info("[GUARD] output masked PII persona=%s", self.persona)
                full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)
                try:
                    _canon_out = full_reply
                    _hash_out = hashlib.sha256(_canon_out.encode("utf-8")).hexdigest()
                    logging.debug(
                        "[LLM OUTPUT] sha256=%s content=%s", _hash_out, _canon_out
                    )
                except Exception as exc:
                    logging.warning("Unable to log LLM output: %s", exc)

        except Exception:
            # Robustness boundary: whatever the backend throws, the UI gets a
            # readable error instead of a stacktrace; details go to the log.
            logging.exception(
                "stream() failed persona=%s model=%s", self.persona, self.model_name
            )
            err = "[ERROR] LLM is not responding correctly."
            self._append_conversation_log("assistant", err)
            yield err

    def respond_one_shot(
        self,
        user_input: str,
        persona: str,
        keyword_finder,
        wiki_mode: str,
        wiki_proxy_port: int,
        wiki_snippet_limit: int,
        wiki_timeout: tuple[float, float],
        max_wiki_snippets: int,
    ) -> str:
        """
        Convenience method for the API: runs a single prompt
        and returns the complete answer as a string.
        """
        messages: list[dict[str, Any]] = []

        # Look up the Wikipedia snippet(s)
        _wiki_hints, contexts = lookup_wiki_snippet(
            user_input,
            persona,
            keyword_finder,
            wiki_mode,
            wiki_proxy_port,
            wiki_snippet_limit,
            wiki_timeout,
            max_wiki_snippets,
        )

        # Attach context
        if contexts:
            inject_wiki_context(messages, contexts)

        # Add the user question as the last message
        messages.append({"role": "user", "content": user_input})

        # Check guard input
        if self.guard:
            guard_texts = getattr(self.guard, "texts", None)
            res_in = self.guard.check_input(user_input or "")
            if not res_in["ok"]:
                logging.info(
                    "[GUARD] input blocked persona=%s reason=%s",
                    persona,
                    res_in.get("reason"),
                )
                return zeigefinger_message(res_in, texts=guard_texts)

        # Run the LLM and collect the answer
        full_reply = run_llm_collect(self, messages)

        # Check guard output
        if self.guard:
            res_out = self.guard.check_output(full_reply or "")
            if not res_out["ok"]:
                logging.info(
                    "[GUARD] output blocked persona=%s reason=%s",
                    persona,
                    res_out.get("reason"),
                )
                return zeigefinger_message(res_out, texts=guard_texts)

        return full_reply


def run_llm_collect(
    streamer: YulYenStreamingProvider, messages: list[dict[str, Any]]
) -> str:
    """
    Runs streaming and collects all tokens into a single response.
    """
    full_reply_parts = []
    for token in streamer.stream(messages=messages):
        full_reply_parts.append(token)
    return "".join(full_reply_parts).strip()
