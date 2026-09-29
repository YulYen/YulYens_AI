# Funktionen: Modi, RSS, Ask-All-Fazit, Mail, API

Die Feature-Modi im Detail, die RSS-Entscheidungen (#73), das Ask-All-Fazit (#27), der E-Mail-Adapter (#14), Sprachstrategie und die API samt OpenAI-Kompatibilität (#37).

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Feature-Modi

| Modus | Beschreibung |
|---|---|
| **Chat** | Einzelne Persona, Streaming |
| **AI-Dialog** | Zwei Personas konversieren automatisch (Stop: Antwort enthält `endegelaende` oder endet auf `_ende_`) |
| **Broadcast/Ask-All** | Eine Frage an alle Personas; Antworten live tokenweise gestreamt als Markdown-Sektion pro Persona. WebUI streamt **parallel** (`iter_broadcast_events_parallel`: Worker-Thread + Queue pro Persona; Fallback `ui.experimental.broadcast_parallel: false`), Terminal sequenziell (`iter_broadcast_events`). Echter Speedup braucht `OLLAMA_NUM_PARALLEL` ≥ Persona-Zahl, sonst serialisiert Ollama. **Ein Token-Event trägt nur sein Token** (#64d) — der kumulative Text wurde pro Token neu gebaut und ins Event gelegt, also quadratisch in der Antwortlänge; wer den laufenden Text braucht, sammelt in einer Liste und fügt beim Anzeigen zusammen (so macht es die WebUI, ein paar Mal pro Sekunde statt einmal pro Token). Ein Häkchen unter dem Eingabefeld hängt ein **Fazit 🎭** an die Runde (#27, Default aus, kostet einen vollen Modelllauf) |
| **RSS als Quelle (#73)** | Nachrichten verhalten sich wie das Wiki: eine Quelle, die sich meldet, wenn die Frage danach ist (`rss/trigger.py`), statt eines Knopfes, der alles abkippt. Geholt wird **im Hintergrund** (`RssCache`, Start + alle `rss.refresh_minutes`) — ein Turn nimmt, was da ist, notfalls nichts. Alle Meldungen zusammen als **eine** System-Nachricht, je Meldung `max_chars_per_item` und ein Datum. Der Knopf „Briefing 📰" bzw. `/briefing` nutzt denselben Cache und ist über `rss.show_button` abschaltbar, ohne die Quelle abzuschalten |
| **Quellen (#32)** | Zugeklapptes Accordion „Quellen 📚" unter dem Chat. Zeigt pro injiziertem Wikipedia-Snippet den Titel als Link auf kiwix-serve, die Herkunft und **den Snippet-Text selbst** samt Zeichenzahl (`1200 von 9800 Zeichen injiziert (gekürzt)` bzw. `51 Zeichen (vollständig)`). `wiki.snippet_limit` kürzt — erst die Anzeige macht sichtbar, was das Modell nie gesehen hat. Datenquelle ist `WikiSnippet` aus `wiki/lookup.py`; die Originallänge liefert der Proxy als `full_length` mit. Ask-All hat ein eigenes Accordion innerhalb seiner Gruppe (#32a), im Terminal zeigt `/quellen` denselben Inhalt ungekürzt. Meta-Zeile geteilt über `format_snippet_meta` |
| **Statuszeile (#36)** | Unter dem Chat: `Kontext █░░░ 424 / 8.192 Token (5 %) · 24,0 Tok/s · erster Token nach 1,9 s`. Füllstand aus `approx_token_count` + `num_ctx`, Tempo aus `StreamStats` (der Provider legt sie nach jedem Stream auf sich selbst ab). Ab `context_utils.threshold` (75 %) fett — ab da greift die Kompression. Wert nur im Schluss-Yield, sonst `gr.update()` |
| **Feedback (#40)** | 👍/👎 an jeder Bot-Bubble, append-only nach `data/feedback_votes.jsonl` (neben der Ablage, auf die es zeigt — `logs/` darf jederzeit geleert werden, gesammelte Bewertungen sind nicht reproduzierbar; eine alte Datei zieht beim ersten Zugriff automatisch um). **Eine Bot-Bubble ist nicht automatisch eine Modellantwort:** Wiki-Hinweise, die Meldung über verworfene Quellen, Briefing-Hinweise und die Kontext-Kompressionswarnung stehen in derselben Spalte und tragen ebenfalls einen Daumen. Erkannt wird das daran, dass Beiwerk **nie in der LLM-History** landet — wer eine neue Hinweis-Bubble einführt, bekommt den Schutz dadurch geschenkt, solange er sie nicht ins Kontextfenster gibt. Ein Vote, der sich nicht gegen die History prüfen lässt, wird verworfen: für einen Trainingsdaten-Kanal (#7) ist eine verlorene Bewertung billiger als eine erfundene. **Jede Zeile trägt seit #65 `conversation_id` + `message_index`** — ohne die ist ein Vote ein loses Textpaar, mit ihnen ein Join auf die Ablage (Persona, Modell, Zeitraum, Gesprächsverlauf davor). Der Index zählt **Positionen unter den Antwort-Bubbles**, nicht Texte: Hinweis-Bubbles stehen in der Anzeige zwischen den Antworten und in der Ablage nicht, und zweimal „Ja." im selben Gespräch ist keine Seltenheit. Den Wortlaut liefert die Ablage, nicht die Anzeige — gegen sie wird später gejoint. Ohne Anmeldung gibt es keine Ablage (#72); dann bleibt `conversation_id` leer und der Vote wird trotzdem geschrieben |
| **Verlauf (#25)** | Karte „Verlauf öffnen 🗂" listet die Gespräche des angemeldeten Nutzers aus dem Store (#54). Auswahl per `gr.Dropdown` (kein `gr.Dataframe`, siehe Stolperfalle unten), Vorschau als Markdown, dazu Öffnen (fortsetzbar — dieselbe Gesprächs-ID), Markdown-Export und Löschen. Länge über `storage.history_limit` (Default 50, neueste zuerst). Ein Suchfeld darüber schränkt die Liste auf Fundstellen ein (#49, FTS5) — dieselbe Form, damit Vorschau, Öffnen, Export und Löschen unverändert daran hängen. Gespräche von Gast-Personas bleiben lesbar, aber nicht fortsetzbar — erkannt an ihrem eigenen `app` (`web-guest`) **und** am exakten Personennamen, sonst öffnete ein Gast namens „Leah" das Gespräch still als die echte LEAH. Die Regel steht in `ui/continuation.py` und gilt für **alle drei** Wege in ein gespeichertes Gespräch: Verlauf, JSON-Upload und der Ladepfad im Terminal. Jeder Handler prüft zusätzlich den Eigentümer (`user_state`) |
| **Gast-Persona (#28)** | Karte „Gast anlegen 🎭" → Formular (Name, System-Prompt, Temperatur). Lebt **nur in der Sitzung**: kein YAML, kein Reload. Läuft über `AppFactory.get_streamer_for_guest`, das sich mit dem Persona-Pfad einen `_build_streamer` teilt — Guard, Wiki, Statuszeile, Quellen und Gesprächs-Ablage kommen dadurch gratis mit. Persistenz nach `ensembles/custom/` wäre V2 |
| **Stop / Nochmal (#35)** | Während eines Streams ersetzt „Stop ⏹" den Senden-Button; der Kill-Switch `SessionContext.stream_stop` beendet den Generator geordnet und **behält die Teilantwort** (Suffix `web_stream_stopped_suffix`). Gilt für Einzelchat, Briefing und Self-Talk — dort erst zwischen den Turns, weil `run_turn()` die Antwort in einem Zug holt. „Nochmal 🔄" verwirft die letzte Antwort in Anzeige und LLM-Verlauf und streamt denselben Kontext erneut (Varianz allein aus der Persona-Temperatur); Wiki-/Briefing-Hints bleiben stehen |

### RSS: vier Entscheidungen, die man leicht umdreht (#73)

1. **Der Guard filtert *pro Meldung*, bevor zusammengefügt wird.** Seit alles in
   *einer* System-Nachricht landet, wäre die umgekehrte Reihenfolge eine stille
   Abschwächung: eine schräge Schlagzeile risse entweder den ganzen Block mit
   oder rutschte in ihm durch. Derselbe Fehler wie damals bei
   `WikiLookup.snippets()`, nur andersherum.
2. **`items_for` holt nie selbst.** Ein Lazy-Load lässt genau die Frage zahlen,
   die nach Ablauf der Frist zuerst kommt — zwei Feeds à 13 s Timeout im
   Request-Pfad, die Lektion aus #51. Der Hintergrund-Thread startet in
   `launch.py`, nicht in der Factory: `--doctor` und die Tests bauen die
   Factory auch und dürfen nie ins Netz.
3. **Nur Plural löst aus.** „Nachrichten" sind Nachrichten, „eine Nachricht" ist
   eine Nachricht an den Chef; „Schlagzeilen" will Schlagzeilen, „eine
   Schlagzeile" ist eine Wortbedeutungsfrage. Diese eine Regel ersetzt eine
   ganze Klasse von Sonderfällen gegen Definitionsfragen. Einzelne Zeitwörter
   („heute", „aktuell", „neu") lösen **nichts** aus — sie stehen in jedem
   zweiten Satz.
4. **Ein Personenbezug schlägt alles.** „Was gibt's Neues **bei dir**?" ist
   Small Talk; der Fehlalarm wäre teuer, weil die Persona anfinge, Schlagzeilen
   aufzusagen.

Gemessen wie beim Guard (#62): die naive Wortliste traf **9 von 12** harmlosen
Sätzen, die Fassung im Repo **0** — bei unveränderter Trefferzahl. Wer eine
Regel ergänzt, legt in `tests/test_rss_trigger.py` den Satz daneben, den sie
nicht treffen darf.

**Die Feed-Namen sind Auslöser und kommen aus der Config** (`rss/trigger.py`,
`feed_aliases`): „Was sagt die Tagesschau?" zieht nur diese Quelle. Wer einen
Feed ergänzt, bekommt seinen Auslöser geschenkt — keine zweite Wortliste.

### Das Ask-All-Fazit: opt-in, und ausdrücklich kein Kontext-Kanal (#27)

`core/ask_all_moderator.py` hängt an eine fertige Ask-All-Runde einen weiteren
Modelllauf, der die vier Antworten zusammenfasst und die stärkste benennt.
Vier Entscheidungen, die man beim Anfassen leicht umdreht:

1. **Das Häkchen ist die Entscheidung — es gibt keinen Config-Schalter
   daneben.** Ein Fazit kostet einen *vollen* zusätzlichen Lauf; das ist nichts,
   was man einmal einstellt und dann vergisst, sondern etwas, das man pro Frage
   will oder nicht. Ein zweiter Schalter in `config.yaml` könnte das Häkchen nur
   verbergen und wäre damit eine Einstellung, die eine Einstellung versteckt.
   Im Terminal ist es dieselbe Entscheidung als eine Rückfrage vor der Runde —
   *vor* ihr, weil danach vier Antworten auf dem Schirm stehen und eine
   Rückfrage dort untergeht.
2. **Kein dritter Kontext-Kanal (#75), und das ist kein Schlupfloch.** Die
   Regel aus #75 gilt für abgerufenen **Fremdtext**. Die vier Antworten sind
   die eigene Modellausgabe desselben Turns und auf dem Weg nach draußen
   bereits durch `_StreamModerator` gelaufen — PII maskiert, Blocklist
   angewandt. Sie durch `inject_context` zu schicken prüfte die Maskierung,
   nicht das Modell; genau das Argument, mit dem `respond_one_shot` keine
   zweite `check_output` fährt. Das Vorbild steht daneben: Karl
   (`context_summarizer`) gibt den Gesprächsverlauf ebenso direkt in einen
   Prompt. Wer hier einmal Fremdtext hineingibt, der *nicht* durch unseren
   Stream kam, dreht diese Begründung um und braucht dann den Kanal.
3. **Genau eine `user`-Nachricht.** `stream()` prüft die *letzte*
   user-Nachricht — zwei daraus zu machen führte die Antworten still am
   Eingangs-Guard vorbei. Der bekannte Preis: vier zusammengefügte Antworten
   können eine Guard-Brücke über eine Zeilengrenze schlagen (dieselbe Klasse
   wie `test_the_guard_bridges_can_span_a_line_break`), dann fällt das Fazit
   mit einer sichtbaren Absage aus. Sichtbar und behebbar ist der bessere
   Tausch als eine Ausnahme, die als einzige Stelle im Projekt ungeprüft in
   ein Modell geht.
4. **Gekürzt wird vor dem Prompt, mit Marker.** Das Budget je Antwort kommt
   aus dem `num_ctx` des Ensembles (halbes Fenster, geteilt durch die Zahl der
   Antworten), nicht aus einer runden Zahl — vier ausführliche Personas
   sprengen sonst genau dann, wenn es interessant wird. Der Marker
   („[…gekürzt]") ist nicht Kosmetik: ohne ihn liest der Moderator einen mitten
   im Satz endenden Absatz als vollständige Antwort und zieht daraus Schlüsse.

**Aufgezeichnet wird nichts** — der Moderator-Streamer bekommt nie eine
Gesprächs-ID. Das ist dieselbe Entscheidung wie bei Ask-All selbst (siehe
„Ablage der Gespräche" in [ablage-und-anmeldung.md](ablage-und-anmeldung.md)): ein Fazit über vier Fäden passt in ein Datenmodell
„eine Persona, ein Faden" noch weniger als die vier Fäden selbst.

**Von der ruhigsten Persona kommen die Sampling-Optionen, nicht die Stimme.**
Moderiert wird mit einem eigenen, neutralen Systemprompt
(`ask_all_moderator_system` in den Locales): Zusammenfassen und Bewerten ist
eine *Aufgabe*, keine Rolle. Eine der vier Personas moderieren zu lassen wäre
naheliegend gewesen — das Projekt hat schließlich eine Besetzung — und kostet
an zwei Stellen, die man erst beim Lesen ihres Prompts sieht:

* **Sie müsste die stärkste Antwort küren, und eine davon ist ihre eigene.**
  Der Prompt sagt „Du bist PETER", der Stoff trägt eine Sektion `### PETER`.
* **PETERs Prompt enthält bereits eine Rangfolge**, nämlich die
  Zuständigkeitsliste des Ensembles („für Wärme und Empathie an LEAH, für
  verspielte Katzenenergie an POPCORN, für trockenen Sarkasmus an DORIS").
  Das ist eine Bewertung *vor* der Runde, unabhängig davon, was diesmal
  tatsächlich dastand. Dazu käme über `_system_prompt_with_date` der
  Zeitstempel- und Guardrail-Block, der fürs Beantworten von Nutzerfragen
  geschrieben ist — und die Zeile „vermeide Meta-Erklärungen über dein
  Vorgehen", während Moderieren genau das ist.

Übernommen wird deshalb nur `llm_options` der Persona mit der niedrigsten
Temperatur — und davon nur, was in `INHERITED_OPTIONS` steht: die Persona leiht
ihr **Sampling**, nicht die *Form* der Antwort. `format`, `stop`, `num_predict`,
`system` und `template` bleiben draußen, weil ein fremdes Ensemble sie sonst
still gegen den Moderator drehen könnte (JSON statt Fazit, nach zwanzig Tokens
abgeschnitten, eigener Systemprompt) — und an einem Fazit sieht niemand, wie es
hätte aussehen sollen. In `classic` ändert der Filter nichts: dort stehen nur
`temperature`, `repeat_penalty` und `num_ctx`, bei den letzten beiden für alle
vier gleich. Es läuft also weiter auf „Ensemble-Optionen plus niedrigste
Temperatur" hinaus, und genau das ist gewollt: sachlich statt kreativ. Abgeleitet statt
verdrahtet, damit es auch für ein fremdes Ensemble stimmt; die Regel liegt in
`config.personas.quietest_persona_name`, weil die Stoppuhr (#42) dieselbe Wahl
aus einem anderen Grund trifft und zwei Fassungen derselben Regel
auseinanderlaufen.

**Der Preis steht auf der anderen Seite und ist bekannt:** das Fazit ist eine
fünfte Stimme ohne Gesicht in einer Oberfläche, in der jede andere Stimme ein
Porträt hat. Wer das ändern will, macht den Moderator zu einer **eigenen**
Persona im Ensemble-YAML — mit Namen und Prompt, die ein fremdes Ensemble
überschreiben kann, aber nicht auf der Startseite — und nicht zu einer der
vier, die gerade bewertet werden.

### E-Mail-Adapter: die Reihenfolge ist die Regel (#14)

Der Adapter (`email_adapter/service.py`, opt-in) ist der einzige Kanal, über den
**Fremde** die Instanz erreichen — und der einzige, der unter der Domain des
Betreibers nach außen sendet. Vier Regeln, die man beim nächsten Umbau leicht
umdreht und die dann teuer sind:

1. **Geantwortet wird an `From`, nie an `Reply-To`.** Über `Reply-To` ließ sich
   die Instanz dazu bringen, an einen *Dritten* zu schreiben — mit gültigem
   SPF/DKIM der eigenen Domain und dem Text des Absenders im Zitat. Dieselbe
   Zeile speist die Schleifenerkennung; mit `Reply-To` war auch die umgehbar.
2. **Erst markieren, dann senden.** Andersherum kostet ein fehlgeschlagenes
   Markieren nicht *eine* Antwort, sondern *jede*: die Mail bleibt UNSEEN und
   wird bei jedem Poll neu beantwortet (gemessen: 4 Zyklen, 4 identische
   Antworten, `run_once()` meldete jedes Mal 0). `_mark_processed` fällt
   deshalb auf `\Seen` zurück, wenn das Verschieben scheitert.
3. **Ohne `allowed_senders` startet der Adapter nicht.** Fail-closed wie bei
   fehlenden Zugangsdaten: der Dienst kostet LLM-Läufe und verschickt Mail.
4. **Gekürzt wird einmal beim Lesen** (`max_body_chars`), nicht an jeder
   Verwendungsstelle — Prompt und Antwortzitat erben es dadurch.

Nicht behoben und deshalb ticketiert (#14a): der IMAP-Ordnertrenner wird
geraten statt per `LIST` erfragt. Regel 2 nimmt dem Fehler die Katastrophe.

## Sprachstrategie

- Projekt-Sprache in `config.yaml`: `language: "de"` (Standard)
- Locale-Dateien: `locales/de.yaml`, `locales/en.yaml`
- Persona-Prompts lokalisiert in `ensembles/classic/locales/{de,en}/personas.yaml`
- UI-Texte via `Config.t()` formatiert

## Wichtige API-Endpunkte

```
POST http://127.0.0.1:8013/ask
  Body: { "question": "Hallo", "persona": "LEAH" }
  → { "answer": "..." }

GET  http://127.0.0.1:8013/health    # Liveness (Prozess antwortet) — ohne Schlüssel
GET  http://127.0.0.1:8013/healthz   # Readiness (Ollama/Modell/spaCy/Kiwix/VRAM, 503 bei kritischem Fehler)

# OpenAI-kompatibel (#37) — "model" ist der Persona-Name
GET  http://127.0.0.1:8013/v1/models
POST http://127.0.0.1:8013/v1/chat/completions
  Body: { "model": "DORIS", "messages": [...], "stream": true|false }
```

### OpenAI-Kompatibilität: worauf zu achten ist
- **`model` = Persona**, nicht LLM. `/v1/models` listet Personas; das echte Modell
  bleibt Serversache (`core.model_name`).
- **`api.openai_compatible.api_key` gilt für *alle* Endpunkte, auch für `/ask`** —
  der Name sagt nur, wo die Option steht. Vorher hing `require_access` allein am
  `/v1`-Router, während `/ask` auf demselben Port dieselbe Fähigkeit ohne
  Schlüssel und ohne Rate-Limit anbot. Die Regel liegt in `check_api_access`,
  die Fehler*form* bleibt pro Router verschieden (`/v1`: OpenAI, `/ask`:
  FastAPI). Ein neuer Endpunkt, der ein LLM anspricht, gehört dort mit dran.
- **Fehler-Bodies müssen `{"error": {...}}` auf oberster Ebene haben.** FastAPIs
  `HTTPException(detail=…)` erzeugt `{"detail": {"error": …}}` — eine Ebene zu tief,
  das offizielle openai-SDK findet die Felder dann nicht. Deshalb eigene
  `OpenAIError` + Exception-Handler (`api/openai_compat.py`), und
  `RequestValidationError` wird unter `/v1` auf 400 + OpenAI-Form gemappt (`/ask`
  behält FastAPIs Standardform).
- **`temperature`/`top_p`/`max_tokens` werden angenommen und ignoriert** — Sampling
  gehört zur Persona, sonst kann jeder Aufrufer den Charakter plattmachen.
- **Client-History wird durchgereicht**, Karl/Heuristik greifen hier nicht
  (OpenAI-Semantik: der Client besitzt sein Kontextfenster).
- Verifikation gegen das echte SDK: `pip install openai`, dann `base_url` auf
  `http://127.0.0.1:8013/v1` zeigen. Bewusst **keine** Dependency im Projekt.

Dieselben Deep-Checks gibt es auch ohne laufenden Server: `python src/launch.py --doctor`.
