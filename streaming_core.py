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


def send_message_stream_gen(messages, stream_url, model_name, enable_logging):
    """
    Generator-Version von send_message_stream:
    Liefert jedes Wort oder Satzzeichen per yield,
    ignoriert aber ab Start von Selftalk dauerhaft alle weiteren Tokens.
    """
    payload = {"model": model_name, "messages": messages, "stream": True}
    is_selftalk = False
    buffer = ""

    try:
        response = requests.post(stream_url, json=payload, stream=True)

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
                # Dummy-Bereinigung
                token = re.sub(r"<dummy\d+>", "", token)
                if not token:
                    continue

                buffer += token
                parts = re.split(r'(\s+)', buffer)
                for i in range(len(parts) - 1):
                    chunk = parts[i]
                    if is_strong_selftalk(chunk, enable_logging):
                        is_selftalk = True
                        break
                    if not is_selftalk:
                        yield chunk
                if is_selftalk:
                    break
                buffer = parts[-1]
            except json.JSONDecodeError as e:
                if enable_logging:
                    print(f"[ERROR] JSON decode failed: {decoded} ({e})")

        if buffer.strip() and not is_selftalk:
            yield buffer

    except requests.RequestException as e:
        if enable_logging:
            print(f"[ERROR] Request failed: {e}")
