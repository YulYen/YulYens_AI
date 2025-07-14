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
    elif re.search(r"\\bassistant: ", text, re.IGNORECASE):
        result = True
    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Text: {text.strip()} -> Selftalk? {result}\n")
    return result

def send_message_stream(messages: list, stream_url: str, model_name: str, enable_logging: bool, print_callback=None) -> str:
    """
    Sendet die Nachrichtenhistorie an die Ollama-API im Streaming-Modus.
    Gibt Token aus, prüft Selftalk nur zum Unterdrücken der Anzeige.
    """
    payload = {"model": model_name, "stream": True, "messages": messages}
    full_reply = ""
    visible_reply = ""
    buffer = ""
    is_selftalk = False

    response = requests.post(stream_url, json=payload, stream=True, timeout=60)
    response.raise_for_status()

    for line in response.iter_lines():
        if not line:
            continue
        data = json.loads(line.decode('utf-8'))
        content = data.get("message", {}).get("content", "")
        clean = re.sub(r"<dummy\d+>", "", content)
        full_reply += clean
        buffer += clean

        words = re.split(r'(\s+)', buffer)
        for i in range(len(words) - 1):
            token = words[i]
            if is_strong_selftalk(token, enable_logging):
                is_selftalk = True
            elif print_callback and not is_selftalk:
                print_callback(token)
                visible_reply += token

        buffer = words[-1]  # Letzter, evtl. unvollständiger Teil bleibt

    # Restpuffer
    if buffer.strip():
        if is_strong_selftalk(buffer, enable_logging):
            is_selftalk = True
        elif print_callback and not is_selftalk:
            print_callback(buffer)
            visible_reply += buffer

    return full_reply

def send_message_stream_gen(messages, stream_url, model_name, enable_logging):
    """
    Generator-Version von send_message_stream:
    Liefert jeden Token per yield, inklusive Selftalk-Filterung mit Wortpuffer.
    """
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True
    }

    try:
        response = requests.post(stream_url, json=payload, stream=True)

        buffer = ""

        for line in response.iter_lines():
            if not line:
                continue

            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                decoded = decoded[len("data: "):]

            if decoded.strip() == "[DONE]":
                break

            try:
                data = json.loads(decoded)
                token = data.get("message", {}).get("content", "")

                if not token:
                    continue

                buffer += token
                parts = re.split(r'(\s+)', buffer)
                for i in range(len(parts) - 1):
                    chunk = parts[i]
                    if not is_strong_selftalk(chunk, enable_logging):
                        yield chunk
                buffer = parts[-1]

            except json.JSONDecodeError as e:
                if enable_logging:
                    print(f"[ERROR] JSON decode failed: {decoded} ({e})")

        if buffer.strip() and not is_strong_selftalk(buffer, enable_logging):
            yield buffer

    except requests.RequestException as e:
        if enable_logging:
            print(f"[ERROR] Request failed: {e}")