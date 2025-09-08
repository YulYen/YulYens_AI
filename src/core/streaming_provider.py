"""
Streaming‑Provider mit Persona‑Handling, Reminder, Logging und Sicherheitschecks.

Alle direkten Ollama‑Aufrufe sind in einer separaten Klasse (`OllamaLLMCore`)
gekapselt. Diese Klasse kümmert sich um Prompt‑Einblendung, Reminder,
Logging (conversation.log) und optionale Output‑Moderation via SecurityGuard.
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

from core.utils import clean_token
from security.tinyguard import BasicGuard, zeigefinger_message
from .ollama_llm_core import OllamaLLMCore


def _apply_reminder_injection(messages: list[dict], reminder: str) -> list[dict]:
    """
    Fügt vor der aktuellen User‑Message eine kurze System‑Reminder‑Message ein.
    Wir duplizieren die Liste, um die Caller‑Referenz nicht zu verändern.
    """
    if not messages:
        return messages
    patched = list(messages)
    patched.insert(len(patched) - 1, {"role": "system", "content": str(reminder)})
    logging.info(f"Reminder injected: {reminder}")
    return patched


class YulYenStreamingProvider:
    """
    Wrapper um das LLM mit Streaming‑Unterstützung.

    Der Streamer nimmt System‑Prompt, Persona‑Name, LLM‑Optionen und die
    Host‑URL entgegen. Die Klasse kümmert sich um Reminder‑Einblendung,
    Logging (conversation.log) und optional um Output‑Moderation via SecurityGuard.
    Der eigentliche LLM‑Aufruf wird an `OllamaLLMCore` delegiert.
    """

    def __init__(
        self,
        base_url: str,
        persona: str,
        persona_prompt: str,
        persona_options: Dict[str, Any],
        model_name: str = "plain",
        warm_up: bool = False,
        reminder: Optional[str] = None,
        log_file: str = "conversation.json",
        guard: Optional[BasicGuard] = None,
        *,
        llm_core: Optional[OllamaLLMCore] = None,
    ) -> None:
        self.model_name = model_name
        self.reminder = reminder or None
        self.persona = persona
        self.persona_prompt = persona_prompt
        self.persona_options = persona_options

        # LLM‑Core initialisieren oder injiziertes verwenden
        self._llm_core = llm_core or OllamaLLMCore(base_url)

        # Logging konfigurieren
        self._logs_dir = "logs"
        os.makedirs(self._logs_dir, exist_ok=True)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
        self.guard: Optional[BasicGuard] = guard

        if warm_up:
            logging.info("Starte Aufwärmen des Modells: %s", model_name)
            self._warm_up()

    def set_guard(self, guard: BasicGuard) -> None:
        """Setzt den Security‑Guard für spätere Checks."""
        self.guard = guard

    def _warm_up(self) -> None:
        """Ruft das LLM einmal auf, um es vorzuheizen."""
        logging.info("Sende Dummy zur Modellaktivierung: %s", self.model_name)
        try:
            self._llm_core.warm_up(self.model_name)
            logging.info("Modell erfolgreich vorgewärmt.")
        except Exception:
            logging.error("Fehler beim Aufwärmen des Modells:\n%s", traceback.format_exc())

    def _append_conversation_log(self, role: str, content: str) -> None:
        """Schreibt einen Eintrag in die conversation.log."""
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
            logging.error("Fehler beim Schreiben des Conversation_log: %s", e)

    def stream(self, messages: List[Dict[str, Any]]):
        """
        Generator, der tokenweise Antworten aus dem LLM zurückliefert.
        Reminder‑Injektion, Logging und Security‑Checks bleiben erhalten.
        """
        # Vorab: letzte User‑Message prüfen
        if self.guard:
            for m in reversed(messages):
                if m.get("role") == "user":
                    res = self.guard.check_input(m.get("content") or "")
                    if not res["ok"]:
                        yield zeigefinger_message(res)
                        return
                    break

        # System‑Prompt voranstellen
        if self.persona_prompt:
            messages = [{"role": "system", "content": self.persona_prompt}] + messages
            logging.debug(messages)

        # Reminder injizieren
        if self.reminder:
            messages = _apply_reminder_injection(messages, self.reminder)

        # Letzte User‑Nachricht im Log festhalten
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_conversation_log("user", m["content"])
                break

        # LLM‑Options übernehmen
        options: Dict[str, Any] = {}
        if self.persona_options:
            options = self.persona_options

        # Payload (Messages + Options) hashen und loggen
        try:
            _payload = {"messages": messages, "options": options}
            _canon = json.dumps(_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            _hash = hashlib.sha256(_canon.encode("utf-8")).hexdigest()
            logging.debug("[OLLAMA INPUT] sha256=%s payload=%s", _hash, _canon)
        except Exception as exc:
            logging.warning("Unable to log Ollama input: %s", exc)

        full_reply_parts = []
        try:
            t_start = time.time()
            first_token_time: Optional[float] = None

            # Delegation an den LLM‑Core
            stream_obj = self._llm_core.stream_chat(
                model_name=self.model_name, messages=messages, options=options, keep_alive=600
            )

            try:
                buffer = ""
                for chunk in stream_obj:
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

                        # Batching heuristisch – Senden, wenn mindestens ein Separator
                        seps = [" ", "\n", "\t", "!", "?"]
                        count = sum(to_send.count(sep) for sep in seps)
                        logging.debug("Buffer:" + to_send + "###" + str(count))
                        if count >= 1:
                            yield to_send
                            buffer = ""

                # Rest senden
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
                # Stream immer schließen, wenn möglich
                try:
                    close = getattr(stream_obj, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass

            # Performance loggen
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

            # Finale Assistant‑Antwort loggen
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)
                try:
                    _canon_out = full_reply
                    _hash_out = hashlib.sha256(_canon_out.encode("utf-8")).hexdigest()
                    logging.debug("[OLLAMA OUTPUT] sha256=%s content=%s", _hash_out, _canon_out)
                except Exception as exc:
                    logging.warning("Unable to log Ollama output: %s", exc)

        except Exception:
            logging.error("Fehler bei stream():\n%s", traceback.format_exc())
            err = "[FEHLER] Ollama antwortet nicht korrekt."
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
        Convenience‑Methode für die API: Führt einen einzigen Prompt aus
        und liefert die komplette Antwort als String zurück.
        """
        messages: List[Dict[str, Any]] = []

        # Wikipedia‑Snippet suchen
        wiki_hint, topic_title, snippet = lookup_wiki_snippet(
            user_input, persona, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout
        )

        # Kontext anhängen
        if snippet:
            inject_wiki_context(messages, topic_title, snippet)

        # Nutzerfrage als letzte Nachricht
        messages.append({"role": "user", "content": user_input})

        # Guard‑Input prüfen
        if self.guard:
            res_in = self.guard.check_input(user_input or "")
            if not res_in["ok"]:
                return zeigefinger_message(res_in)

        # LLM ausführen und Antwort sammeln
        full_reply = run_llm_collect(self, messages)

        # Guard‑Output prüfen
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
    Hilfsfunktion: Holt ein Wikipedia‑Snippet über einen lokalen Proxy.
    """
    snippet: Optional[str] = None
    wiki_hint: Optional[str] = None
    topic_title: Optional[str] = None
    proxy_base = "http://localhost:" + str(proxy_port)

    if not keyword_finder:
        return (None, None, None)

    topic = keyword_finder.find_top_keyword(question)
    if topic:
        online_flag = "1" if wiki_mode == "online" else "0"
        url = f"{proxy_base.rstrip('/')}/{topic}?json=1&limit={limit}&online={online_flag}&persona={persona_name}"
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[:limit]
                wiki_hint = data.get("wiki_hint")
                topic_title = topic
            elif r.status_code == 404:
                wiki_hint = f"🕵️‍♀️ *Kein Eintrag gefunden:*{topic}"
            else:
                wiki_hint = f"🕵️‍♀️ *Wikipedia nicht erreichbar.*{topic}"
        except Exception as e:
            logging.error("[WIKI EXC] topic='%s' err=%s", topic, e)
            wiki_hint = f"🕵️‍♀️ *Fehler: Wikipedia nicht erreichbar.*{topic}"
    return (wiki_hint, topic_title, snippet)


def inject_wiki_context(history: list, topic: str, snippet: str) -> None:
    """
    Füge (falls ein Wikipedia‑Snippet vorhanden ist) zwei System‑Nachrichten an:
    eine Guardrail‑Nachricht und eine Kontext‑Nachricht mit dem Wiki‑Text.
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
    Führt das Streaming aus und sammelt alle Tokens zu einer Antwort.
    """
    full_reply_parts = []
    for token in streamer.stream(messages=messages):
        full_reply_parts.append(token)
    return "".join(full_reply_parts).strip()
