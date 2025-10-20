"""
Streaming provider with persona handling, logging, and safety checks.

All direct calls to the underlying LLM are abstracted through an
``LLMCore`` (e.g. ``OllamaLLMCore`` or ``DummyLLMCore``).
This class takes care of prompt injection, logging (conversation.log),
and optional output moderation via SecurityGuard.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import time
import traceback
from typing import Any, Dict, List, Optional

import requests

from core.utils import clean_token, ensure_dir_exists
from core.context_utils import approx_token_count

from security.tinyguard import BasicGuard, zeigefinger_message

# Import the LLM interface
from .llm_core import LLMCore

from config.config_singleton import Config


def _get_config() -> Config:
    """Returns the current config singleton instance."""
    return Config()



class YulYenStreamingProvider:
    """
    Wrapper around the LLM with streaming support.

    The streamer accepts the system prompt, persona name, LLM options,
    and the host URL. The class handles logging (conversation.log) and
    optionally output moderation via SecurityGuard. The actual LLM call
    is delegated to an ``LLMCore``.
    """

    def __init__(
        self,
        base_url: str,
        persona: str,
        persona_prompt: str,
        persona_options: Dict[str, Any],
        model_name: str = "plain",
        warm_up: bool = False,
        log_file: str = "conversation.json",
        guard: Optional[BasicGuard] = None,
        *,
        llm_core: Optional[LLMCore] = None,
    ) -> None:
        self.model_name = model_name
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
                missing_name = getattr(exc, "name", None)
                message = str(exc)
                if missing_name == "ollama" or (
                    missing_name is None and "ollama" in message.lower()
                ):
                    raise RuntimeError(
                        "Es wurde kein LLM-Core injiziert und das Python-Paket 'ollama' fehlt. "
                        "Installiere 'ollama' oder übergib eine Dummy-Implementierung."
                    ) from exc
                raise

            self._llm_core = OllamaLLMCore(base_url)

        # Configure logging
        self._logs_dir = "logs"
        ensure_dir_exists(self._logs_dir)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
        self.guard: Optional[BasicGuard] = guard

        if warm_up:
            logging.info("Starting model warm-up: %s", model_name)
            self._warm_up()

    def set_guard(self, guard: BasicGuard) -> None:
        """Sets the security guard for later checks."""
        self.guard = guard

    def _warm_up(self) -> None:
        """Calls the LLM once to warm it up."""
        logging.info("Sending dummy request to activate the model: %s", self.model_name)
        try:
            self._llm_core.warm_up(self.model_name)
            logging.info("Model warmed up successfully.")
        except Exception:
            logging.error("Error while warming up the model:\n%s", traceback.format_exc())

    def _append_conversation_log(self, role: str, content: str) -> None:
        """Writes an entry to conversation.log."""
        try:
            entry = {
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "model": self.model_name,
                "bot": self.persona,
                "options": self.persona_options,
                "role": role,
                "content": content,
            }
            with open(self.conversation_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.error("Error while writing conversation.log: %s", e)

    def _log_generation_start(self, messages: List[Dict[str, Any]], options: Dict[str, Any]) -> None:
        """Logs context and wiki information before the actual LLM call.
            TODO: Refactor: This method can be far leaner with less overblown error handling
        """

        # Hash and log the payload (messages plus options)
        try:
            _payload = {"messages": messages, "options": options}
            _canon = json.dumps(_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            _hash = hashlib.sha256(_canon.encode("utf-8")).hexdigest()
            logging.debug("[LLM INPUT] sha256=%s payload=%s", _hash, _canon)
        except Exception as exc:
            logging.warning("Unable to log LLM input: %s", exc)


        timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            estimated_tokens = approx_token_count(messages)
        except Exception as exc:  # pragma: no cover - safety net
            logging.warning("Could not estimate token count: %s", exc)
            estimated_tokens = None
        persona_options = self.persona_options or {}
        num_ctx_raw = persona_options.get("num_ctx") if isinstance(persona_options, dict) else None
        num_ctx_value: Any
        if num_ctx_raw is None:
            num_ctx_value = None
        else:
            try:
                num_ctx_value = int(num_ctx_raw)
            except (TypeError, ValueError):
                num_ctx_value = num_ctx_raw
        log_payload = {
            "ts": timestamp,
            "estimated_tokens": estimated_tokens,
            "num_ctx": num_ctx_value,
        }
        logging.info("[LLM TURN] %s", json.dumps(log_payload, ensure_ascii=False))


    def stream(self, messages: List[Dict[str, Any]]):
        """
        Generator that yields the LLM response token by token.
        Includes logging and security checks.
        """
        # Pre-check: validate the latest user message
        if self.guard:
            for m in reversed(messages):
                if m.get("role") == "user":
                    res = self.guard.check_input(m.get("content") or "")
                    if not res["ok"]:
                        yield zeigefinger_message(res)
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
        options: Dict[str, Any] = {}
        if self.persona_options:
            options = self.persona_options

        full_reply_parts = []
        try:
            t_start = time.time()
            first_token_time: Optional[float] = None

            self._log_generation_start(messages, options)

            # Delegate to the LLM core
            stream_obj = self._llm_core.stream_chat(
                model_name=self.model_name, messages=messages, options=options, keep_alive=600
            )

            try:
                buffer = ""
                for chunk in stream_obj:
                    logging.debug("[RAW CHUNK] %r", chunk) 
                    if first_token_time is None:
                        first_token_time = time.time()
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        cleaned = clean_token(token)
                        if not cleaned:
                            continue
                        buffer += cleaned
                        full_reply_parts.append(cleaned)

                        to_send = buffer
                        if self.guard:
                            pol = self.guard.process_output(to_send)
                            if pol["blocked"]:
                                yield zeigefinger_message(
                                    {"reason": pol.get("reason") or "blocked_keyword", "detail": ""}
                                )
                                break
                            to_send = pol["text"]

                        # Batch heuristically — send once at least one separator appears
                        seps = [" ", "\n", "\t", "!", "?"]
                        count = sum(to_send.count(sep) for sep in seps)
                        logging.debug("Buffer:" + to_send + "###" + str(count))
                        if count >= 1:
                            yield to_send
                            buffer = ""

                # Send the remaining buffer
                if buffer:
                    to_send = buffer
                    if self.guard:
                        pol = self.guard.process_output(to_send)
                        if pol["blocked"]:
                            yield zeigefinger_message({"reason": pol.get("reason") or "blocked_keyword", "detail": ""})
                        else:
                            yield pol["text"]
                    else:
                        yield to_send

            finally:
                # Always close the stream when possible
                try:
                    close = getattr(stream_obj, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass

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

            # Log the final assistant reply
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)
                try:
                    _canon_out = full_reply
                    _hash_out = hashlib.sha256(_canon_out.encode("utf-8")).hexdigest()
                    logging.debug("[LLM OUTPUT] sha256=%s content=%s", _hash_out, _canon_out)
                except Exception as exc:
                    logging.warning("Unable to log LLM output: %s", exc)

        except Exception:
            logging.error("Error in stream():\n%s", traceback.format_exc())
            err = "[FEHLER] LLM antwortet nicht korrekt."
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
    ) -> str:
        """
        Convenience method for the API: runs a single prompt
        and returns the complete answer as a string.
        """
        messages: List[Dict[str, Any]] = []

        # Look up the Wikipedia snippet
        wiki_hint, topic_title, snippet = lookup_wiki_snippet(
            user_input, persona, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout
        )

        # Attach context
        if snippet:
            inject_wiki_context(messages, topic_title, snippet)

        # Add the user question as the last message
        messages.append({"role": "user", "content": user_input})

        # Check guard input
        if self.guard:
            res_in = self.guard.check_input(user_input or "")
            if not res_in["ok"]:
                return zeigefinger_message(res_in)

        # Run the LLM and collect the answer
        full_reply = run_llm_collect(self, messages)

        # Check guard output
        if self.guard:
            res_out = self.guard.check_output(full_reply or "")
            if not res_out["ok"]:
                return zeigefinger_message(res_out)

        return full_reply


def lookup_wiki_snippet(
    question: str,
    persona_name: str,
    keyword_finder,
    wiki_mode: str,
    proxy_port: int,
    limit: int,
    timeout: tuple[float, float],
) -> tuple[str, str, str]:
    """
    Helper function: fetches a Wikipedia snippet via a local proxy.
    """
    snippet: Optional[str] = None
    wiki_hint: Optional[str] = None
    topic_title: Optional[str] = None
    cfg = _get_config()
    texts = cfg.texts
    proxy_base = "http://localhost:" + str(proxy_port)



    if not keyword_finder:
        return (None, None, None)

    topic = keyword_finder.find_top_keyword(question)
    if topic:
        online_flag = "1" if wiki_mode == "online" else "0"
        url = f"{proxy_base.rstrip('/')}/{topic}?json=1&limit={limit}&online={online_flag}&persona={persona_name}"
        try:
            proxy_response = requests.get(url, timeout=timeout)

            if proxy_response.status_code == 200:
                data = proxy_response.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[:limit]
                wiki_hint = data.get("wiki_hint")
                topic_title = topic
            elif proxy_response.status_code == 404:
                wiki_hint = cfg.t("wiki_hint_not_found", topic=topic)
            else:
                wiki_hint = cfg.t("wiki_hint_unreachable", topic=topic)
        except requests.exceptions.RequestException as err:
            logging.error(
                "[WIKI EXC] Network error while retrieving '%s': %s",
                topic,
                err,
                exc_info=True,
            )
            wiki_hint = texts["wiki_hint_proxy_error"]
        except Exception as err:  # pragma: no cover - unexpected errors
            logging.exception("[WIKI EXC] Unexpected error for topic='%s'", topic)
            wiki_hint = texts["wiki_hint_unknown_error"]
    return (wiki_hint, topic_title, snippet)


def inject_wiki_context(history: list, topic: str, snippet: str) -> None:
    """
    If a Wikipedia snippet is available, append two system messages:
    a guardrail message and a context message with the wiki text.
    """
    if not snippet:
        return
    guardrail = (
        "Nutze ausschließlich den folgenden Kontext aus Wikipedia. "
        "Wenn etwas dort nicht steht, sag knapp, dass du es nicht sicher weißt."
    )
    history.append({"role": "system", "content": guardrail})
    context_message = (
        f"Kontext zum Thema {topic.replace('_', ' ')}: "
        f"[Quelle: Wikipedia] {snippet}"
    )
    history.append({"role": "system", "content": context_message})


def run_llm_collect(streamer: YulYenStreamingProvider, messages: List[Dict[str, Any]]) -> str:
    """
    Runs streaming and collects all tokens into a single response.
    """
    full_reply_parts = []
    for token in streamer.stream(messages=messages):
        full_reply_parts.append(token)
    return "".join(full_reply_parts).strip()


    