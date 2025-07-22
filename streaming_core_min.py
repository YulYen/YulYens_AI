
import requests
import json
from datetime import datetime

LOGFILE = "debug_plain_chatml_log.txt"

def build_chatml_prompt(messages, system_prompt, enable_logging):
    result = []
    if system_prompt:
        result.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
    for msg in messages:
        result.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    result.append("<|im_start|>assistant\n")
    prompt = "\n".join(result)

    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write("\n========== CHATML PROMPT ==========")
            log.write(prompt + "\n")
            log.write("===================================\n\n")
    return prompt

def send_message_stream_gen(messages, stream_url, model_name, enable_logging):
    system_prompt = "Du bist ein hilfsbereiter KI-Assistent."
    prompt = build_chatml_prompt(messages, system_prompt, enable_logging)

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "template": """
<|im_start|>system
{system_message}<|im_end|>
<|im_start|>user
{prompt}<|im_end|>
<|im_start|>assistant
""",
    }

    if enable_logging:
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write("========== CHATML PAYLOAD ==========")
            log.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            log.write("====================================\n")

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
                if token:
                    buffer += token
                    yield token
            except json.JSONDecodeError as e:
                if enable_logging:
                    with open(LOGFILE, "a", encoding="utf-8") as log:
                        log.write(f"[ERROR] JSON decode failed: {decoded} ({e})\n")

        if buffer.strip() and enable_logging:
            with open(LOGFILE, "a", encoding="utf-8") as log:
                log.write(f"[FINAL OUTPUT] {buffer}\n")

    except requests.RequestException as e:
        if enable_logging:
            with open(LOGFILE, "a", encoding="utf-8") as log:
                log.write(f"[ERROR] Request failed: {e}\n")
            
