import requests
import json

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "marco/em_german_mistral_v01"
SYSTEM_PROMPT = "Du bist Leah, eine extrem hilfsbereite, freundliche und humorvolle deutschsprachige KI-Partnerin. Du sprichst klar und empathisch und gibst ausführliche Antworten für eine angeregte Konversation. Du bist auch mutig und stellst, wenn nötig, Vermutungen auf."


def send_message_stream(history):
    with requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "stream": True,
        "system": SYSTEM_PROMPT,
        "messages": history
    }, stream=True) as response:
        response.raise_for_status()

        full_reply = ""
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode('utf-8'))
                    content = data.get("message", {}).get("content")
                    if content:
                        print(content, end="", flush=True)
                        full_reply += content
                except json.JSONDecodeError as e:
                    print("\n⚠️ JSON-Fehler:", e)
                    print("Antwortzeile:", line)
        print()  # Neue Zeile nach der Ausgabe
        return full_reply

def main():
    print("💬 Starte lokalen Chat mit L-E-A-H Version 0.0a ('exit' zum Beenden)")
    history = []

    while True:
        user_input = input("🧑 Du: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break

        history.append({"role": "user", "content": user_input})
        try:
            reply = send_message_stream(history)
            history.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"\n⚠️ Fehler: {e}\n")

if __name__ == "__main__":
    main()
