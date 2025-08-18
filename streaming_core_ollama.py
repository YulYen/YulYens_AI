# streaming_core_ollama.py
import traceback
import datetime, json, os
from ollama import chat
from core.utils import clean_token
import requests, logging


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
    logging.info("Reminder injected:" + str(reminder) )
    return patched

class OllamaStreamer:
    def __init__(self, persona, model_name="plain", warm_up=False, reminder=None, log_file="conversation.json"):
        self.model_name = model_name
        self.reminder = None
        self.persona_prompt = persona
        if reminder: 
            self.reminder =  " ".join(reminder)
        self._logs_dir = "logs"
        os.makedirs(self._logs_dir, exist_ok=True)
        self.conversation_log_path = os.path.join(self._logs_dir, log_file)
       
        if warm_up:
            logging.info("Starte aufwärmen des Models:" + model_name)
            self._warm_up()

    def _warm_up(self):
        logging.info(f"Sende Dummy zur Modellaktivierung: {self.model_name}")
        try:
            chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "..."}]
            )
            logging.info("Modell erfolgreich vorgewärmt.")
        except Exception:
            logging.error(f"Fehler beim Aufwärmen des Modells:\n{traceback.format_exc()}")

    def _append_conversation_log(self, role, content):
        try:
            entry = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "model": self.model_name,
                "role": role,
                "content": content
            }
            with open(self.conversation_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.error(f"Fehler beim Schreiben des Conversation_log : {e}")

    def stream(self, messages):
        if self.persona_prompt:
            messages = [{"role": "system", "content": self.persona_prompt}] + messages
            logging.debug(messages)

        if self.reminder:
            messages = _apply_reminder_injection(messages, self.reminder)


        # Letzte User-Nachricht ins zentrale Log schreiben
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                self._append_conversation_log("user", m["content"])
                break

        full_reply_parts = []
        try:
            # Eigentliches Streaming
            stream = chat(
                model=self.model_name,
                messages=messages,
                stream=True
            )
            buffer = ""
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    cleaned = clean_token(token)
                    if not cleaned:
                        continue
                    buffer += cleaned
                    full_reply_parts.append(cleaned)

                    seps = [" ", "\n", "\t", ".", "?"]
                    count = sum(buffer.count(sep) for sep in seps)
                    logging.debug(f"Buffer:" + buffer + "###" + str(count))
                    if count >= 1:
                        yield buffer
                        buffer = ""

            if buffer:
                yield buffer

            # Finale Assistant-Antwort loggen
            full_reply = "".join(full_reply_parts).strip()
            if full_reply:
                self._append_conversation_log("assistant", full_reply)

        except Exception as e:
            logging.error(f"Fehler bei stream():\n{traceback.format_exc()}")
            err = f"[FEHLER] Ollama antwortet nicht korrekt: {str(e)}"
            self._append_conversation_log("assistant", err)
            yield err



    def respond_one_shot(self, user_input: str, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout) -> str:
        messages = []

        # Feste Persona für respond_one_shot
        persona = "PETER"
        
        # 1. Wikipedia-Snippet suchen
        wiki_hint, topic_title, snippet = lookup_wiki_snippet(user_input, persona, keyword_finder, wiki_mode, wiki_proxy_port, wiki_snippet_limit, wiki_timeout)

        # 2. Wikipedia-Kontext (falls vorhanden) als System-Nachrichten anhängen
        if snippet:
            inject_wiki_context(messages, topic_title, snippet)

        # 3. Nutzerfrage als letzte Nachricht hinzufügen
        messages.append({"role": "user", "content": user_input})

        # 4. LLM ausführen und gesamte Antwort sammeln
        full_reply = run_llm_collect(self, messages)
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