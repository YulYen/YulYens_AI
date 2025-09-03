# Backlog

| Nr. | Name                                   | Beschreibung                                                                 | Aufwand | Nutzen | Kategorie          |
|----:|----------------------------------------|-------------------------------------------------------------------------------|:------:|:-----:|--------------------|
| 1   | Unit-Tests: One-Shot via Fixtures      | Tests offline via PyTest-Fixtures, kein Server nötig                          |   S    |   L   | Technische Basis   |
| 2   | Mehr Unit-Tests                        | Kernpfade absichern                                                           |   S    |   L   | Technische Basis   |
| 3   | Healthchecks/Monitoring                | Statusseite (Ollama/VRAM), simple `/healthz` + VRAM-Probe                     |   S    |   M   | Technische Basis   |
| 4   | Gradio-Share + Basic Auth              | Extern testen, geschützt                                                      |   S    |   M   | Technische Basis   |
| 5   | Modellauswahl in der UI                | Dropdown/Radio für verfügbare Modelle, explizit wählbar je Persona & Run      |   S    |   L   | UX/Technik         |
| 6   | LoRA-Feintuning-Pipeline               | 100× GPT-OSS-20B Antworten kuratieren → LoRA-Adapter für Leo                  |   XL   |   XL  | Forschung/Qualität |
| 7   | Chatverläufe speichern/laden           | Sessions persistent (JSON/DB)                                                 |   M    |   L   | Technische Basis   |
| 8   | Ask-All (Broadcast)                    | Gleiche Frage nacheinander an Leah, Doris, Peter, Popcorn, getrennte Kontexte |   S    |   M   | Orchestrierung     |
| 9   | Stage-Mode (Self-Talk)                 | Zwei+ Personas führen n Runden Dialog, Start nur mit 1 Auftaktsatz            |   M    |   L   | Orchestrierung     |
| 10  | Easter-Egg Logik                       | Stichwort → Nachsatz                                                          |   M    |   M   | Cooles Feature     |
| 11  | Kontext-Overflow-Detektor + UI-Hinweis | „Leah holt Tee.“ + Trigger für Karl                                           |   M    |   L   | UX/Robustheit      |
| 12  | Karl (Kontextzusammenfasser)           | Verlauf komprimieren bei Bedarf                                               |   XL   |   XL  | Technische Basis   |
| 13  | STT/TTS (Sprache ↔ Text) MVP           | Einfache Sprach-I/O                                                           |   M    |   M   | Cooles Feature     |
| 14  | E-Mail an/von AI                       | Mail lesen/schreiben/versenden                                                |   M    |   M   | Integration        |
| 15  | Tagesbrief (IoT + RSS)                 | Tägliche Kurzupdates                                                          |   M    |   M   | Cooles Feature     |
| 16  | Sandbox-/PDF-Funktionen                | Lokale Doku-Spielwiese                                                        |   L    |   M   | Cooles Feature     |
| 17  | First-Token schneller                  | Warm-up, Prompt-Diät, Stream-Puffer                                           |   M    |   L   | Performance        |
