# streaming_core.py
import requests
import json
import re
from datetime import datetime

LOGFILE = "selftalk_log.txt"

# Filter für echten Selftalk (nicht legitime Antworten)
def is_strong_selftalk(text: str, enable_logging: bool) -> bool:
    result = False
    if re.search(r"<\|user\|>", text):
        result = True
    elif re.search(r"<\|system\|>", text):
        result = True
    elif re.match(r"\s*(assistant:)", text, re.IGNORECASE):
        result = True
    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Text: {text.strip()} -> Selftalk? {result}\n")
    return result


def send_message_stream(messages: list, stream_url: str, model_name: str, enable_logging: bool) -> str:
    """
    Sendet die Nachrichtenhistorie an die Ollama-API im Streaming-Modus.
    Bricht ab, sobald Selftalk erkannt wird.
    """
    payload = {"model": model_name, "stream": True, "messages": messages}
    full_reply = ""
    response = requests.post(stream_url, json=payload, stream=True, timeout=60)
    response.raise_for_status()

    buffer = ""
    for line in response.iter_lines():
        if not line:
            continue
        data = json.loads(line.decode('utf-8'))
        content = data.get("message", {}).get("content", "")
        clean = re.sub(r"<dummy\d+>", "", content)
        buffer += clean
        # Prüfen, ob buffer an Wortgrenze endet (Leerzeichen oder Zeilenumbruch)
        if re.search(r"\s$", buffer):
            if is_strong_selftalk(buffer, enable_logging):
                break
            full_reply += buffer
            print(buffer, end="", flush=True)
            buffer = ""
    # Restpuffer
    if buffer and not is_strong_selftalk(buffer, enable_logging):
        full_reply += buffer
        print(buffer, end="", flush=True)
    return full_reply