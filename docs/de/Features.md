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
- **Web-UI** – Webbasierte Oberfläche (Gradio), die im Browser verfügbar ist. Sie bietet eine grafische Persona-Auswahl (mit Avatar-Bildern) und ein Chat-Fenster für die Unterhaltung. Die KI-Antwort wird hier live im Verlauf angezeigt, während sie generiert wird. Standardmäßig horcht sie nur auf `127.0.0.1`, ist also nur vom eigenen Rechner aus erreichbar; für den Zugriff aus dem Netz muss `ui.web.host` bewusst umgestellt werden (und dann bitte mit Anmeldung, siehe unten).

Optional kann ein **Ask-All/Broadcast-Modus** aktiviert werden (`ui.experimental.broadcast_mode: true`). Dann lässt sich eine Frage an alle Personas richten – im Terminal über die Ask-All-Option im Startmenü, in der Web-UI über die Ask-All-Kachel. Im Terminal antworten die Personas nacheinander; in der Web-UI laufen sie **parallel** und erscheinen **live tokenweise gestreamt** als Markdown-Abschnitt pro Persona. Ein echter Zeitgewinn setzt allerdings voraus, dass Ollama parallel bedient (`OLLAMA_NUM_PARALLEL` ≥ Zahl der Personas) — sonst reiht es die Anfragen doch wieder auf. Zurückschalten lässt sich das mit `ui.experimental.broadcast_parallel: false`:

![Ask-All: Alle vier Personas beantworten dieselbe Frage](../screenshot_ask_all.png)

Zusätzlich kann `ui.type` auch auf `null` gesetzt werden, um ausschließlich die API zu betreiben; die Web-UI unterstützt außerdem einen optionalen Gradio-Share-Link (`ui.web.share: true`). Die Zugangsdaten dafür kommen aus dem Abschnitt `ui.web.auth` — der gilt **unabhängig davon, ob ein Share-Link aktiv ist** (siehe „Anmeldung"). Das frühere `ui.web.share_auth` ist veraltet und wirkt nur noch als Fallback, wenn kein `auth`-Abschnitt vorhanden ist.

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
- **Automatisches Ende:** Der Dialog endet, sobald eine Persona das definierte End-Token (`_endegelaende_`) ausgibt. Aus Nachsicht gegenüber kleinen Modellen zählt außerdem eine Antwort, die auf `_ende_` endet.

Damit eignet sich der Modus z. B. für Brainstorming zwischen zwei Charakteren oder das Durchspielen mehrerer Sichtweisen auf dieselbe Fragestellung.

## Text-to-Speech (TTS)

Eine integrierte **Text-to-Speech-Ausgabe mit Piper** steht in beiden Oberflächen zur Verfügung:

- Aktivierung über `tts.enabled: true`.
- **Terminal:** automatische WAV-Erzeugung pro Antwort über `tts.features.terminal_auto_create_wav: true`, inklusive Wiedergabe.
- **Web-UI:** der Knopf „Vorlesen 🔊" im Persona-Chat spielt die letzte Antwort mit der Stimme der Persona **im Browser** ab, nicht über einen System-Player. Er erscheint nur, wenn `pip install piper-tts` erfolgt ist und Stimmen im `voices/`-Ordner liegen; abschalten über `tts.features.web_read_aloud: false`.
- Sprachmodelle werden über `tts.voices` in der `config.yaml` konfiguriert (Default je Sprache plus optionale persona-spezifische Stimmen).
- **Plattformen:** Die automatische WAV-Erzeugung und -Wiedergabe in der Terminal-UI läuft auf allen drei Plattformen. Windows nutzt `winsound` aus der Standardbibliothek, Linux und macOS greifen auf die üblichen Kommandozeilen-Player zurück (`paplay`, `aplay` oder `ffplay` unter Linux, `afplay` unter macOS) — ohne zusätzliche Abhängigkeit. Findet sich kein Player, wird die Wiedergabe still übersprungen und die WAV-Datei liegt trotzdem in `out/`.

So kann die KI-Antwort nicht nur gelesen, sondern unmittelbar auch als Audio ausgegeben werden.

## Spracheingabe (STT)

Umgekehrt lässt sich in der Web-UI auch **sprechen** statt tippen: Mit `stt.enabled: true` und einem installierten `faster-whisper` (`pip install faster-whisper`) erscheint ein Mikrofon neben dem Eingabefeld. Aufnehmen → stoppen → das Transkript wird an das Eingabefeld angehängt und lässt sich vor dem Absenden noch bearbeiten — die Erkennung ersetzt das Senden also nicht, sie füllt nur das Feld. Die erste Aufnahme lädt das Whisper-Modell (einmalig, inklusive Download) und dauert deshalb spürbar länger als die folgenden. Größe und Sprache stehen unter `stt.model` und `stt.language`; Details in [src/stt/ReadMe.md](../../src/stt/ReadMe.md).

## One-Shot API

Parallel zur UI kann das System auch über eine REST-API angesprochen werden (z. B. für Integrationen oder Tests). Ein FastAPI-Server stellt einen **`/ask`-Endpoint** bereit, über den per HTTP-POST einzelne Fragen gestellt werden können. Die Anfrage nimmt ein JSON entgegen (mit Feldern für die **Frage** und die gewünschte **Persona**) und liefert die KI-Antwort als JSON-Antwort zurück. Für das Monitoring existieren zwei Endpunkte: **`/health`** als schneller Liveness-Check und **`/healthz`** als Deep-Check, der Ollama-Erreichbarkeit, gepulltes Modell, spaCy, Kiwix und VRAM prüft (HTTP 503 bei kritischem Ausfall). Dieselben Prüfungen laufen auch per CLI über `python src/launch.py --doctor` als farbiger Preflight-Report. Diese API ermöglicht es, die KI-Funktionalität in externe Anwendungen einzubinden oder automatisiert zu nutzen.

## OpenAI-kompatible API

Zusätzlich sprechen die Personas das **OpenAI-Protokoll**. Damit lässt sich jeder
Client benutzen, der mit OpenAI reden kann — Open WebUI, Handy-Apps,
Editor-Plugins — nur eben mit LEAH, DORIS, PETER und POPCORN statt mit einem
Cloud-Modell. Anders als rohes Ollama läuft dabei alles durch Guard,
Wiki-Injektion und Gesprächs-Ablage, weil derselbe Streamer arbeitet wie in der UI.

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

Das MVP verarbeitet einfache Text-E-Mails; HTML wird pragmatisch zu Text reduziert, Attachments werden ignoriert. **Antworten gehen an die `From`-Adresse** — ein `Reply-To` wird bewusst ignoriert, sonst könnte ein fremder Absender die Instanz dazu bringen, an Dritte zu schreiben. **Antworten bekommt nur, wer auf `email_adapter.allowed_senders` steht** (volle Adressen oder ganze Domains wie `@meine-domain.de`); die Liste ist Pflicht, sobald der Adapter eingeschaltet ist, und ohne sie startet er nicht. Automatische Mails (Abwesenheitsassistenten, Newsletter, Listen) werden erkannt und nicht beantwortet, und die eigenen Antworten sind als solche markiert (RFC 3834) — sonst schaukeln sich zwei Automaten gegenseitig hoch. Der übernommene Mailtext ist auf `max_body_chars` begrenzt. Um Mail-Loops und doppelte Antworten zu vermeiden, ignoriert der Adapter eigene System-/Persona-Adressen und verschiebt bearbeitete Nachrichten in den konfigurierten `processed_mailbox`-Ordner — **markiert wird vor dem Senden**, damit eine Mail nicht bei jedem Durchlauf erneut beantwortet wird, falls das Verschieben scheitert. Zugangsdaten gehören nicht in den Code: In `config.yaml` sind Platzhalter wie `env:YULYEN_MAIL_IMAP_PASSWORD` vorgesehen, die zur Laufzeit aus Umgebungsvariablen gelesen werden.

## Gespräche wiederfinden

Gespräche liegen in einer lokalen SQLite-Datei (`storage.path`, standardmäßig `data/conversations.sqlite3`) — nicht in Logdateien. Über die Karte „Verlauf öffnen 🗂" lassen sie sich auflisten, ansehen, **fortsetzen**, als Markdown exportieren und löschen. Angezeigt werden nur die eigenen Gespräche, geprüft wird der Eigentümer serverseitig.

**In der Web-UI setzt das eine Anmeldung voraus.** Ohne sie sind alle Besucher derselbe Nutzer `local` — der „eigene" Verlauf wäre dann der Verlauf aller, fortsetzbar und löschbar von jedem, der die Seite erreicht. Deshalb zeichnet die Web-UI ohne Anmeldung **gar nichts** auf und blendet die Verlauf-Karte aus; der Start sagt beide Auswege dazu. Wer den gemeinsamen Topf am Einzelplatz ausdrücklich will, setzt `storage.shared_without_login: true` und bekommt dafür eine laute Warnung beim Start. Terminal und API sind davon nicht betroffen — dort gibt es keine Anmeldung, die fehlen könnte.

Fortsetzen heißt wirklich fortsetzen: die Antwort landet im selben Gesprächseintrag, es entsteht kein zweiter. Gespräche einer Gast-Persona bleiben lesbar, lassen sich aber nicht fortsetzen — deren System-Prompt lebte nur in der damaligen Sitzung.

**Nicht im Verlauf stehen Ask-All und der AI-Dialog** — und das ist Absicht, kein Fehler. „Frage an alle" sind vier parallele Antworten auf *eine* Frage und passen nicht in die Form „ein Gespräch mit einer Persona"; der AI-Dialog erzeugt ein Artefakt, zu dem der Nutzer nur den Startprompt beigesteuert hat. Wer beides behalten will, nimmt den Datei-Export.

Der Austausch per Datei (JSON herunterladen/hochladen im WebUI, `/save` und „Gespräch laden" im Terminal) bleibt daneben bestehen — er ist für Backups und den Wechsel zwischen Rechnern gedacht. Wer ihn nicht braucht, schaltet ihn mit `storage.file_exchange: false` ab; der Markdown-Export im Verlauf bleibt davon unberührt.

Der frühere JSONL-Mitschnitt in `logs/` ist weiterhin verfügbar, aber als reines Debug-Werkzeug und standardmäßig aus (`logging.conversation_jsonl`).

## Anmeldung (optional)

Standardmäßig verlangt die Web-UI **keine Anmeldung** — für den Einzelplatz am eigenen Rechner wäre sie nur Aufwand. Über `ui.web.auth.provider` lässt sie sich einschalten:

- `disabled` (Standard): kein Login, alle Besucher sind derselbe Nutzer `local` — und genau deshalb zeichnet die Web-UI in dieser Einstellung keine Gespräche auf (siehe „Gespräche wiederfinden").
- `local`: Benutzername und Passwort aus `ui.web.auth.users`. Passwörter gehören nicht im Klartext in die Config, sondern als `env:NAME`.
- `header`: die Identität kommt von einem vorgeschalteten Reverse-Proxy (oauth2-proxy, Authelia, …). Das ist der Weg, um später einen echten Anmeldedienst wie Keycloak davorzusetzen — Gradio selbst kann kein OpenID Connect.

Der Nutzername wird zu jedem Gespräch in der Ablage vermerkt und steht in jeder 👍/👎-Bewertung. Die Anmeldung gilt unabhängig davon, ob ein öffentlicher Share-Link aktiv ist.

> **Wichtig:** Die Anmeldung überträgt Passwörter über HTTP im Klartext. Ohne TLS trennt sie Nutzer voneinander, schützt aber nicht gegen jemanden, der den Netzwerkverkehr mitliest. Der `header`-Modus vertraut dem Header bedingungslos und gehört deshalb ausschließlich hinter einen Proxy, der ihn von außen entfernt.

## Gast-Persona

Über die Karte „Gast anlegen 🎭" lässt sich eine eigene Persona aus Name, System-Prompt und Temperatur zusammenstellen — ohne YAML und ohne Neustart. Sie lebt nur in der laufenden Sitzung und ist nach einem Neustart wieder weg; alles andere (Wikipedia-Kontext, Sicherheitsfilter, Gesprächs-Ablage, Statuszeile) funktioniert dabei genau wie bei den mitgelieferten Personas.

## Bedienkomfort in der Web-UI

- **Heller und dunkler Modus:** Oben rechts steht ein Knopf, der immer den *anderen* Modus anbietet („🌙 Dunkel" im hellen Modus, „☀️ Hell" im dunklen). Der Wechsel geschieht im Browser: kein Neuladen, und das laufende Gespräch, die gewählte Persona und getippter, noch nicht abgeschickter Text bleiben stehen. Die Wahl wird im Browser gespeichert und gilt auch beim nächsten Besuch.
- **Startseite auf einen Blick:** Die vier Persona-Karten tragen ihre Porträts, die Funktionskarten („AI Dialog", „Gast-Persona", „Verlauf", „Frage an alle") ein schlichtes Icon. Wer wen anspricht und was nur eine Funktion ist, ist damit ohne Lesen unterscheidbar.
- **Antwort kopieren:** Jede Nachricht im Chat hat ein Kopier-Symbol.
- **Statuszeile:** Unter dem Chat steht nach jeder Antwort, wie voll das Kontextfenster ist (`Kontext █░░░ 424 / 8.192 Token (5 %)`) und wie schnell das Modell war (`24,0 Tok/s · erster Token nach 1,9 s`). Ab 75 % Füllstand wird die Zeile hervorgehoben — genau dort beginnt die Anwendung, den Gesprächsverlauf zu kürzen.

## Nachrichten als Quelle (RSS)

Mit `rss.enabled: true` verhalten sich Nachrichten wie die Offline-Wikipedia: als **Quelle, die sich meldet, wenn die Frage danach ist** — nicht als Knopf, der alles abkippt.

Die konfigurierten Feeds werden **im Hintergrund** geholt (beim Start und dann alle `rss.refresh_minutes`), die neuesten Meldungen liegen im Speicher. Fragt jemand „Was gibt's Neues?", „Gibt es aktuelle Nachrichten?" oder nennt eine Quelle beim Namen („Was sagt die Tagesschau?"), legt die Persona die passenden Meldungen von selbst als Kontext dazu — mit Datum je Meldung und dem Stand des Zwischenspeichers, damit aus einer Meldung von vorgestern kein „heute" wird.

Zwei Eigenschaften, die im Alltag zählen:

- **Ein Chat wartet nie auf das Netz.** Was noch nicht geholt ist, fehlt eben; die Antwort kommt trotzdem. Ein Feed, der gerade nicht erreichbar ist, wirft die zuletzt geholten Meldungen nicht weg.
- **Small Talk löst nichts aus.** „Was gibt's Neues bei dir?" ist eine Frage an die Persona, keine Bitte um Schlagzeilen — die Unterscheidung ist an alltäglichen Sätzen gemessen und nicht geraten.

Der Button „Briefing 📰" (bzw. `/briefing` im Terminal) gibt es weiterhin; er benutzt denselben Zwischenspeicher und lässt sich über `rss.show_button: false` ausblenden, ohne die Quelle abzuschalten. Alles zusammen abschalten: `rss.enabled: false` — dann geht die Anwendung für Nachrichten nie ins Netz.

## Wikipedia-Integration

Um fundierte Antworten zu ermöglichen, kann das System bei Wissensfragen automatisch **Wikipedia-Wissen einbinden** (optional konfigurierbar). Dabei kommen folgende Mechanismen zum Einsatz:

- **Automatischer Wissensabruf:** Aus der Nutzerfrage wird mittels spaCy-NLP das relevanteste Schlagwort extrahiert. Anschließend sucht ein interner Wiki-Proxy nach einem passenden Wikipedia-Artikel – je nach Einstellung entweder **offline** über eine lokale Kiwix-Datenbank oder **online** über die Wikipedia-API. Bei Offline-Modus kann der Kiwix-Server automatisch gestartet werden, sofern konfiguriert.
- **Kontext-Erweiterung:** Findet der Wiki-Proxy einen Artikel, wird ein Ausschnitt (Snippet) daraus entnommen. Dieser Ausschnitt wird als zusätzliche, deutlich als Fremdtext markierte *user*-Nachricht in den Chat-Kontext eingefügt (`[FREMDTEXT ANFANG] … [FREMDTEXT ENDE]`), bevor die KI antwortet — bewusst nicht als *system*-Nachricht, denn ein heruntergeladener Artikel ist Material, über das geredet wird, und keine Anweisung. Vorher durchläuft er den Sicherheits-Guard, der Anweisungsversuche im Artikeltext verwirft. Die KI erhält so geprüfte Fakten als Kontext und kann präzisere Antworten geben. Der Ausschnitt gehört zum Prompt, nicht zum Gespräch: in Ablage, Verlauf und Export taucht er nicht auf. In der Terminal-UI wird außerdem ein Hinweis-Icon (🕵️) angezeigt, wenn ein Wikipedia-Snippet benutzt wurde. Bleibt die Suche ohne Treffer, wird dies durch eine kurze Hinweisnachricht vermerkt.
- **Quellen einsehbar (Web-UI):** Unter dem Chat sitzt ein zugeklapptes Accordion „Quellen 📚". Aufgeklappt zeigt es pro Snippet den Artikeltitel als klickbaren Link (offline auf den lokalen kiwix-serve), die Herkunft — und vor allem **den Ausschnitt im Wortlaut, so wie er in den Prompt gegangen ist**, samt Zeichenzahl. Weil `wiki.snippet_limit` lange Artikel kürzt (Standard 1200 Zeichen), steht dort z. B. „1200 von 9800 Zeichen injiziert (gekürzt)" — daran ist erkennbar, wie viel des Artikels die KI gar nicht gesehen hat. Passte alles hinein, heißt es „vollständig". Ohne Wiki-Treffer bleibt das Accordion unsichtbar. In der Ask-All-Ansicht gibt es dasselbe Accordion unter den Antworten, im Terminal zeigt das Kommando `/quellen` denselben Inhalt.
- **Mehrere Treffer nutzbar:** Erkennt der Keyword-Finder mehrere relevante Entitäten, können mehrere Snippets in den Prompt aufgenommen werden. Die Obergrenze steuert `wiki.max_wiki_snippets` (Standard: 2), sodass der Kontext gezielt erweitert werden kann, ohne zu überladen.

## Logging und Tests

Stabile Nutzung wird durch umfangreiches Logging und automatische Tests unterstützt:

- **Gespräche vs. Logs:** Die Gespräche selbst liegen **nicht** in `logs/`, sondern in der SQLite-Ablage (siehe „Gespräche wiederfinden"). In `logs/` steht Betriebs-Diagnostik: ein fortlaufendes System-Logfile (Präfix `yulyen_ai_...`) mit internen Abläufen und Debug-Informationen. Der rohe JSONL-Mitschnitt der einzelnen Generierungs*versuche* (Zeitstempel, Modell, Persona, Nachrichten) lässt sich mit `logging.conversation_jsonl: true` dazuschalten — er ist ein Debug-Werkzeug und standardmäßig aus.
- **Wiki-Proxy Logging:** Der Wikipedia-Proxy-Dienst führt eigene Logdateien über die Artikelanfragen und Ergebnisse. Dadurch lassen sich Wiki-Zugriffe und etwaige Fehler nachvollziehen, getrennt vom Haupt-Chat-Log.
- **Antwort-Feedback (👍/👎):** In der Web-UI lässt sich jede Antwort bewerten. Jeder Klick schreibt eine Zeile nach `logs/feedback_votes.jsonl` — mit Zeitstempel, Persona, Modell, Frage, Antwort, Bewertung und einem Verweis auf das gespeicherte Gespräch. Die Datei wächst nur an (eine Umbewertung ergänzt eine Zeile, statt die alte zu ersetzen), sodass sich der Verlauf auswerten lässt. Gedacht als Datenbasis für Qualitätsvergleiche und späteres Finetuning.
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
- **Eval-Suite:** Ob eine Änderung das Modell wirklich besser gemacht hat, beantwortet ein eigener Korpus aus goldenen Fragen pro Persona und Guard-Angriffen — als YAML, damit neue Fälle keinen Testcode brauchen (`python scripts/run_evals.py -e classic`, Details in [evals/ReadMe.md](../../evals/ReadMe.md)). Der Guard-Teil läuft ohne Modell in der normalen Testsuite mit.
- **Zukünftige Features:** Das Projekt hat eine priorisierte Roadmap (siehe [backlog.md](../../backlog.md)). Geplant sind u. a. die Integration von Werkzeugen (*Tool Use* wie Websuche oder Rechner), ein Langzeit-Gedächtnis über die Gesprächs-Ablage und Volltextsuche im Verlauf. Die aktuelle Codebasis bildet eine einfache, erweiterbare Grundlage, auf der solche Features aufsetzen können.

siehe auch: [backlog.md](../../backlog.md)
