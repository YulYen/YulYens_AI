# leah_terminal_chat.py

import subprocess
import json
import re

# Modellname (muss zuvor via ollama create erzeugt worden sein)
MODEL_NAME = "LEAH13b"

# Filtert Dummy-Tags wie <dummy12345> aus der Antwort
def clean_output(text):
    return re.sub(r"<dummy\d+>", "", text).strip()

# Schickt einen Prompt an ollama und gibt die bereinigte Antwort zurück
def ask_leah(prompt):
    try:
        # Aufruf von ollama innerhalb der WSL
        process = subprocess.run(
            ["ollama", "run", MODEL_NAME],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60
        )

        stdout = process.stdout.decode("utf-8").strip()
        stderr = process.stderr.decode("utf-8").strip()

        if process.returncode != 0:
            return f"[Ollama-Fehlercode {process.returncode}]\nSTDERR:\n{stderr or '(leer)'}\nSTDOUT:\n{stdout or '(leer)'}"

        if stderr := process.stderr.decode("utf-8", errors="replace").strip():
            print(f"⚠️  [ollama STDERR]:\n{stderr}\n")


        # Dummy-Tags filtern (z. B. <dummy32006>)
        clean = re.sub(r"<dummy\d+>", "", stdout)
        clean = clean.replace("\\n", "\n").replace('\\"', '"').strip()
        return clean.strip() or "(leere Antwort)"

    except subprocess.TimeoutExpired:
        return "[Timeout] Der Aufruf von ollama hat länger als 60 Sekunden gedauert."
    except FileNotFoundError:
        return "[Fehler] Das Kommando 'ollama' wurde nicht gefunden – läuft dein Modell in der WSL?"
    except Exception as e:
        return f"[Unerwarteter Fehler] {type(e).__name__}: {str(e)}"
# Hauptschleife
def main():
    print(f"👋 Willkommen bei Leah (Modell: {MODEL_NAME})\n")
    while True:
        try:
            user_input = input("🟢 Du: ")
            if user_input.lower() in {"exit", "quit", "bye"}:
                print("👋 Bis bald!")
                break

            response = ask_leah(user_input)
            print(f"💬 Leah: {response}\n")

        except KeyboardInterrupt:
            print("\n👋 Gespräch beendet.")
            break

if __name__ == "__main__":
    main()
