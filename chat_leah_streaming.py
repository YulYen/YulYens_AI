import requests
import json
import re
from colorama import Fore, Style, init
from datetime import datetime

# Farbausgabe aktivieren
init(autoreset=True)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leah13b1"
LOGFILE = "selftalk_log.txt"
ENABLE_LOGGING = False


# Nachrichtenverlauf für Kontext
history = []

# Filter für echten Selftalk (nicht legitime Antworten)
def is_strong_selftalk(text):
    result = False
    if re.search(r"<\|user\|>", text):
        result = True
    elif re.search(r"<\|system\|>", text):
        result = True
    elif re.match(r"\s*(assistant:)", text, re.IGNORECASE):
        result = True
    if ENABLE_LOGGING:
        # Loggen
        with open(LOGFILE, "a", encoding="utf-8") as log:
            log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Text: {text.strip()} -> Selftalk? {result}\n")
    return result

# Farben und Begrüßung
print(f"{Fore.MAGENTA}💬 Starte lokalen Chat mit Leah ({MODEL_NAME}) ('exit' zum Beenden){Style.RESET_ALL}")

# Hauptfunktion: Streaming mit Wort-basiertem Selftalk-Abbruch bei Leerzeichen

def send_message_stream(messages):
    payload = {"model": MODEL_NAME, "stream": True, "messages": messages}
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60) as response:
            response.raise_for_status()
            full_reply = ""
            print(f"{Fore.CYAN}🤖 Leah:{Style.RESET_ALL} ", end="", flush=True)

            buffer = ""
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode('utf-8'))
                    content = data.get("message", {}).get("content", "")
                except json.JSONDecodeError:
                    continue

                # Dummy-Tags entfernen und Puffer auffüllen
                clean = re.sub(r"<dummy\d+>", "", content)
                buffer += clean

                # Prüfen, ob buffer ein Leerzeichen oder Zeilenumbruch enthält (nicht nur am Ende)
                if re.search(r"\s", buffer):
                    if is_strong_selftalk(buffer):
                        break
                    print(buffer, end="", flush=True)
                    full_reply += buffer
                    buffer = ""

            # Restpuffer ausgeben, wenn kein Selftalk
            if buffer and not is_strong_selftalk(buffer):
                print(buffer, end="", flush=True)
                full_reply += buffer

            print()  # Zeilenumbruch am Ende
            return full_reply
    except requests.exceptions.RequestException as e:
        print(f"\n❌ API-Fehler: {e}\n")
        return ""

# Hauptloop
while True:
    try:
        user_input = input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()
        print()  # Leerzeile
        if user_input.lower() in ("exit", "quit"):  
            print("👋 Auf Wiedersehen!")
            break
        history.append({"role": "user", "content": user_input})
        reply = send_message_stream(history)
        history.append({"role": "assistant", "content": reply})
    except KeyboardInterrupt:
        print("\n👋 Auf Wiedersehen!")
        break
    except Exception as e:
        print(f"\n❌ Fehler: {e}\n")
        break
