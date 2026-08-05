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
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from typing import Any

from config.config_singleton import Config
from security.tinyguard import BasicGuard, zeigefinger_message
from storage import ConversationStore, NullStore
from wiki.lookup import WikiLookup, inject_wiki_context

from core.context_utils import approx_token_count
from core.utils import LOCAL_USER, ensure_dir_exists, is_ollama_module_not_found

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
# can still leak their prefix.
#
# This is also the single biggest contributor to the perceived response time
# (#51): nothing reaches the display before this many characters exist. The
# default favours a local, single-user setup — see the comment on
# `security.stream_holdback_chars` in config.yaml for when to raise it.
_STREAM_HOLDBACK_CHARS = 32

# Wie weit der Moderator hinter die Freigabemarke zurückschaut, damit ein
# Treffer, der davor beginnt, noch vollständig im Fenster liegt. Muss bequem
# über dem längsten Ausgangsmuster liegen; hält die Prüfung trotzdem bei O(1)
# pro Token statt bei O(Antwortlänge).
_CONTEXT_WINDOW_CHARS = 256


def _output_checks_active(guard: BasicGuard | None) -> bool:
    """True when the guard actually inspects outgoing text.

    Both output-side checks can be switched off in ``config.yaml``. With neither
    active, ``process_output`` is a no-op and holding tokens back buys nothing.
    """
    if guard is None or not getattr(guard, "enabled", False):
        return False
    flags = getattr(guard, "flags", {}) or {}
    return bool(flags.get("pii_protection") or flags.get("output_blocklist"))


@dataclass(frozen=True)
class StreamStats:
    """Kennzahlen des letzten Streams (#36).

    Gemessen wurden sie schon immer — sie standen nur im Logfile. Für die
    Statuszeile im WebUI müssen sie den Aufrufer erreichen, ohne die Signatur
    von ``stream()`` zu ändern: der Provider legt sie auf sich selbst ab.
    """

    tokens: int
    t_first_ms: int | None
    t_total_ms: int

    @property
    def tokens_per_second(self) -> float:
        if self.t_total_ms <= 0 or self.tokens <= 0:
            return 0.0
        return self.tokens / (self.t_total_ms / 1000)


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
        # Der Holdback ist der Preis für den Straddle-Schutz und bestimmt direkt
        # die Zeit bis zum ersten sichtbaren Token: es geht nichts raus, bevor
        # `holdback` Zeichen da sind (#51 — gemessen 96 Zeichen ≈ 4 s bei
        # 24 Zeichen/s). Prüft der Guard ausgangsseitig nichts, gibt es auch
        # nichts zurückzuhalten — dann kostet er nur Latenz.
        self.holdback = holdback if _output_checks_active(guard) else 0
        self.blocked = False
        self.masked = False
        self._acc = ""
        # Index in den ROHEN Text: wie viel davon bereits (maskiert) raus ist.
        self._released = 0

    def _block_message(self, reason: str | None) -> str:
        self.blocked = True
        return zeigefinger_message(
            {
                "ok": False,
                "reason": reason or "blocked_keyword",
                "detail": "",
                "rule": None,
            },
            texts=self.guard_texts,
        )

    def feed(self, token: str) -> list[str]:
        """Consume one token; return the chunks that are now safe to emit."""
        if self.blocked or not token:
            return []
        self._acc += token

        # No guard: nothing to moderate, stream the token straight through.
        if self.guard is None:
            self._released += len(token)
            return [token]

        return self._release_up_to(len(self._acc) - self.holdback)

    def flush(self) -> list[str]:
        """Release the held-back tail once the stream has ended."""
        if self.blocked or self.guard is None:
            return []
        return self._release_up_to(len(self._acc))

    def _release_up_to(self, frontier: int) -> list[str]:
        """Gibt ``self._acc`` bis ``frontier`` frei — maskiert und lückenlos.

        Der Index läuft über den **rohen** Text, nicht über den maskierten.
        Vorher war es umgekehrt, und weil die Maskierung die Länge ändert
        (``max@example.com`` → ``[PII]``), zeigte der Index nach jedem Treffer
        auf die falsche Stelle: Modelltext verschwand oder kam doppelt.

        Damit das Maskieren eines Abschnitts *für sich* dasselbe Ergebnis
        liefert wie über den ganzen Text, darf die Freigabegrenze nie mitten in
        einem Treffer liegen. Genau das prüft ``output_match_crossing``; liegt
        einer quer, wird die Grenze vor seinen Anfang zurückgezogen und der
        Rest wartet auf mehr Text.

        Gearbeitet wird nur auf einem Fenster um die Grenze statt auf dem
        gesamten bisherigen Text. Vorher lief ``process_output`` pro Token über
        alles Bisherige — quadratisch im Antwortumfang, 1,6 s reine CPU auf
        16.000 Zeichen.
        """
        guard = self.guard
        if guard is None or frontier <= self._released:
            return []

        # Fenster: etwas vor der freigegebenen Marke (damit ein Treffer, der
        # davor beginnt, noch sichtbar ist) bis ans Ende des Bekannten.
        window_start = max(0, self._released - _CONTEXT_WINDOW_CHARS)
        window = self._acc[window_start:]

        # Blockieren gilt für den ganzen Stream, nicht nur für den Abschnitt.
        pol = guard.process_output(window)
        if pol["blocked"]:
            return [self._block_message(pol.get("reason"))]

        crossing = guard.output_match_crossing(window, frontier - window_start)
        if crossing is not None:
            frontier = window_start + crossing
            if frontier <= self._released:
                return []

        segment = self._acc[self._released : frontier]
        result = guard.process_output(segment)
        if result["blocked"]:
            return [self._block_message(result.get("reason"))]
        self.masked = self.masked or bool(result.get("masked"))
        self._released = frontier
        return [result["text"]] if result["text"] else []


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
        store: ConversationStore | None = None,
        jsonl_log: bool = False,
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

        # Die Aufzeichnung liegt seit #54 im Store; der JSONL-Mitschnitt ist ein
        # ausdrückliches Debug-Artefakt und standardmäßig aus.
        self.store: ConversationStore = store if store is not None else NullStore()
        self.conversation_id: str = ""
        self.jsonl_log = bool(jsonl_log)
        self._logs_dir = "logs"
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
        if self.jsonl_log:
            ensure_dir_exists(self._logs_dir)
        self.guard: BasicGuard | None = guard
        # Wer das Gespräch führt (#53). Ohne Anmeldung — Terminal, API — ist
        # der lokale Nutzer die ehrliche Antwort; die WebUI überschreibt es
        # mit der angemeldeten Identität.
        self.user: str = LOCAL_USER
        # Kennzahlen des zuletzt gelaufenen Streams (#36); None vor dem ersten.
        self.last_stream_stats: StreamStats | None = None
        self.stream_holdback: int = _STREAM_HOLDBACK_CHARS

    def set_guard(self, guard: BasicGuard) -> None:
        """Sets the security guard for later checks."""
        self.guard = guard

    def set_stream_holdback(self, chars: int) -> None:
        """Override how many trailing characters the output guard holds back.

        Directly trades perceived latency against straddle protection (#51) —
        see ``_STREAM_HOLDBACK_CHARS``.
        """
        try:
            self.stream_holdback = max(0, int(chars))
        except (TypeError, ValueError):
            self.stream_holdback = _STREAM_HOLDBACK_CHARS

    def set_user(self, user: str) -> None:
        """Identität des Gesprächs setzen (#53).

        Hängt am Gespräch in der Ablage — ohne dieses Feld wäre die Anmeldung
        nur Zierde, weil #25 (Verlauf) und #24 niemandem etwas zuordnen könnten.
        """
        self.user = (user or "").strip() or LOCAL_USER

    def set_conversation(self, conversation_id: str) -> None:
        """Gespräch, in das aufgezeichnet wird (#54).

        Die ID gehört der Oberfläche, nicht dem Streamer: wird der Streamer neu
        gebaut (Persona geladen, Modell gewechselt), bleibt das Gespräch dasselbe.
        Ohne das begänne jede Fortsetzung einen neuen Datensatz.
        """
        self.conversation_id = (conversation_id or "").strip()

    def record_conversation(self, messages: list[dict[str, Any]]) -> None:
        """Bringt die Ablage auf den Stand des Gesprächs (#59).

        **Aufgerufen von der Oberfläche, nicht von ``stream()``.** Der Streamer
        sieht nur einen Generierungs*versuch*; welcher davon zum Gespräch
        gehört, weiß allein der Aufrufer. Solange die Aufzeichnung in
        ``stream()`` saß, protokollierte sie Versuche: „Nochmal 🔄" hängte
        Frage und verworfene Antwort erneut an, „Stop ⏹" ließ die Antwort ganz
        weg.

        **Ask-All und Self-Talk rufen das hier bewusst nicht** (#75, verworfen
        am 2026-08-05): vier parallele Antworten sind kein *ein* Gespräch, und
        Self-Talk erzeugt ein Artefakt statt eines Nutzergesprächs. Begründung
        in CLAUDE.md, Abschnitt „Ablage der Gespräche" — hier steht es, damit
        niemand die fehlenden Aufrufe für ein Versehen hält.

        Aufzeichnen darf den Betrieb nie stören — dieselbe Regel wie zuvor.
        """
        try:
            self.store.sync(self.conversation_id, messages)
        except Exception:
            logging.exception("Could not record the conversation in the store")

    def _append_jsonl(self, role: str, content: str) -> None:
        """Roher Turn-Mitschnitt (opt-in, `logging.conversation_jsonl`).

        Bewusst weiter *anhängend* und weiter hier: das ist das Debug-Artefakt,
        das festhält, was tatsächlich passiert ist — verworfene Versuche
        eingeschlossen. Damit stimmt die Rollenverteilung aus #54 endlich:
        JSONL = roher Mitschnitt, SQLite = das Gespräch.
        """
        if not self.jsonl_log:
            return
        try:
            entry = {
                "ts": datetime.datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
                "model": self.model_name,
                "bot": self.persona,
                "user": self.user,
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

    def _input_refusal(self, text: str, persona: str) -> str | None:
        """Guard-Eingangsprüfung: die Absage — oder None, wenn nichts anschlägt.

        Geteilt von ``stream()`` und ``respond_one_shot()``: die Prüfung stand
        zweimal da und hätte bei jeder Änderung auseinanderlaufen können.
        """
        if not self.guard:
            return None
        result = self.guard.check_input(text or "")
        if result["ok"]:
            return None
        logging.info(
            "[GUARD] input blocked persona=%s reason=%s", persona, result.get("reason")
        )
        return zeigefinger_message(result, texts=getattr(self.guard, "texts", None))

    def stream(self, messages: list[dict[str, Any]]) -> Generator[str, None, None]:
        """
        Generator that yields the LLM response token by token.
        Includes logging and security checks.

        Generator, nicht bloß Iterator: Aufrufer schließen den Stream
        explizit (``close()``), damit das ``finally`` hier den Backend-Stream
        beendet, statt auf den GC zu warten.
        """
        guard_texts = getattr(self.guard, "texts", None) if self.guard else None
        # Pre-check: validate the latest user message
        if self.guard:
            for m in reversed(messages):
                if m.get("role") == "user":
                    refusal = self._input_refusal(m.get("content") or "", self.persona)
                    if refusal is not None:
                        yield refusal
                        return
                    break

        # Prepend the system prompt
        if self.persona_prompt:
            messages = [{"role": "system", "content": self.persona_prompt}] + messages
            logging.debug(messages)

        # Record the most recent user message in the log
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_jsonl("user", m["content"])
                break

        # Apply LLM options
        options: dict[str, Any] = self.persona_options or {}

        full_reply_parts = []
        try:
            t_start = time.time()
            first_token_time: float | None = None
            token_count = 0

            self._log_generation_start(messages, options)

            # Delegate to the LLM core
            stream_obj = self._llm_core.stream_chat(
                model_name=self.model_name,
                messages=messages,
                options=options,
                keep_alive=self.keep_alive,
            )

            log_raw_chunks = _log_flag("log_raw_chunks")
            moderator = _StreamModerator(
                self.guard, guard_texts, holdback=self.stream_holdback
            )
            try:
                for chunk in stream_obj:
                    if log_raw_chunks:
                        logging.debug("[RAW CHUNK] %r", chunk)
                    if first_token_time is None:
                        first_token_time = time.time()
                    token = chunk.get("message", {}).get("content", "")
                    if not token:
                        continue
                    token_count += 1
                    # Aufgezeichnet wird, was der Moderator freigibt — nicht der
                    # rohe Token. Sonst steht im Store (und im JSONL-Mitschnitt)
                    # die unmaskierte Fassung, während der Bildschirm maskiert
                    # ist: die Maskierung wäre dann Bildschirmschoner statt
                    # Datenschutz, und über Verlauf, Markdown-Export und
                    # JSON-Download käme sie vollständig wieder heraus.
                    for out in moderator.feed(token):
                        full_reply_parts.append(out)
                        yield out
                    if moderator.blocked:
                        break

                # Release the held-back tail (unless we already blocked).
                for out in moderator.flush():
                    full_reply_parts.append(out)
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
            t_total_ms = int((t_end - t_start) * 1000)
            self.last_stream_stats = StreamStats(
                tokens=token_count, t_first_ms=t_first_ms, t_total_ms=t_total_ms
            )
            logging.info(
                "model %s options: %s t_first_ms: %s t_total_ms: %s",
                self.model_name,
                options,
                t_first_ms,
                t_total_ms,
            )

            # Log the final assistant reply. When the guard blocked the output
            # we must not persist the raw (e.g. secret) text to the log.
            if moderator.blocked:
                logging.info("[GUARD] output blocked persona=%s", self.persona)
                self._append_jsonl("assistant", "[BLOCKED by guard]")
                full_reply = ""
            else:
                if moderator.masked:
                    logging.info("[GUARD] output masked PII persona=%s", self.persona)
                full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_jsonl("assistant", full_reply)
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
            self._append_jsonl("assistant", err)
            yield err

    def respond_one_shot(self, user_input: str, persona: str, wiki: WikiLookup) -> str:
        """
        Convenience method for the API: runs a single prompt
        and returns the complete answer as a string.
        """
        # Zuerst der Guard, dann das Netz (#64b). Vorher lief der Wiki-Lookup
        # davor, also löste auch eine *abgelehnte* Eingabe einen Abruf mit
        # fremdbestimmtem Suchbegriff aus — die Absage kam danach, der Abruf
        # war da schon passiert.
        refusal = self._input_refusal(user_input, persona)
        if refusal is not None:
            return refusal

        messages: list[dict[str, Any]] = []

        # Look up the Wikipedia snippet(s)
        _wiki_hints, contexts = wiki.snippets(user_input, persona, self.guard)

        # Attach context
        if contexts:
            inject_wiki_context(messages, contexts, self.guard)

        # Add the user question as the last message
        messages.append({"role": "user", "content": user_input})

        # Der Ausgangs-Guard sitzt im Stream, nicht hier (#64a): `stream()`
        # schickt jedes Token durch `_StreamModerator`, `run_llm_collect`
        # liefert also bereits moderierten Text. Eine zweite `check_output`
        # darauf sah nach Tiefenverteidigung aus, konnte aber nie anschlagen —
        # nachgemessen mit einem Secret und einer Mailadresse im Modelltext:
        # beide waren beim zweiten Blick längst ersetzt, das Ergebnis war jedes
        # Mal `ok`. Wer hier wieder eine Prüfung einzieht, prüft die Maskierung,
        # nicht das Modell.
        full_reply = run_llm_collect(self, messages)
        # Die Ablage bekommt das Gespräch, nicht den Generierungsversuch (#59).
        self.record_conversation(
            [*messages, {"role": "assistant", "content": full_reply}]
        )
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
