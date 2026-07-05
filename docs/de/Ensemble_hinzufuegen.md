# Eigenes Ensemble hinzufügen

Dieses Dokument beschreibt, wie du ein neues Persona-Ensemble für Yul Yen’s AI Orchestra anlegst. Ein Ensemble bündelt alle Personas, ihre Spracheinstellungen sowie optionale Medien-Dateien. Du kannst bestehende Personas anpassen oder komplett neue Charaktere erstellen.

## Verzeichnisstruktur verstehen

Alle Ensembles liegen im Verzeichnis [`ensembles/`](../../ensembles). Ein Ensemble besteht mindestens aus:

- `personas_base.yaml` – Globale Einstellungen (Name, LLM-Optionen, Defaults)
- `locales/<sprache>/personas.yaml` – Sprachabhängige Beschreibungen, Prompts und Metadaten
- `static/personas/<NAME>/{thumb.webp,full.webp}` – (optional) Web-UI-Avatare

> 💡 Tipp: Das Beispiel-Ensemble [`ensembles/examples/spaceship_crew`](../../ensembles/examples/spaceship_crew) zeigt eine vollständige Beispielstruktur mit Lokalisierung (de/en) und Avatar-Bildern. Starten lässt es sich per `python src/launch.py -e examples/spaceship_crew`.

## Schritt-für-Schritt-Anleitung

1. **Neues Verzeichnis anlegen**
   ```bash
   cp -r ensembles/classic ensembles/mein_ensemble
   rm -rf ensembles/mein_ensemble/locales/*
   ```
   Passe den Ordnernamen an (nur Kleinbuchstaben und `_` oder `-` haben sich bewährt). Entferne anschließend nicht benötigte Sprachen.

2. **`personas_base.yaml` anpassen**
   - Lege unter `personas:` alle Charaktere an.
   - `name` muss eindeutig sein und dient gleichzeitig als Schlüssel für Bilder.
   - `llm_options` überschreibt globale Einstellungen wie Temperatur, Seed oder `num_ctx`.
   - `defaults.featured: true` markiert eine Persona für die Web-UI als Startauswahl.

3. **Sprachdateien erstellen**
   - Erzeuge für jede unterstützte Sprache einen Unterordner, z. B. `locales/de/`.
   - Lege dort `personas.yaml` mit folgendem Aufbau an:
     ```yaml
     personas:
       LEAH:
         name: "LEAH"
         description: "Kurze Beschreibung für die Web-UI"
         prompt: |-
           Mehrzeiliger Systemprompt …
     ```
   - Optional: Felder wie `drink`, `greeting` oder eigene Schlüssel werden an die UI weitergereicht.

4. **Medien hinzufügen (optional)**
   - Lege für jede Persona einen Ordner `static/personas/<NAME>/` an.
   - `thumb.webp` (quadratisch, ~256 px) dient als Avatar-Vorschau.
   - `full.webp` (größer, ~512–768 px) wird in der Detailansicht gezeigt.
   - Nutze WebP für geringe Dateigrößen. Andere Formate werden nicht automatisch konvertiert.

5. **Ensemble testen**
   - Starte das Projekt über den CLI-Parameter `-e`:
     ```bash
     python src/launch.py -e mein_ensemble
     ```
   - Alternativ kannst du in `config.yaml` den Eintrag `ensemble: "mein_ensemble"` hinzufügen, wenn du das CLI-Flag nicht setzen möchtest.
   - Prüfe sowohl Terminal- als auch Web-UI (falls aktiviert), ob alle Personas erscheinen und Antworten liefern.

6. **Automatisierte Tests prüfen (optional)**
   - Führe `pytest` aus, wenn du sicherstellen möchtest, dass bestehende Tests weiterlaufen.
   - Für Projekte mit CI empfiehlt es sich, Dummy-Modelle (z. B. `core.backend: "dummy"`) zu konfigurieren.

## Zeitaufwand

| Variante | Geschätzter Aufwand | Hinweise |
| --- | --- | --- |
| Ohne KI-Bilderstellung | ca. 45–90 Minuten | Struktur anlegen, Prompts schreiben, Testlauf durchführen |
| Mit KI-Bilderstellung | ca. 60–120 Minuten | Zusätzlich Zeit für Prompting, Generierung, Nachbearbeitung und WebP-Konvertierung einplanen |

Die Angaben verstehen sich als grober Rahmen für ein Ensemble mit 3–4 Personas. Umfangreiche Storytelling-Prompts oder manuelle Bildbearbeitung können den Aufwand erhöhen.

## Weiterführende Hinweise

- Halte die Persona-Namen konsistent zwischen `personas_base.yaml`, Lokalisierungsdateien und Bildordnern.
- Nutze Versionskontrolle (Git), um Änderungen an Prompts oder Optionen nachverfolgen zu können.
- Dokumentiere Besonderheiten deiner Personas (z. B. zusätzliche Werkzeuge oder Kontextquellen) für spätere Pflege.
- Prüfe bei Bedarf Sicherheitsrichtlinien (PII-Filter, Prompt Guard), falls deine Personas unkonventionelle Antworten generieren sollen.
