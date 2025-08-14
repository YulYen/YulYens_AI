# streaming_core_ollama.py
import traceback
import datetime, json, os
from ollama import chat
from streaming_helper import clean_token
import requests, logging


class OllamaStreamer:
    def __init__(self, model_name="plain", warm_up=True, system_prompt=None, log_file="conversation.json"):
        self.model_name = model_name
        self.system_prompt = system_prompt
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
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
            logging.info(messages)

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



    def respond_one_shot(self, user_input: str, keyword_finder, wiki_mode, wiki_proxy_base, wiki_snippet_limit) -> str:

        messages = []
        
        # 1. Wikipedia-Snippet suchen
        wiki_hint, topic_title, snippet = lookup_wiki_snippet(user_input, keyword_finder, wiki_mode, wiki_proxy_base, wiki_snippet_limit)

        # 2. Wikipedia-Kontext (falls vorhanden) als System-Nachrichten anhängen
        if snippet:
            inject_wiki_context(messages, topic_title, snippet)

        # 3. Nutzerfrage als letzte Nachricht hinzufügen
        messages.append({"role": "user", "content": user_input})

        # 4. LLM ausführen und gesamte Antwort sammeln
        full_reply = run_llm_collect(self, messages)
        return full_reply
    



def lookup_wiki_snippet(question: str, keyword_finder, wiki_mode: str, proxy_base: str, limit: int) -> tuple[str, str, str]:
    """
    Find a relevant Wikipedia article snippet for the given question.

    This function uses a keyword finder to extract a topic from the user question and then retrieves 
    a short snippet of text from the corresponding Wikipedia article via a proxy API.

    Parameter:
        question (str): Die Nutzerfrage, aus der das Wikipedia-Thema extrahiert wird.
        keyword_finder: Ein Objekt mit Methode `find_top_keyword(text)`, um das relevanteste Schlüsselwort (Thema) zu finden.
        wiki_mode (str): Betriebsmodus für Wikipedia ("online" oder "offline"). 
                         Wenn "online", werden Online-Daten bevorzugt (online_flag=1), sonst offline (online_flag=0).
        proxy_base (str): Basis-URL des Wikipedia-Proxy-Servers (wird mit Topic und Parametern kombiniert).
        limit (int): Maximale Länge des zurückgegebenen Snippet-Textes in Zeichen.

    Rückgabe:
        tuple[str, str, str]: (wiki_hint, topic_title, snippet), alle Strings oder None.
        - wiki_hint: Hinweistext oder Fehlermeldung (z.B. "*Kein Eintrag gefunden:*<Topic>" bei 404, 
                     "*Wikipedia nicht erreichbar.*<Topic>" bei anderem Fehler). None, falls kein spezieller Hinweis nötig.
        - topic_title: Der gefundene Thema-Titel (als String, wie in Wikipedia verwendet), oder None, wenn kein Thema gefunden wurde.
        - snippet: Ein Auszug aus dem Wikipedia-Artikel zum Thema (bis zu `limit` Zeichen), 
                   oder None, falls kein Text gefunden/abgerufen wurde.
    """
    snippet = None
    wiki_hint = None
    topic_title = None

    if not keyword_finder:
        return (None, None, None)

    # Bestimmen des Top-Schlüsselworts (Thema) aus der Frage
    topic = keyword_finder.find_top_keyword(question)
    if topic:
        # Wikipedia-Proxy mit entsprechendem Modus (online/offline) abfragen
        online_flag = "1" if wiki_mode == "online" else "0"
        url = f"{proxy_base.rstrip('/')}/{topic}?json=1&limit={limit}&online={online_flag}"
        try:
            r = requests.get(url, timeout=(3.0, 8.0))
            if r.status_code == 200:
                data = r.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[:limit]
                wiki_hint = data.get("wiki_hint")
                topic_title = topic
            elif r.status_code == 404:
                # Kein Wikipedia-Artikel gefunden
                wiki_hint = f"🕵️‍♀️ *Kein Eintrag gefunden:*{topic}"
            else:
                # Anderer Fehler (Wikipedia nicht erreichbar etc.)
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