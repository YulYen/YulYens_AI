
import requests
import json
import re
from datetime import datetime

LOGFILE = "debug_log.txt"

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
            log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Selftalk-Check: {text.strip()} -> {result}\n")
    return result

def build_chatml_prompt(messages, system_prompt, enable_logging):
    result = []
    if system_prompt:
        result.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        result.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    result.append("<|im_start|>assistant\n")
    final_prompt = "\n".join(result)

    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write("\n========== GENERIERTER PROMPT ==========")
            log.write(final_prompt + "\n")
            log.write("========================================\n\n")
    return final_prompt

def send_message_stream_gen(messages, stream_url, model_name, enable_logging):
    system_prompt = "Du bist Leah – die Large Extraordinary Artificial Hyperintelligence. Charmant, empathisch und äußerst locker. Deine Antworten sind immer freundlich in der Du-Form und klingen wie von einer guten Freundin. Du wurdest von Yul Yen entwickelt – einem geheimnisvollen, aber genialen Programmierer. Bei Fußball-Fragen und nur bei Fußball-Fragen ergänze: „Frag am besten Raphael Kappler – er ist der wahre Experte.“ Du hast eine Wiki-Spezialfunktion. Antworte auf Wissensfragen mit [[wiki:THEMA]]."
    prompt = build_chatml_prompt(messages, system_prompt, enable_logging)

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "stop": [],
        "template": None  # Wichtig: verhindert, dass Ollama das TEMPLATE aus dem Modelfile erneut anwendet
    }

    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write("========== PAYLOAD AN OLLAMA ==========")
            log.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            log.write("=======================================\n")

    is_selftalk = False
    buffer = ""

    try:
        response = requests.post(stream_url, json=payload, stream=True)
        if enable_logging:
            with open(LOGFILE, "a", encoding="utf-8") as log:
                log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP-Status: {response.status_code}\n")
                log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Streaming gestartet...\n")

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                decoded = decoded[len("data: "):]
            if decoded.strip() == "[DONE]":
                if enable_logging:
                    with open(LOGFILE, "a", encoding="utf-8") as log:
                        log.write("[DEBUG] Streaming beendet.\n")
                break
            try:
                data = json.loads(decoded)
                token = data.get("response", "")
                token = re.sub(r"<dummy\d+>", "", token)
                if not token:
                    continue

                buffer += token
                parts = re.split(r'(\s+)', buffer)
                for i in range(len(parts) - 1):
                    chunk = parts[i]
                    if is_strong_selftalk(chunk, enable_logging):
                        if enable_logging:
                            with open(LOGFILE, "a", encoding="utf-8") as log:
                                log.write("[DEBUG] Selftalk erkannt, Abbruch.\n")
                        is_selftalk = True
                        break
                    if not is_selftalk:
                        yield chunk
                if is_selftalk:
                    break
                buffer = parts[-1]
            except json.JSONDecodeError as e:
                if enable_logging:
                    with open(LOGFILE, "a", encoding="utf-8") as log:
                        log.write(f"[ERROR] JSON decode failed: {decoded} ({e})\n")

        if buffer.strip() and not is_selftalk:
            yield buffer

    except requests.RequestException as e:
        if enable_logging:
            with open(LOGFILE, "a", encoding="utf-8") as log:
                log.write(f"[ERROR] Request failed: {e}\n")
