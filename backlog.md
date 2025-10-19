# Backlog

| Nr. | Name | Beschreibung | Aufwand | Nutzen | Kategorie |
| --- | --- | --- | --- | --- | --- |
| 18  | Terminal-UI Logging fix                | Logging ausschließlich in Dateien schreiben, Konsole sauber halten             |   S     |   M    | Bugfix              |
| 19  | Web-UI "Neue Unterhaltung" im Stream   | ✅ Erledigt: Streaming sauber abbrechen, damit Button "Neue Unterhaltung" funktioniert |   M     |   L    | Bugfix              |
| 20  | Personas internationalisieren          | ✅ Erledigt: Personas ebenso wie UI-Texte für Deutsch und Englisch bereitstellen |   M     |   L    | UX/Technik          |
| 21  | spaCy-Internationalisierung            | Bei englischer Konfiguration automatisch das passende englische spaCy-Modell nutzen |   M     |   M    | Technische Basis    |
| 22  | Doku zweisprachig strukturieren        | ReadMe, Features und Backlog sinnvoll auf Deutsch und Englisch anbieten        |   M     |   M    | Dokumentation       |
| 3   | Healthchecks/Monitoring                | Statusseite (Ollama/VRAM), simple `/healthz` + VRAM-Probe                      |   S     |   M    | Technische Basis    |
| 4   | Gradio-Share + Basic Auth              | ✅ Erledigt: Extern testen, geschützt                                          |   S     |   M    | Technische Basis    |
| 5   | Modellauswahl in der UI                | Dropdown/Radio für verfügbare Modelle, explizit wählbar je Persona & Run       |   S     |   S    | UX/Technik          |
| 6   | LoRA-Feintuning-Pipeline               | IN ARBEIT → LoRA-Adapter für LeoLM13B                                          |   L     |   XL   | Forschung/Qualität  |
| 7   | Chatverläufe speichern/laden           | Sessions persistent (JSON/DB)                                                  |   M     |   L    | Technische Basis    |
| 8   | Ask-All (Broadcast)                    | Gleiche Frage nacheinander an Leah, Doris, Peter, Popcorn, getrennte Kontexte  |   S     |   M    | Orchestrierung      |
| 9   | Stage-Mode (Self-Talk)                 | Zwei+ Personas führen n Runden Dialog, Start nur mit 1 Auftaktsatz             |   M     |   L    | Orchestrierung      |
| 10  | Easter-Egg Logik                       | Stichwort → Nachsatz                                                           |   M     |   M    | Cooles Feature      |
| 12  | Karl (Kontextzusammenfasser)           | Verlauf komprimieren bei Bedarf durch LLM-Summary statt aktuelle Lösung        |   L     |   L    | Technische Basis    |
| 13  | STT/TTS (Sprache ↔ Text) MVP           | Einfache Sprach-I/O                                                            |   M     |   M    | Cooles Feature      |
| 14  | E-Mail an/von AI                       | Mail lesen/schreiben/versenden                                                 |   M     |   M    | Integration         |
| 15  | Tagesbrief (IoT + RSS)                 | Tägliche Kurzupdates                                                           |   M     |   M    | Cooles Feature      |
| 16  | Sandbox-/PDF-Funktionen                | Lokale Doku-Spielwiese                                                         |   L     |   M    | Cooles Feature      |
| 17  | First-Token schneller                  | Warm-up, Prompt-Diät, Stream-Puffer                                            |   M     |   L    | Performance         |
