@echo off
echo [1/3] Starte Ollama-Server in WSL ...
start wsl -d Ubuntu sh -c "ollama serve > /dev/null 2>&1 &"

timeout /t 3 >nul

echo [2/3] Lade deutsches Modell in WSL ...
start wsl -d Ubuntu ollama run marco/em_german_mistral_v01

timeout /t 1 >nul

echo [3/3] Starte Python-Interface ...
start python C:\J_KI\chat.py

exit
