# streaming_core_ollama.py
import traceback
import datetime, json, os, time
from core.utils import clean_token
from ollama import Client
import hashlib
import requests, logging
from typing import Optional
from security.tinyguard import BasicGuard, zeigefinger_message

def _apply_reminder_injection(messages: list[dict], reminder: str) -> list[dict]:
    """
    Fügt VOR der aktuellen User-Message eine kurze system-Reminder-Message ein.
    Minimalinvasiv: Wir gehen davon aus, dass die letzte Message die User-Frage ist.
    """
    if not messages:
        return messages

    # wir duplizieren die Liste, um nichts an der Caller-Referenz zu ändern
    patched = list(messages)
    # Reminder VOR die letzte Message (die aktuelle User-Frage) setzen
    patched.insert(len(patched) - 1, {"role": "system", "content": str(reminder)})
    logging.info(f"Reminder injected: {reminder}")
    return patched

class OllamaStreamer:
    """
    Wrapper um den Ollama‑Client mit Streaming‑Unterstützung.

    Der Streamer nimmt System‑Prompt, Persona‑Name, LLM‑Optionen und
    die Host‑URL des Ollama‑Servers entgegen.  Diese URL wird
    ausschließlich aus der Konfiguration gelesen; es gibt keinen
    stillen Fallback.  Die Klasse kümmert sich um Reminder‑Einblendung,
    Logging und Output‑Moderation via SecurityGuard.
    """
    def __init__(self, base_url, persona, persona_prompt, persona_options, model_name="plain", warm_up=False,
                 reminder=None, log_file="conversation.json", guard: Optional[BasicGuard] = None):
        self.model_name = model_name
        self.reminder = None
        self.persona = persona
        self.persona_prompt = persona_prompt
        self.persona_options = persona_options
        self._ollama_client = Client(host=base_url)
        if reminder:
            self.reminder = reminder
        self._logs_dir = "logs"
        os.makedirs(self._logs_dir, exist_ok=True)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
        self.guard: Optional[BasicGuard] = guard
       
        if warm_up:
            logging.info("Starte aufwärmen des Models:" + model_name)
            self._warm_up()

    def set_guard(self, guard: BasicGuard) -> None:
        self.guard = guard

    def _warm_up(self):
        logging.info(f"Sende Dummy zur Modellaktivierung: {self.model_name}")
        try:
            self._ollama_client.chathat(
                model=self.model_name,
                messages=[{"role": "user", "content": "..."}]
            )
            logging.info("Modell erfolgreich vorgewärmt.")
        except Exception:
            logging.error(f"Fehler beim Aufwärmen des Modells:\n{traceback.format_exc()}")

    def _append_conversation_log(self, role, content):
        try:
            entry = {
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "model": self.model_name,
                "bot" : self.persona,
                "options" : self.persona_options,
                "role": role,
                "content": content
            }
            with open(self.conversation_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.error(f"Fehler beim Schreiben des Conversation_log : {e}")

    def stream(self, messages):
        # Vorab: letzte User-Message prüfen (unverändert)
        if self.guard:
            for m in reversed(messages):
                if m.get("role") == "user":
                    res = self.guard.check_input(m.get("content") or "")
                    if not res["ok"]:
                        yield zeigefinger_message(res)
                        return
                    break

        if self.persona_prompt:
            messages = [{"role": "system", "content": self.persona_prompt}] + messages
            logging.debug(messages)

        if self.reminder:
            messages = _apply_reminder_injection(messages, self.reminder)

        # Letzte User-Nachricht ins Log (unverändert)
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_conversation_log("user", m["content"])
                break

        options = {}
        if self.persona_options:
            options = self.persona_options

         # --- Logging des vollständigen Payloads (Nachrichten und Optionen) ---+        # Wir berechnen eine kanonische JSON-Repräsentation und einen SHA-256‑Hash.
        try:
            _payload = {"messages": messages, "options": options}
            _canon = json.dumps(_payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            _hash = hashlib.sha256(_canon.encode('utf-8')).hexdigest()
            logging.debug(f"[OLLAMA INPUT] sha256={_hash} payload={_canon}")
        except Exception as _e:
            logging.warning(f"Unable to log Ollama input: {_e}")

        full_reply_parts = []
        try:
            t_start = time.time()
            first_token_time = None

            # stream_obj referenzieren, damit wir es im finally schließen können
            stream_obj = self._ollama_client.chat(
                model=self.model_name,
                keep_alive=600,
                messages=messages,
                options=options,
                stream=True
            )

            try:
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
                                yield zeigefinger_message({"reason": pol.get("reason") or "blocked_keyword", "detail": ""})
                                # Wichtig: nicht return, damit finally den Stream schließt
                                break
                            to_send = pol["text"]

                        seps = [" ", "\n", "\t", "!", "?"]
                        count = sum(to_send.count(sep) for sep in seps)
                        logging.debug(f"Buffer:" + to_send + "###" + str(count))
                        if count >= 1:
                            yield to_send
                            buffer = ""

                # nach der Schleife (auch bei break) evtl. Rest senden
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
                #  Stream IMMER schließen, wenn möglich
                try:
                    close = getattr(stream_obj, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass

            #Performance loggen (unverändert)
            t_end = time.time()
            logging.info(f"model {self.model_name} options: {options} t_first_ms: {int((first_token_time - t_start)*1000)} t_total_ms: {int((t_end - t_start)*1000)}")

            # Finale Assistant-Antwort loggen (unverändert)
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)
                try:
                    _canon_out = full_reply
                    _hash_out = hashlib.sha256(_canon_out.encode('utf-8')).hexdigest()
                    logging.debug(f"[OLLAMA OUTPUT] sha256={_hash_out} content={_canon_out}")
                except Exception as _e:
                    logging.warning(f"Unable to log Ollama output: {_e}")

        except Exception as e:
            logging.error(f"Fehler bei stream():\n{traceback.format_exc()}")
            err = f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"
            self._append_conversation_log("assistant", err)
            yield err


    def respond_one_shot(self, user_input: str, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout) -> str:
        messages = []

        # Feste Persona für respond_one_shot
        # persona = "PETER"
        persona = "DORIS"
        
        # 1. Wikipedia-Snippet suchen
        wiki_hint, topic_title, snippet = lookup_wiki_snippet(user_input, persona, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout)

        # 2. Wikipedia-Kontext (falls vorhanden) als System-Nachrichten anhängen
        if snippet:
            inject_wiki_context(messages, topic_title, snippet)

        # 3. Nutzerfrage als letzte Nachricht hinzufügen
        messages.append({"role": "user", "content": user_input})

        # Vor LLM: Input prüfen
        if self.guard:
            res_in = self.guard.check_input(user_input or "")
            if not res_in["ok"]:
                return zeigefinger_message(res_in)

        # 4. LLM ausführen und gesamte Antwort sammeln
        full_reply = run_llm_collect(self, messages)

        # Nach LLM: Output prüfen
        if self.guard:
            res_out = self.guard.check_output(full_reply or "")
            if not res_out["ok"]:
                return zeigefinger_message(res_out)
            
        return full_reply
    



def lookup_wiki_snippet(question: str, persona_name: str, keyword_finder, wiki_mode: str, proxy_port: int,
                        limit: int, timeout: tuple[float, float]) -> tuple[str, str, str]:
    snippet = None
    wiki_hint = None
    topic_title = None
    proxy_base = "http://localhost:"+str(proxy_port)

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
            logging.error(f"[WIKI EXC] topic='{topic}' err={e}")
            wiki_hint = f"🕵️‍♀️ *Fehler: Wikipedia nicht erreichbar.*{topic}"
    return (wiki_hint, topic_title, snippet)

def inject_wiki_context(history: list, topic: str, snippet: str) -> None:
    """
    Inject Wikipedia context into the message history as system prompts.

    Fügt (sofern ein Wikipedia-Snippet vorhanden ist) zwei System-Nachrichten in die gegebene 
    Nachrichten-History ein: eine Guardrail-Nachricht und eine Kontext-Nachricht mit dem Wiki-Text.

    Parameter:
        history (list): Das Nachrichten-Array (Liste von {"role": ..., "content": ...}-Dictionaries), 
                        das um den Wiki-Kontext erweitert werden soll.
        topic (str): Titel des Wikipedia-Themas, passend zum Snippet (z.B. "Albert_Einstein"). 
                     Wird in der Nachricht in lesbarer Form (Unterstriche→Leerzeichen) angezeigt.
        snippet (str): Der aus Wikipedia extrahierte Textausschnitt. Falls None oder leer, 
                       wird kein Kontext hinzugefügt.

    Rückgabe:
        None – die `history`-Liste wird direkt modifiziert.
    """
    if not snippet:
        return  # Nichts zu tun, wenn kein Wiki-Snippet vorhanden ist

    # Guardrail-Systemnachricht: Modell anweisen, nur diesen Kontext zu nutzen
    guardrail = (
        "Nutze ausschließlich den folgenden Kontext aus Wikipedia. "
        "Wenn etwas dort nicht steht, sag knapp, dass du es nicht sicher weißt."
    )
    history.append({"role": "system", "content": guardrail})

    # Kontext-Systemnachricht mit dem Wikipedia-Ausschnitt
    context_message = (
        f"Kontext zum Thema {topic.replace('_', ' ')}: "
        f"[Quelle: Wikipedia] {snippet}"
    )
    history.append({"role": "system", "content": context_message})

def run_llm_collect(streamer: OllamaStreamer, messages: list[dict]) -> str:
    """
    Execute the LLM stream and collect all tokens into a single response string.

    Parameter:
        streamer (OllamaStreamer): Der LLM-Streamer, der verwendet werden soll. Dieser stellt die 
                                   Methode `.stream(messages)` bereit, welche tokenweise antwortet.
        messages (list[dict]): Die Nachrichten-Historie (Liste von Message-Dictionaries), 
                               die an das LLM geschickt werden soll.

    Rückgabe:
        str: Die vollständige Antwort des LLM (alle empfangenen Tokens als zusammengesetzter String, 
             ohne führende/trailing Leerzeichen).
    """
    full_reply_parts = []
    for token in streamer.stream(messages=messages):
        full_reply_parts.append(token)
    # Alle gesammelten Token zu einem String verbinden und säubern
    full_reply = "".join(full_reply_parts).strip()
    return full_reply