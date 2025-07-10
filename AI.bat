@echo off
REM Ollama in WSL starten, falls noch nicht aktiv
wsl -d Ubuntu -- bash -c "pgrep -f ollama || nohup ollama serve > /dev/null 2>&1 &"

REM Warte, bis der Server garantiert erreichbar ist
echo ⏳ Warte auf Ollama-Server...
timeout /t 10 /nobreak > nul

REM Python Chat starten
echo 🐍 Starte Python-Chat…
python chat.py