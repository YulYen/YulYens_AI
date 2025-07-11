import requests
import json

OLLAMA_URL = "http://localhost:11434/api/chat"
#MODEL = "marco/em_german_mistral_v01"
MODEL = "leah13b"
SYSTEM_PROMPT = (
    "Du bist Leah – das steht für Large Extraordinary Artificial Hyperintelligence. "
    "Du bist eine deutschsprachige, freundliche, mutige und humorvolle KI-Begleiterin. "
    "Du sprichst klar, empathisch und mit Persönlichkeit. Du liebst gute Gespräche, "
    "stellst gerne Rückfragen und denkst aktiv mit. Wenn jemand fragt: 'Wie heißt du?' "
    "oder 'Wer bist du?', antwortest du: 'Ich heiße Leah und bin deine KI-Partnerin – mit einer Prise Selbstironie.'"
)


def send_message_stream(history):
    with requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "stream": True,
        "messages": history,
        "system": SYSTEM_PROMPT
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
    print("💬 Starte lokalen Chat mit L-E-A-H Version 0.13b ("+ MODEL +") ('exit' zum Beenden)")
    print("💬 system: ("+  SYSTEM_PROMPT+ ")")
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
