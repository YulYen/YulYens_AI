import requests
import re
from colorama import Fore, Style, init

init(autoreset=True)  # Für Farbausgabe im Terminal

MODEL_NAME = "leah13b"
API_URL = "http://localhost:11434/api/generate"
WELCOME = f"\n{Fore.MAGENTA}👋 Willkommen bei Leah (Modell: {MODEL_NAME}){Style.RESET_ALL}\n"
PROMPT_SYMBOL = f"{Fore.GREEN}🟢 Du:{Style.RESET_ALL} "
RESPONSE_SYMBOL = f"{Fore.CYAN}💬 Leah:{Style.RESET_ALL} "

# Entfernt Dummy-Tags und glättet die Ausgabe
def clean_text(text: str) -> str:
    text = re.sub(r"<dummy\d+>", "", text)
    text = text.strip()
    return text

# Anfrage an Ollama-API
def ask_leah(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "stop": "<|assistant|>"
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").split("<|assistant|>")[0]
        return clean_text(text) or "(leere Antwort)"
    except requests.exceptions.RequestException as e:
        return f"❌ API-Fehler: {e}"
    except ValueError:
        return "❌ Ungültige Antwort von API"

# Hauptloop
def main():
    print(WELCOME)
    while True:
        try:
            user_input = input(PROMPT_SYMBOL)
            if user_input.lower() in ("exit", "quit", "bye"):
                print("👋 Auf Wiedersehen!")
                break

            response = ask_leah(user_input)
            print(f"{RESPONSE_SYMBOL}{response}\n")

        except KeyboardInterrupt:
            print("\n👋 Auf Wiedersehen!")
            break
        except Exception as e:
            print(f"❌ Unerwarteter Fehler: {e}")
            break

if __name__ == "__main__":
    main()
