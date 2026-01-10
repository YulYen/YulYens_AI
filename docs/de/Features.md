# Funktionalitäten

## Mehrere KI-Personas

Das System umfasst vier unterschiedliche KI-Personas mit eigenen Charakteren. Alle Personas nutzen das gleiche zugrundeliegende Sprachmodell, unterscheiden sich jedoch durch spezielle System-Prompts, die ihren Sprachstil und Ton festlegen:

- **Leah** – empathisch und freundlich  
- **Doris** – sarkastisch und schlagfertig humorvoll  
- **Peter** – faktenorientiert, analytisch und sachlich  
- **Popcorn** – verspielt und kindgerecht (Katzen-Persona)  

Die Auswahl der Persona erfolgt entweder beim Start (Terminal-UI) oder über die Weboberfläche. Jede Persona reagiert im entsprechenden Stil auf Nutzeranfragen.

## Benutzeroberflächen (UI)

Zwei verschiedene Benutzeroberflächen stehen zur Verfügung, auswählbar über die Konfiguration (`ui.type`):

- **Terminal-UI** – Konsolenbasierte Chat-Anwendung mit farbig hervorgehobenen Rollen (Nutzer/KI). Bei Start wird die gewünschte Persona per Menü ausgewählt. Nutzereingaben werden direkt in der Konsole eingegeben, und die KI-Antwort erscheint tokenweise gestreamt. Es gibt einfache Befehle wie `exit` zum Beenden und `clear` für einen neuen Chatverlauf.
- **Web-UI** – Webbasierte Oberfläche (Gradio), die im Browser verfügbar ist. Sie bietet eine grafische Persona-Auswahl (mit Avatar-Bildern) und ein Chat-Fenster für die Unterhaltung. Die KI-Antwort wird hier live im Verlauf angezeigt, während sie generiert wird. Die Web-UI ist im lokalen Netzwerk zugänglich und ermöglicht ein komfortables Chat-Erlebnis über HTTP.

Optional kann ein **Ask-All/Broadcast-Modus** aktiviert werden (`ui.experimental.broadcast_mode: true`). Dann lässt sich eine Frage parallel an alle Personas richten – im Terminal über die Ask-All-Option im Startmenü, in der Web-UI über die Ask-All-Kachel mit Ergebnis-Tabelle für alle Antworten.

Zusätzlich kann `ui.type` auch auf `null` gesetzt werden, um ausschließlich die API zu betreiben; die Web-UI unterstützt außerdem einen optionalen Gradio-Share-Link mit Zugangsdaten aus `ui.web.share_auth`.

## One-Shot API

Parallel zur UI kann das System auch über eine REST-API angesprochen werden (z. B. für Integrationen oder Tests). Ein FastAPI-Server stellt einen **`/ask`-Endpoint** bereit, über den per HTTP-POST einzelne Fragen gestellt werden können. Die Anfrage nimmt ein JSON entgegen (mit Feldern für die **Frage** und die gewünschte **Persona**) und liefert die KI-Antwort als JSON-Antwort zurück. Zusätzlich existiert ein einfacher **`/health`-Endpoint** für Health-Checks. Diese API ermöglicht es, die KI-Funktionalität in externe Anwendungen einzubinden oder automatisiert zu nutzen.

## Wikipedia-Integration

Um fundierte Antworten zu ermöglichen, kann das System bei Wissensfragen automatisch **Wikipedia-Wissen einbinden** (optional konfigurierbar). Dabei kommen folgende Mechanismen zum Einsatz:

- **Automatischer Wissensabruf:** Aus der Nutzerfrage wird mittels spaCy-NLP das relevanteste Schlagwort extrahiert. Anschließend sucht ein interner Wiki-Proxy nach einem passenden Wikipedia-Artikel – je nach Einstellung entweder **offline** über eine lokale Kiwix-Datenbank oder **online** über die Wikipedia-API. Bei Offline-Modus kann der Kiwix-Server automatisch gestartet werden, sofern konfiguriert.  
- **Kontext-Erweiterung:** Findet der Wiki-Proxy einen Artikel, wird ein Ausschnitt (Snippet) daraus entnommen. Dieser Ausschnitt wird als zusätzliche *System*-Nachricht in den Chat-Kontext eingefügt, bevor die KI antwortet. Die KI erhält so geprüfte Fakten als Kontext und kann präzisere Antworten geben. In der Terminal-UI wird außerdem ein Hinweis-Icon (🕵️) angezeigt, wenn ein Wikipedia-Snippet benutzt wurde. Bleibt die Suche ohne Treffer, wird dies durch eine kurze Hinweisnachricht vermerkt.
- **Mehrere Treffer nutzbar:** Erkennt der Keyword-Finder mehrere relevante Entitäten, können mehrere Snippets in den Prompt aufgenommen werden. Die Obergrenze steuert `wiki.max_wiki_snippets` (Standard: 2), sodass der Kontext gezielt erweitert werden kann, ohne zu überladen.

## Logging und Tests

Stabile Nutzung wird durch umfangreiches Logging und automatische Tests unterstützt:

- **Chat-Logging:** Jede Unterhaltung wird in einer JSON-Datei (im Ordner `logs/`) mitprotokolliert. Darin werden Zeitstempel, verwendetes Modell, Persona sowie alle Nutzer- und KI-Nachrichten festgehalten. Zusätzlich schreibt die Anwendung fortlaufend ein System-Logfile (mit Präfix `yulyen_ai_...`), das interne Abläufe und Debug-Informationen (Info/Fehler) enthält.  
- **Wiki-Proxy Logging:** Der Wikipedia-Proxy-Dienst führt eigene Logdateien über die Artikelanfragen und Ergebnisse. Dadurch lassen sich Wiki-Zugriffe und etwaige Fehler nachvollziehen, getrennt vom Haupt-Chat-Log.  
- **Automatisierte Tests:** Eine Sammlung von Pytest-Tests (`tests/` Verzeichnis) prüft zentrale Funktionen des Systems. Beispielsweise wird getestet, ob die Personas korrekt initialisiert werden, ob der Sicherheits-Filter greift und ob wiederholbare Antworten (z. B. gleiche Witze von Doris) konsistent bleiben. Diese Tests helfen, Regressionen zu vermeiden und die Zuverlässigkeit der KI-Orchestrierung sicherzustellen.

## Sicherheitsmechanismen

Das Projekt verfügt über einen einfachen integrierten **Security-Guard** (`BasicGuard`), der Eingaben und Ausgaben auf problematische Inhalte prüft:

- **Prompt Injection Schutz:** Benutzer-Eingaben werden auf Muster überprüft, die auf Versuch einer *Prompt Injection* hindeuten (z. B. Anweisungen, vorherige Regeln zu ignorieren). Wird ein solcher Versuch erkannt, unterbricht der Guard den normalen Ablauf – anstelle einer KI-Antwort erhält der Nutzer einen Hinweis, dass die Anfrage abgelehnt wurde. Die potenziell schädliche Eingabe wird nicht an das Sprachmodell weitergeleitet.  
- **PII-Filterung:** Der Guard erkennt in generierten KI-Antworten persönliche Daten (*Personally Identifiable Information*, z. B. E-Mail-Adressen, Telefonnummern) und ersetzt diese vorsorglich durch eine Standardwarnung. So wird verhindert, dass private oder sensible Informationen ungefiltert im Chat erscheinen.  
- **Output-Blockliste:** Bestimmte vertrauliche Schlüssel oder Tokens (z. B. API-Schlüssel im Format `sk-...`) werden ebenfalls erkannt. Sollte die KI derartige Sequenzen produzieren, wird die Ausgabe vollständig blockiert, um ein Leaken von Geheimnissen zu vermeiden. Im Ergebnis sieht der Nutzer dann lediglich eine allgemeine Warnung statt des gefährlichen Inhalts.

Diese Prüfungen greifen bereits während des Streamings: Tokens werden laufend kontrolliert, bei Bedarf maskiert und bei blockierten Sequenzen sofort durch eine Sicherheitswarnung ersetzt.

## Erweiterbarkeit und Experimente

Die Architektur von *Yul Yen’s AI Orchestra* ist darauf ausgelegt, zukünftige Erweiterungen und Verbesserungen zu ermöglichen:

- **Modulare Architektur:** Das System kapselt den LLM-Zugriff hinter klar definierten Schnittstellen. Beispielsweise ist die Anbindung an das Sprachmodell über die abstrakte Klasse `LLMCore` gelöst. Dies erlaubt es, das Backend einfach auszutauschen (z. B. ein anderer Modellserver statt Ollama, oder Verwendung des Dummy-LLM für Tests), ohne den Rest der Anwendung anzupassen. Auch neue Personas lassen sich durch Ergänzung der Konfiguration leicht hinzufügen.  
- **LoRA-Finetuning (PoC):** Erste Experimente zur Modellverfeinerung existieren als Proof-of-Concept, werden jedoch aus Platzgründen nicht im Standard-Repository mitgeliefert. Intern zeigt ein kleines **LoRA-Finetuning**-Beispiel (basierend auf [PEFT/QLoRA](https://github.com/huggingface/peft)), wie ein kompakter Adapter für die Persona Doris mit ca. 200 Frage-Antwort-Paaren trainiert wurde. Die zugehörigen Trainingsskripte und Testläufe dienen ausschließlich Demonstrationszwecken und sind nicht in den Hauptbetrieb integriert. Interessierte können sich bei den Maintainer:innen melden, um Details oder Zugang zu den Materialien zu erhalten.
- **Zukünftige Features:** Das Projekt hat bereits eine Roadmap für weitere Ideen. Geplant sind u. a. die Integration von Werkzeugen (*Tool Use* wie Websuche oder Rechner), Sprach-Ein-/Ausgabe (Speech-to-Text, Text-to-Speech) sowie ein verbesserter Umgang mit langen Chats durch *Retrieval-Augmented Generation* (z. B. automatisches Zusammenfassen alter Chat-Teile durch einen virtuellen Assistenten namens "Karl"). Die aktuelle Codebasis bildet eine einfache, erweiterbare Grundlage, auf der solche Features in Zukunft aufsetzen können.

siehe auch: [backlog.md](../../backlog.md)
