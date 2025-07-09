""# chat.py: Wahl des Ollama-Modells (Mistral, Intel-Neural, Leah) und Prüfung auf laufenden Ollama-Server
import subprocess
import requests
import json
import time
import os

# Konfiguration
OLLAMA_URL = "http://localhost:11434/api/chat"
AVAILABLE_MODELS = {
    "1": ("Mistral 7B German", "marco/em_german_mistral_v01"),
    "2": ("Intel Neural Chat", "neural-chat"),
    "3": ("Leah (Leah13B)", "leah13b"),
}

# Funktion: Ollama-Server-Verfügbarkeit prüfen
def check_ollama_running():
    print("🔍 Warte auf Ollama-Server...")
    for i in range(20):  # Max. 10 Sekunden warten
        try:
            r = requests.get("http://localhost:11434")
            if r.status_code == 200:
                print("✅ Ollama-Server läuft.")
                return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)

    print("❌ Fehler: Ollama-Server ist nicht erreichbar.")
    print("👉 Bitte prüfe, ob WSL korrekt konfiguriert ist oder starte manuell mit 'ollama serve'")
    exit(1)

# Auswahlmenü für Modell
def choose_model():
    print("Bitte wähle ein Modell aus:")
    for key, (name, _) in AVAILABLE_MODELS.items():
        print(f"  {key}. {name}")
    choice = None
    while choice not in AVAILABLE_MODELS:
        choice = input("Deine Wahl [1/2/3]: ").strip()
    selected_name, selected_id = AVAILABLE_MODELS[choice]
    print(f"Ausgewählt: {selected_name} ({selected_id})")
    return selected_id

# Streaming-Anfrage an Ollama
def send_message_stream(history, model):
    response = requests.post(
        OLLAMA_URL,
        json={"model": model, "stream": True, "messages": history},
        stream=True
    )
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
            except json.JSONDecodeError:
                continue
    print()
    return full_reply

# Hauptprogramm
def main():
    if not os.path.exists('.git'):
        print("💡 Tipp: Du kannst dieses Verzeichnis mit 'git init' versionieren, um Fortschritte zu sichern.")

    check_ollama_running()
    model = choose_model()

    print(f"💬 Starte Chat mit {model} ('exit' zum Beenden)")
    history = []
    while True:
        user_input = input("🧑 Du: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        history.append({"role": "user", "content": user_input})
        try:
            reply = send_message_stream(history, model)
            history.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"⚠️ Fehler: {e}")

if __name__ == "__main__":
    main()
