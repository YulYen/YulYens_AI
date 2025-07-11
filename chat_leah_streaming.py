import requests
import json
import re
from colorama import Fore, Style, init

# Farbausgabe aktivieren
init(autoreset=True)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leah13b"

# Farben und Begrüßung
print(f"{Fore.MAGENTA}💬 Starte lokalen Chat mit L-E-A-H Version 13b ({MODEL_NAME}) ('exit' zum Beenden){Style.RESET_ALL}")

# Nachrichtenverlauf für Kontext
history = []

# Streaming-Funktion mit Dummy-Filter und Farbausgabe
def send_message_stream(messages):
    with requests.post(OLLAMA_URL, json={
        "model": MODEL_NAME,
        "stream": True,
        "messages": messages
    }, stream=True) as response:
        response.raise_for_status()

        full_reply = ""
        print(f"{Fore.CYAN}🤖 Leah:{Style.RESET_ALL} ", end="", flush=True)
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode('utf-8'))
                    content = data.get("message", {}).get("content")
                    if content:
                        # Dummy-Tags entfernen und ausgeben
                        clean = re.sub(r"<dummy\d+>", "", content)
                        print(clean, end="", flush=True)
                        full_reply += clean
                except json.JSONDecodeError as e:
                    print(f"\n⚠️ JSON-Fehler: {e}")
                    print(f"Antwortzeile: {line}")
        print()  # Neue Zeile nach Ausgabe
        return full_reply

# Hauptloop
while True:
    try:
        user_input = input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()
        if user_input.lower() in ("exit", "quit"): break

        history.append({"role": "user", "content": user_input})
        reply = send_message_stream(history)
        history.append({"role": "assistant", "content": reply})

    except KeyboardInterrupt:
        print("\n👋 Auf Wiedersehen!")
        break
    except Exception as e:
        print(f"\n❌ Fehler: {e}\n")
