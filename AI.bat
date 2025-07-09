@echo off
REM Ollama in WSL starten, falls nicht schon gestartet
wsl -d Ubuntu -- bash -c "pgrep -f ollama || nohup ollama serve > /dev/null 2>&1 &"

REM Warten, bis Ollama stabil läuft
echo Warte 10 Sekunden, bis Ollama-Server bereit ist...
timeout /t 10 /nobreak > nul

REM Python Chat starten
echo Starte Python Chat Interface...
python chat.py
