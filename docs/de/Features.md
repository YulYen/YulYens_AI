# Funktionalitäten

## Mehrere KI-Personas

Das System umfasst vier unterschiedliche KI-Personas mit eigenen Charakteren. Alle Personas nutzen das gleiche zugrundeliegende Sprachmodell, unterscheiden sich jedoch durch spezielle System-Prompts, die ihren Sprachstil und Ton festlegen:

- **Leah** – empathisch und freundlich
- **Doris** – sarkastisch und schlagfertig humorvoll
- **Peter** – faktenorientiert, analytisch und sachlich
- **Popcorn** – verspielt und kindgerecht (Katzen-Persona)

Die Auswahl der Persona erfolgt entweder beim Start (Terminal-UI) oder über die Weboberfläche. Jede Persona reagiert im entsprechenden Stil auf Nutzeranfragen.

Diese vier gehören zum Ensemble `classic` — der Standardbesetzung. Welche Personas antworten, hängt am gewählten Ensemble (siehe nächster Abschnitt).

## Persona-Ensembles

Ein Ensemble bündelt Personas mit ihren System-Prompts, LLM-Optionen (Temperatur, `repeat_penalty`, `num_ctx`) und Avataren. Welches beim Start geladen wird, bestimmt `--ensemble` / `-e`. Zwei Ensembles liegen im Repo:

- **`classic`** — LEAH, DORIS, PETER, POPCORN (Standard, `python src/launch.py -e classic`)
- **`examples/spaceship_crew`** — die Crew des Raumschiffs *Aurora-One*: CAPTAIN_SELINA (besonnene Kommandantin), ZETA_FLUX (sarkastische Chefingenieurin), ELIAS_MOREL (poetischer Navigator) und LYRA_VEX (außerirdische Diplomatin). Start: `python src/launch.py -e examples/spaceship_crew`

![Spaceship-Crew: Persona-Auswahl mit der Crew der Aurora-One](../screenshot_spaceship_crew.png)

Welche Ensembles verfügbar sind, listet `python src/launch.py --list-ensembles` — mit Personas, vorhandenen Sprachen und dem Namen, den `-e` erwartet. Der Ensemble-Name ist ein Pfad unterhalb von `ensembles/` und wird immer mit Schrägstrich geschrieben. Eigene Ensembles brauchen keinen Code, nur YAML und Bilder: siehe [Eigenes Ensemble hinzufügen](Ensemble_hinzufuegen.md).

## Benutzeroberflächen (UI)

Zwei verschiedene Benutzeroberflächen stehen zur Verfügung, auswählbar über die Konfiguration (`ui.type`):

- **Terminal-UI** – Konsolenbasierte Chat-Anwendung mit farbig hervorgehobenen Rollen (Nutzer/KI). Bei Start wird die gewünschte Persona per Menü ausgewählt. Nutzereingaben werden direkt in der Konsole eingegeben, und die KI-Antwort erscheint tokenweise gestreamt. Es gibt einfache Befehle wie `exit` zum Beenden und `clear` für einen neuen Chatverlauf.
- **Web-UI** – Webbasierte Oberfläche (Gradio), die im Browser verfügbar ist. Sie bietet eine grafische Persona-Auswahl (mit Avatar-Bildern) und ein Chat-Fenster für die Unterhaltung. Die KI-Antwort wird hier live im Verlauf angezeigt, während sie generiert wird. Die Web-UI ist im lokalen Netzwerk zugänglich und ermöglicht ein komfortables Chat-Erlebnis über HTTP.

Optional kann ein **Ask-All/Broadcast-Modus** aktiviert werden (`ui.experimental.broadcast_mode: true`). Dann lässt sich eine Frage an alle Personas richten – im Terminal über die Ask-All-Option im Startmenü, in der Web-UI über die Ask-All-Kachel. Die Personas antworten nacheinander; in der Web-UI erscheinen die Antworten **live tokenweise gestreamt** als Markdown-Abschnitt pro Persona:

![Ask-All: Alle vier Personas beantworten dieselbe Frage](../screenshot_ask_all.png)

Zusätzlich kann `ui.type` auch auf `null` gesetzt werden, um ausschließlich die API zu betreiben; die Web-UI unterstützt außerdem einen optionalen Gradio-Share-Link mit Zugangsdaten aus `ui.web.share_auth`.

### Stream-Steuerung: Stop und Nochmal

Während eine Antwort generiert wird, tritt in der Web-UI ein **„Stop ⏹"**-Button an
die Stelle des Senden-Buttons. Ein Klick beendet die Generierung sofort und **behält
die bereits geschriebene Teilantwort** im Verlauf, gekennzeichnet mit
`…[abgebrochen]` — meist bricht man ja gerade ab, weil der Anfang schon zeigt,
wohin es geht. Der Stop wirkt im Einzelchat und beim Briefing tokengenau; im
AI-Dialog greift er zwischen zwei Sprecherwechseln, weil dort jede Antwort in
einem Zug geholt wird.

**„Nochmal 🔄"** verwirft die letzte Antwort und lässt dieselbe Frage neu
beantworten. Der Kontext bleibt unverändert — die Abwechslung kommt allein aus der
Temperatur der Persona, POPCORN (0.8) variiert also deutlich stärker als PETER
(0.1). Wiki- und Briefing-Hinweise über der Antwort bleiben stehen.

## AI-Dialog (Self-Talk)

Das Projekt unterstützt einen **AI-Dialog-Modus**, in dem zwei Personas automatisiert miteinander sprechen, um eine vorgegebene Aufgabe zu lösen:

- **Terminal-UI:** Über das Startmenü kann „Self Talk“ gewählt werden. Danach werden Persona A, Persona B und ein Start-Prompt abgefragt.
- **Web-UI:** Eine eigene Self-Talk-Kachel startet denselben Ablauf direkt im Browser.
- **Ablauf:** Beide Personas antworten abwechselnd; die jeweils erzeugte Antwort wird als nächste Eingabe für die andere Persona verwendet.
- **Automatisches Ende:** Der Dialog endet, sobald eine Persona das definierte End-Token (`_endegelaende_`) ausgibt.

Damit eignet sich der Modus z. B. für Brainstorming zwischen zwei Charakteren oder das Durchspielen mehrerer Sichtweisen auf dieselbe Fragestellung.

## Text-to-Speech (TTS)

Für die Terminal-Interaktion ist eine integrierte **Text-to-Speech-Ausgabe mit Piper** verfügbar:

- Aktivierung über `tts.enabled: true`.
- Automatische WAV-Erzeugung pro Antwort über `tts.features.terminal_auto_create_wav: true`.
- Sprachmodelle werden über `tts.voices` in der `config.yaml` konfiguriert (Default je Sprache plus optionale persona-spezifische Stimmen).
- **Plattformen:** Die automatische WAV-Erzeugung und -Wiedergabe in der Terminal-UI läuft auf allen drei Plattformen. Windows nutzt `winsound` aus der Standardbibliothek, Linux und macOS greifen auf die üblichen Kommandozeilen-Player zurück (`paplay`, `aplay` oder `ffplay` unter Linux, `afplay` unter macOS) — ohne zusätzliche Abhängigkeit. Findet sich kein Player, wird die Wiedergabe still übersprungen und die WAV-Datei liegt trotzdem in `out/`.

So kann die KI-Antwort nicht nur gelesen, sondern unmittelbar auch als Audio ausgegeben werden.

## One-Shot API

Parallel zur UI kann das System auch über eine REST-API angesprochen werden (z. B. für Integrationen oder Tests). Ein FastAPI-Server stellt einen **`/ask`-Endpoint** bereit, über den per HTTP-POST einzelne Fragen gestellt werden können. Die Anfrage nimmt ein JSON entgegen (mit Feldern für die **Frage** und die gewünschte **Persona**) und liefert die KI-Antwort als JSON-Antwort zurück. Für das Monitoring existieren zwei Endpunkte: **`/health`** als schneller Liveness-Check und **`/healthz`** als Deep-Check, der Ollama-Erreichbarkeit, gepulltes Modell, spaCy, Kiwix und VRAM prüft (HTTP 503 bei kritischem Ausfall). Dieselben Prüfungen laufen auch per CLI über `python src/launch.py --doctor` als farbiger Preflight-Report. Diese API ermöglicht es, die KI-Funktionalität in externe Anwendungen einzubinden oder automatisiert zu nutzen.

## OpenAI-kompatible API

Zusätzlich sprechen die Personas das **OpenAI-Protokoll**. Damit lässt sich jeder
Client benutzen, der mit OpenAI reden kann — Open WebUI, Handy-Apps,
Editor-Plugins — nur eben mit LEAH, DORIS, PETER und POPCORN statt mit einem
Cloud-Modell. Anders als rohes Ollama läuft dabei alles durch Guard,
Wiki-Injektion und Gesprächslog, weil derselbe Streamer arbeitet wie in der UI.

Der Trick ist die Zuordnung: **`model` ist der Persona-Name.** `/v1/models`
listet daher die Personas und nicht die LLMs — welches Modell darunter läuft,
bleibt Serversache (`core.model_name`).

```bash
# Verfügbare Personas
curl http://127.0.0.1:8013/v1/models

# Frage an DORIS
curl http://127.0.0.1:8013/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "DORIS", "messages": [{"role": "user", "content": "Was ist Kaffee?"}]}'
```

Mit dem offiziellen Python-SDK:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8013/v1", api_key="dein-key")
stream = client.chat.completions.create(
    model="POPCORN",                      # Persona statt Modell
    messages=[{"role": "user", "content": "Erklär mir Rekursion"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

Einstellungen unter `api.openai_compatible`:

| Schlüssel | Bedeutung |
|---|---|
| `enabled` | Endpunkte an/aus. Aus = HTTP 404, als gäbe es sie nicht |
| `api_key` | Optionaler Bearer-Key. Leer = offen. Besser als `env:YULYEN_API_KEY` setzen als im Klartext |
| `rate_limit_per_minute` | Anfragen pro Client und Minute, `0` schaltet das Limit ab |

Zu wissen:

- **Streaming** läuft als Server-Sent Events wie beim Original, inklusive
  abschließendem `data: [DONE]`.
- **`temperature`, `top_p`, `max_tokens`** werden angenommen und **ignoriert**.
  Die Sampling-Werte gehören zur Persona (`personas_base.yaml`) — würde man sie
  überschreiben lassen, könnte jeder Aufrufer POPCORNs Verspieltheit oder PETERs
  Präzision plattmachen. Clients, die diese Felder immer mitsenden, funktionieren
  trotzdem.
- **Die Gesprächshistorie kommt vom Client**, so wie es das OpenAI-Protokoll
  vorsieht. Karl und die heuristische Kürzung greifen hier bewusst nicht: wer die
  Historie schickt, verwaltet auch das Kontextfenster. Eine zu lange Historie
  läuft also ins `num_ctx`-Limit — genau wie bei OpenAI selbst.
- **Solange `api.host` auf `127.0.0.1` steht**, ist der Server nur lokal
  erreichbar. Erst wenn er im LAN hängt, wird der `api_key` wirklich wichtig.

## E-Mail-Adapter für Personas

Optional kann ein schlanker **E-Mail-Adapter** aktiviert werden (`email_adapter.enabled: true`). Er ruft regelmäßig neue Nachrichten aus einem konfigurierten IMAP-Postfach ab, ordnet Empfängeradressen über `email_adapter.address_persona_map` einer Persona zu und beantwortet die Anfrage mit derselben One-Shot-Logik, die auch die HTTP-API nutzt. Die Antwort wird per SMTP an den ursprünglichen Absender zurückgesendet.

Das MVP verarbeitet einfache Text-E-Mails; HTML wird pragmatisch zu Text reduziert, Attachments werden ignoriert. Um Mail-Loops und doppelte Antworten zu vermeiden, ignoriert der Adapter eigene System-/Persona-Adressen und verschiebt erfolgreich bearbeitete oder bewusst ignorierte Nachrichten standardmäßig in den konfigurierten `processed_mailbox`-Ordner. Zugangsdaten gehören nicht in den Code: In `config.yaml` sind Platzhalter wie `env:YULYEN_MAIL_IMAP_PASSWORD` vorgesehen, die zur Laufzeit aus Umgebungsvariablen gelesen werden.

## Gespräche wiederfinden

Gespräche liegen in einer lokalen SQLite-Datei (`storage.path`, standardmäßig `data/conversations.sqlite3`) — nicht in Logdateien. Über die Karte „Verlauf öffnen 🗂" lassen sie sich auflisten, ansehen, **fortsetzen**, als Markdown exportieren und löschen. Angezeigt werden nur die eigenen Gespräche; wer als `local` arbeitet, sieht die des lokalen Nutzers.

Fortsetzen heißt wirklich fortsetzen: die Antwort landet im selben Gesprächseintrag, es entsteht kein zweiter. Gespräche einer Gast-Persona bleiben lesbar, lassen sich aber nicht fortsetzen — deren System-Prompt lebte nur in der damaligen Sitzung.

Der frühere JSONL-Mitschnitt in `logs/` ist weiterhin verfügbar, aber als reines Debug-Werkzeug und standardmäßig aus (`logging.conversation_jsonl`).

## Anmeldung (optional)

Standardmäßig verlangt die Web-UI **keine Anmeldung** — für den Einzelplatz am eigenen Rechner wäre sie nur Aufwand. Über `ui.web.auth.provider` lässt sie sich einschalten:

- `disabled` (Standard): kein Login, jedes Gespräch wird dem Nutzer `local` zugeordnet.
- `local`: Benutzername und Passwort aus `ui.web.auth.users`. Passwörter gehören nicht im Klartext in die Config, sondern als `env:NAME`.
- `header`: die Identität kommt von einem vorgeschalteten Reverse-Proxy (oauth2-proxy, Authelia, …). Das ist der Weg, um später einen echten Anmeldedienst wie Keycloak davorzusetzen — Gradio selbst kann kein OpenID Connect.

Der Nutzername landet in jeder Zeile des Gesprächslogs und in jeder 👍/👎-Bewertung. Die Anmeldung gilt unabhängig davon, ob ein öffentlicher Share-Link aktiv ist.

> **Wichtig:** Die Anmeldung überträgt Passwörter über HTTP im Klartext. Ohne TLS trennt sie Nutzer voneinander, schützt aber nicht gegen jemanden, der den Netzwerkverkehr mitliest. Der `header`-Modus vertraut dem Header bedingungslos und gehört deshalb ausschließlich hinter einen Proxy, der ihn von außen entfernt.

## Gast-Persona

Über die Karte „Gast anlegen 🎭" lässt sich eine eigene Persona aus Name, System-Prompt und Temperatur zusammenstellen — ohne YAML und ohne Neustart. Sie lebt nur in der laufenden Sitzung und ist nach einem Neustart wieder weg; alles andere (Wikipedia-Kontext, Sicherheitsfilter, Gesprächslog, Statuszeile) funktioniert dabei genau wie bei den mitgelieferten Personas.

## Bedienkomfort in der Web-UI

- **Heller und dunkler Modus:** Oben rechts schalten zwei Links zwischen den Themes (`?__theme=dark` bzw. `?__theme=light`). Gradio liest die Einstellung beim Laden, der Wechsel bedeutet also einen kurzen Reload.
- **Antwort kopieren:** Jede Nachricht im Chat hat ein Kopier-Symbol.
- **Statuszeile:** Unter dem Chat steht nach jeder Antwort, wie voll das Kontextfenster ist (`Kontext █░░░ 424 / 8.192 Token (5 %)`) und wie schnell das Modell war (`24,0 Tok/s · erster Token nach 1,9 s`). Ab 75 % Füllstand wird die Zeile hervorgehoben — genau dort beginnt die Anwendung, den Gesprächsverlauf zu kürzen.

## Wikipedia-Integration

Um fundierte Antworten zu ermöglichen, kann das System bei Wissensfragen automatisch **Wikipedia-Wissen einbinden** (optional konfigurierbar). Dabei kommen folgende Mechanismen zum Einsatz:

- **Automatischer Wissensabruf:** Aus der Nutzerfrage wird mittels spaCy-NLP das relevanteste Schlagwort extrahiert. Anschließend sucht ein interner Wiki-Proxy nach einem passenden Wikipedia-Artikel – je nach Einstellung entweder **offline** über eine lokale Kiwix-Datenbank oder **online** über die Wikipedia-API. Bei Offline-Modus kann der Kiwix-Server automatisch gestartet werden, sofern konfiguriert.
- **Kontext-Erweiterung:** Findet der Wiki-Proxy einen Artikel, wird ein Ausschnitt (Snippet) daraus entnommen. Dieser Ausschnitt wird als zusätzliche *System*-Nachricht in den Chat-Kontext eingefügt, bevor die KI antwortet. Die KI erhält so geprüfte Fakten als Kontext und kann präzisere Antworten geben. In der Terminal-UI wird außerdem ein Hinweis-Icon (🕵️) angezeigt, wenn ein Wikipedia-Snippet benutzt wurde. Bleibt die Suche ohne Treffer, wird dies durch eine kurze Hinweisnachricht vermerkt.
- **Quellen einsehbar (Web-UI):** Unter dem Chat sitzt ein zugeklapptes Accordion „Quellen 📚". Aufgeklappt zeigt es pro Snippet den Artikeltitel als klickbaren Link (offline auf den lokalen kiwix-serve), die Herkunft — und vor allem **den Ausschnitt im Wortlaut, so wie er in den Prompt gegangen ist**, samt Zeichenzahl. Weil `wiki.snippet_limit` lange Artikel kürzt (Standard 1200 Zeichen), steht dort z. B. „1200 von 9800 Zeichen injiziert (gekürzt)" — daran ist erkennbar, wie viel des Artikels die KI gar nicht gesehen hat. Passte alles hinein, heißt es „vollständig". Ohne Wiki-Treffer bleibt das Accordion unsichtbar. In der Ask-All-Ansicht gibt es dasselbe Accordion unter den Antworten, im Terminal zeigt das Kommando `/quellen` denselben Inhalt.
- **Mehrere Treffer nutzbar:** Erkennt der Keyword-Finder mehrere relevante Entitäten, können mehrere Snippets in den Prompt aufgenommen werden. Die Obergrenze steuert `wiki.max_wiki_snippets` (Standard: 2), sodass der Kontext gezielt erweitert werden kann, ohne zu überladen.

## Logging und Tests

Stabile Nutzung wird durch umfangreiches Logging und automatische Tests unterstützt:

- **Chat-Logging:** Jede Unterhaltung wird in einer JSON-Datei (im Ordner `logs/`) mitprotokolliert. Darin werden Zeitstempel, verwendetes Modell, Persona sowie alle Nutzer- und KI-Nachrichten festgehalten. Zusätzlich schreibt die Anwendung fortlaufend ein System-Logfile (mit Präfix `yulyen_ai_...`), das interne Abläufe und Debug-Informationen (Info/Fehler) enthält.
- **Wiki-Proxy Logging:** Der Wikipedia-Proxy-Dienst führt eigene Logdateien über die Artikelanfragen und Ergebnisse. Dadurch lassen sich Wiki-Zugriffe und etwaige Fehler nachvollziehen, getrennt vom Haupt-Chat-Log.
- **Antwort-Feedback (👍/👎):** In der Web-UI lässt sich jede Antwort bewerten. Jeder Klick schreibt eine Zeile nach `logs/feedback_votes.jsonl` — mit Zeitstempel, Persona, Modell, Frage, Antwort und Bewertung. Die Datei wächst nur an (eine Umbewertung ergänzt eine Zeile, statt die alte zu ersetzen), sodass sich der Verlauf auswerten lässt. Gedacht als Datenbasis für Qualitätsvergleiche und späteres Finetuning.
- **Automatisierte Tests:** Eine Sammlung von Pytest-Tests (`tests/` Verzeichnis) prüft zentrale Funktionen des Systems. Beispielsweise wird getestet, ob die Personas korrekt initialisiert werden, ob der Sicherheits-Filter greift und ob wiederholbare Antworten (z. B. gleiche Witze von Doris) konsistent bleiben. Diese Tests helfen, Regressionen zu vermeiden und die Zuverlässigkeit der KI-Orchestrierung sicherzustellen.

## Sicherheitsmechanismen

Das Projekt verfügt über einen einfachen integrierten **Security-Guard** (`BasicGuard`), der Eingaben und Ausgaben auf problematische Inhalte prüft:

- **Prompt Injection Schutz:** Benutzer-Eingaben werden auf Muster überprüft, die auf Versuch einer *Prompt Injection* hindeuten (z. B. Anweisungen, vorherige Regeln zu ignorieren). Wird ein solcher Versuch erkannt, unterbricht der Guard den normalen Ablauf – anstelle einer KI-Antwort erhält der Nutzer einen Hinweis, dass die Anfrage abgelehnt wurde. Die potenziell schädliche Eingabe wird nicht an das Sprachmodell weitergeleitet.
- **PII-Filterung:** Der Guard erkennt in generierten KI-Antworten persönliche Daten (*Personally Identifiable Information*, z. B. E-Mail-Adressen, Telefonnummern) und ersetzt diese vorsorglich durch eine Standardwarnung. So wird verhindert, dass private oder sensible Informationen ungefiltert im Chat erscheinen.
- **Output-Blockliste:** Bestimmte vertrauliche Schlüssel oder Tokens (z. B. API-Schlüssel im Format `sk-...`) werden ebenfalls erkannt. Sollte die KI derartige Sequenzen produzieren, wird die Ausgabe vollständig blockiert, um ein Leaken von Geheimnissen zu vermeiden. Im Ergebnis sieht der Nutzer dann lediglich eine allgemeine Warnung statt des gefährlichen Inhalts.
- **Wrongdoing-Guardrail (Gewalt/Waffen):** Anfragen nach Gewalt- oder Waffenanleitungen werden bereits vor dem LLM-Aufruf deterministisch erkannt und abgelehnt. Jede Eingabe wird für sich geprüft, sodass ein Treffer nur diese eine Anfrage blockt und harmlose Folgefragen wieder normal durchgehen. Optional lässt sich per `security.wrongdoing_lock_turns` (Standard: `0` = aus) ein kurzer **Session-Lock** aktivieren: Nach einem Treffer werden die nächsten *N* Eingaben unabhängig vom Inhalt blockiert — das fängt Umgehungsversuche ohne Triggerwort ab („ist doch nur für einen Roman…"). Steuerbar über `security.wrongdoing_protection` (Standard: aktiv).

Diese Prüfungen greifen bereits während des Streamings: Tokens werden laufend kontrolliert, bei Bedarf maskiert und bei blockierten Sequenzen sofort durch eine Sicherheitswarnung ersetzt.

## Erweiterbarkeit und Experimente

Die Architektur von *Yul Yen’s AI Orchestra* ist darauf ausgelegt, zukünftige Erweiterungen und Verbesserungen zu ermöglichen:

- **Modulare Architektur:** Das System kapselt den LLM-Zugriff hinter klar definierten Schnittstellen. Beispielsweise ist die Anbindung an das Sprachmodell über die abstrakte Klasse `LLMCore` gelöst. Dies erlaubt es, das Backend einfach auszutauschen (z. B. ein anderer Modellserver statt Ollama, oder Verwendung des Dummy-LLM für Tests), ohne den Rest der Anwendung anzupassen. Auch neue Personas lassen sich durch Ergänzung der Konfiguration leicht hinzufügen.
- **LoRA-Finetuning (PoC):** Erste Experimente zur Modellverfeinerung existieren als Proof-of-Concept, werden jedoch aus Platzgründen nicht im Standard-Repository mitgeliefert. Intern zeigt ein kleines **LoRA-Finetuning**-Beispiel (basierend auf [PEFT/QLoRA](https://github.com/huggingface/peft)), wie ein kompakter Adapter für die Persona Doris mit ca. 200 Frage-Antwort-Paaren trainiert wurde. Die zugehörigen Trainingsskripte und Testläufe dienen ausschließlich Demonstrationszwecken und sind nicht in den Hauptbetrieb integriert. Interessierte können sich bei den Maintainer:innen melden, um Details oder Zugang zu den Materialien zu erhalten.
- **Kontext-Kompression („Karl“):** Bei langen Unterhaltungen wird die Chat-History automatisch komprimiert, bevor das Kontextfenster überläuft. Standard ist eine schnelle Heuristik (alte Nachrichten kürzen, System-Prompt und jüngste Nachrichten behalten); optional fasst der LLM-basierte Summarizer „Karl“ ältere Chat-Teile zusammen (`context_management.strategy: "karl"`, mit automatischem Fallback auf die Heuristik).
- **Drei-Zeitstempel-Transparenz:** Der System-Prompt trennt drei leicht verwechselbare Zeitangaben sauber: das aktuelle Systemdatum, den Trainings-Cutoff des Modells (`core.knowledge_cutoffs`) und den Datenstand des Wikipedia-Archivs. So behaupten die Personas nicht versehentlich, „aktuelles“ Wissen zu haben.
- **Zukünftige Features:** Das Projekt hat eine priorisierte Roadmap (siehe [backlog.md](../../backlog.md)). Geplant sind u. a. die Integration von Werkzeugen (*Tool Use* wie Websuche oder Rechner), Spracheingabe (STT) und schnellere First-Token-Zeiten. Die aktuelle Codebasis bildet eine einfache, erweiterbare Grundlage, auf der solche Features aufsetzen können.

siehe auch: [backlog.md](../../backlog.md)
