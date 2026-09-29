# WebUI und Gradio-Stolperfallen

Modulschnitt (#56), Sitzungszustand im `gr.State`, und die Gradio-Fallen: Dataframe, `messages`-Format, `js=`, Button-Updates, Links, `cancels`, Kill-Switch.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

### Ein Modul bekommt eine Regel, nicht hundert Zeilen (#56)

`web_ui.py` ist von 2440 auf 1438 Zeilen geschrumpft — die Zahl ist aber nicht
das Kriterium, und wer sie zum Kriterium macht, baut den Schaden ein, den #56
vermeiden wollte. **Gemessen** vor dem zweiten Durchgang: die sauberen Nähte
waren die *kleinen* Blöcke (Gast: 69 Zeilen, 2 WebUI-Felder), die Masse lag in
den Blöcken mit der stärksten Kopplung (Navigation: 264 Zeilen, **11** Felder).
Ein mechanischer „fünf Controller"-Schnitt hätte fünf Module mit sechs bis elf
Konstruktor-Argumenten ergeben, die weiter ins WebUI zurückrufen: mehr Dateien,
dieselbe Kopplung, plus eine Indirektion.

Der Test ist deshalb: **besitzt das Modul eine Regel?** `feedback.py` besitzt
„ein nicht deutbarer Vote-Index wird verworfen, nicht geraten". `history_access.py`
besitzt „jeder Zugriff trägt `user`". `webui_chat.py` besitzt den
Stream-Lebenszyklus (Button-Updates im selben Yield, genau ein
`record_conversation`, Kill-Switch über Identität). `webui_features.py` besitzt
„welche Funktion ist verfügbar — und warum nicht". Gast, Self-Talk und die
Ask-All-Handler besitzen keine und bleiben deshalb, wo sie sind; sie zu
verschieben wäre Kosmetik, die sich als Fortschritt ausgibt.

Zwei Dinge, die beim Schneiden wehtaten:

1. **Keine delegierenden Wrapper.** Der bequeme Weg ist, `WebUI.respond_streaming`
   als Einzeiler stehenzulassen, der auf `self.chat` zeigt — dann müssen die
   Aufrufer nicht angefasst werden. Zwei Namen für eine Sache laufen aber
   auseinander, genau wie `KNOWN_TOP_LEVEL_KEYS` neben den pydantic-Modellen
   (#66). Die Aufrufer zeigen direkt auf `ui.chat.…`.
2. **Ein weitergereichter Wert ist nicht mehr nachträglich zu drehen.** `_t` war
   ein Feld am WebUI; ein Test tauschte es *nach* dem Bauen aus, und das ging
   gut, solange alle Leser dasselbe Feld lasen. Sobald es an den Controller
   weitergegeben wird, liest der still den alten Wert. Aufgefallen an einem
   Test, hätte aber genauso eine Config-Option treffen können. **Was
   weitergereicht wird, kommt beim Bauen herein** — bei Tests also über die
   Config, wie im Betrieb auch.

Und der Grund, warum der Browser-Rauchtest existiert: er hat in dieser Runde
den einen echten Fund gemacht. In-process waren 1154 Tests grün, während der
Patch-Zielpfad `ui.web_ui.module_available` ins Leere zeigte.

### Sitzungszustand gehört in den `gr.State`, nicht ans WebUI-Objekt
Die `WebUI` ist ein **Singleton der AppFactory** und bedient alle Browser
gleichzeitig. Persona, Streamer, die beiden Kill-Switches und der
Self-Talk-Runner hingen anfangs am Objekt — zwei parallele Sitzungen teilten sie
sich also. Belegt im Browser: A wählt LEAH, B danach DORIS, A fragt → die
Nachricht landet in **DORIS'** Gespräch, LEAHs bleibt leer.

Sie liegen deshalb in `SessionContext` (`ui/session.py`) und reisen als
`gr.State` durch die Handler — als **erster** Parameter, passend zur
`inputs=`-Reihenfolge. Gradio legt pro Browser-Sitzung eine eigene Kopie des
Default-Werts an (`SessionState.__getitem__` in `gradio/state_holder.py` macht
einmalig ein `deepcopy` und merkt sie sich), deshalb genügt es, das Objekt
durchzureichen und **in-place** zu ändern; als Output zurück muss es nicht.
Konsequenzen fürs Weiterbauen:

- **Neuer sitzungsabhängiger Zustand gehört in `SessionContext`**, nie an `self`.
  Am WebUI-Objekt bleibt nur, was für alle gleich ist (Config-Flags, Auth, Texte).
- Der Default-Wert muss `deepcopy`-fähig sein — ein Streamer im Default würde die
  Trennung still wieder aufheben.
- Auslieferungsdateien (WAV, JSON, Markdown) hängen aus demselben Grund an der
  Sitzung (`SessionContext.tmp_files`): sonst räumt ein Download im einen Browser
  die Datei eines anderen weg. Beim nächsten Mal wird die vorherige Datei
  derselben Art gelöscht, das Verzeichnis räumt ein `atexit`-Handler ab.
  **Nur die Originale:** Gradio kopiert Ausgabedateien in seinen eigenen Cache
  (`blocks.py` → `processing_utils.move_files_to_cache`) und liefert von dort
  aus. Gut, denn das Löschen kann keinen laufenden Abruf zerreißen — aber die
  zweite Kopie verwaltet Gradio, nicht wir.

### ⚠️ Die Konsolenwarnung „Too many arguments provided for the endpoint" ist normal
Sie kommt aus Gradios **Frontend**
(`_frontend_code/client/src/helpers/api_info.ts`) und vergleicht die Zahl der
gesendeten Werte mit `api_info.parameters`. `gr.State` hat `skip_api = True` und
steht dort nicht drin — **jedes Event mit einem State als Input warnt**, ohne
dass etwas kaputt wäre. Nicht suchen, nicht "reparieren".

### ⚠️ Stolperfalle: gr.Dataframe kann kein Streaming (gemessen auf Gradio 4.44)
Die Dataframe-Komponente **verlor Updates aus Generator-Handlern** — das Frontend
fror nach den ersten Yields ein (galt für `gr.update` wie Rohwerte, `str` wie
`markdown`-datatype; per Minimal-Repro bestätigt). Zusätzlich: fester 500px-Scroll-
Viewport und eine virtualisierte Tabelle, deren Mess-Klon-Zeilen DOM-Selektoren in
Browser-Tests verfälschen. **Für live wachsende Ausgaben `gr.Markdown` (Voll-Ersatz
pro Yield) oder `gr.Chatbot` verwenden** — so macht es die Ask-All-Ansicht.

**Unter Gradio 5 ist das nicht nachgemessen.** Der Befund stammt aus der
4.44-Zeit; die Komponente kommt im Code nicht mehr vor, es gab also keinen
Anlass. Wer sie einführen will, misst neu — und schreibt das Ergebnis hierher.
Der frühere `pydantic==2.9.2`-Pin (bool-Schemas ab 2.10 ließen `gradio_client`
1.3 abstürzen) ist mit #61 **entfallen**.

### ⚠️ Der Chat läuft im `messages`-Format — und was zurückkommt, ist anders
Seit #61a ist eine Anzeige-Zeile *eine* Nachricht (`{"role", "content"}`); das
Paarformat ist in Gradio 6 ersatzlos weg. Drei Dinge, die dabei teuer waren:

1. **`content` kommt als Liste zurück, nicht als String.** Wir hängen
   `{"role": "assistant", "content": "Text"}` an; Gradio reicht die Zeile als
   `{"role": …, "metadata": None, "content": [{"type": "text", "text": …}]}`
   zurück. Mit `str()` wird daraus `"[{'text': …}]"`. **Jeder Verbraucher liest
   den Text durch `webui_format.bubble_text`** — beide Formen stehen im selben
   Verlauf nebeneinander (frisch angehängte Zeilen sind noch Strings).
2. **`evt.index` ist flach**, kein `[row, col]`. Ein nicht deutbarer Index wird
   **verworfen statt geraten**: der frühere Rückfall auf „letzte Antwort" schrieb
   eine plausibel aussehende, falsch zugeordnete Trainingszeile (#65 → #7).
3. Die Zählregel selbst ist unverändert: die k-te Antwort-Bubble ist die k-te
   `assistant`-Nachricht im Verlauf, Hinweis-Bubbles zählen nicht mit.

### ⚠️ Zwei Skripte, zwei Formen — und die Verwechslung ist stumm (#69/#61a)
Der Theme-Umschalter hat zwei Teile, und Gradio 6 will sie **unterschiedlich**:

| Teil | wohin | Form |
|---|---|---|
| Laden (Wahl wiederherstellen) | `demo.launch(js=…)` | **reiner Anweisungsblock** |
| Klick (umschalten) | `Button.click(js=…)` | Pfeilfunktion `() => {…}` |

`gr.Blocks(js=…)` gibt es nicht mehr — Gradio warnt zwar, aber `demo.js` bleibt
`None`. Und `launch(js=…)` **ignoriert eine Pfeilfunktion stillschweigend**: im
Browser gemessen lief der Rumpf null Mal, als nackter Block einmal. Beides
zusammen hätte den Umschalter still um seine Persistenz gebracht — sichtbar
erst als „das Theme vergisst sich beim Neuladen".

### ⚠️ Stolperfalle: Button-Updates nie als eigenes Event vor den Stream hängen
Der naheliegende Weg für „Senden ⇄ Stop tauschen" ist ein kleines Event vor dem
Stream-Handler (`btn.click(toggle).then(stream)`). **Kostet ~3,5 s bis zum ersten
Token** — das gequeuete `.then()` startet erst nach einem vollen Roundtrip des
ersten Events. Stattdessen die Button-Updates **in denselben Yields** des
Stream-Generators mitschicken (`ChatController.with_controls`, #35): Stop erscheint
dann nach 0,16 s. Achtung beim Schluss-Yield: für `gr.State` müssen die echten
Werte erneut mitgeschickt werden, `gr.update()` würde den Update-Marker als
Zustand speichern.

Verwandt: **`cancels` kann nur gequeuete Events abbrechen.** Zeigt die Liste auf
ein `queue=False`-Event (z. B. das letzte Glied einer `.then()`-Kette), verweigert
Gradio den Start der App komplett mit „Queue needs to be enabled!".

### ⚠️ Ein Link ist ein Reload, und ein Reload ist eine neue Sitzung (#69)
Der Theme-Umschalter waren zwei `<a href="?__theme=…">`. Ein Klick navigierte,
also lud die Seite neu, also bekam Gradio einen neuen `session_hash` — und
damit war **jeder** `gr.State` neu initialisiert: Persona, Streamer,
`conversation_state`, Gast. Im Browser nachgestellt: getippter, noch nicht
abgeschickter Text weg, zurück auf der Startseite. Beim Entwurf von #36 stand
das als „der Reload ist der Preis" im Code; der Preis war aber nie kosmetisch.

Dark-Mode ist im ausgelieferten Gradio-Bundle nichts als die Klasse `dark` am
`<body>` (Funktion `Ue` in `templates/frontend/assets/Index-*.js`). Der
Umschalter setzt sie jetzt selbst: ein `gr.Button` mit `fn=None` + `js=` —
für Gradio heißt das `backend_fn: false`, also **kein Request**. Die Wahl liegt
im `localStorage`, wiederhergestellt über `gr.Blocks(js=…)`.

Zwei Dinge, die beim Bauen wehtaten:
- Die Wiederherstellung muss **nach** Gradios eigener Initialisierung laufen
  (`Je()` liest `?__theme` bzw. `prefers-color-scheme`), sonst flackert es oder
  Gradio gewinnt — daher der `setTimeout(…, 0)`.
- Beide Skripte sind **je für sich vollständig**. Hinge der Klick am Lade-Skript,
  wäre ein früher Klick stumm wirkungslos.

Merksatz fürs Weiterbauen: alles, was rein clientseitig ist (Theme, Fokus,
Scrollen), gehört in `js=` — eine Navigation kostet die ganze Sitzung.

### ⚠️ Stolperfalle: Gradio `cancels` schließt Generatoren nicht (gemessen auf 4.44)
`cancels=[...]` bricht nur den **asyncio-Task** ab (`task.cancel()` in
`gradio/utils.py`); `reset_iterators` löscht bloß die Referenz — das `finally`
eines laufenden Generator-Handlers wird **nicht zuverlässig ausgeführt**, im
Backend gestartete Arbeit (LLM-Streams, Threads) läuft weiter (live gemessen:
Streams liefen nach Cancel komplett durch). **Lösung im Projekt:** expliziter
Kill-Switch — `SessionContext.ask_all_stop` (`threading.Event`) wird vom Reset-Handler
(eigenes, zuverlässig laufendes Gradio-Event) gesetzt und stoppt die
Broadcast-Worker direkt (`stop_event`-Parameter von `iter_broadcast_events_parallel`).
Für neue streamende Handler dasselbe Muster verwenden, nicht auf `cancels` bauen.

### ⚠️ Ein Aufgerufener fasst den Kill-Switch seines Aufrufers nicht an (#27)

`iter_broadcast_events_parallel` nimmt ein `stop_event` entgegen und benutzte
**genau dieses Objekt** als sein eigenes Abschaltsignal — inklusive `stop.set()`
im `finally`, das auch beim **normalen** Ende läuft. Für den Aufrufer war
„fertig" damit nicht mehr von „abgebrochen" zu unterscheiden.

Der Schaden lag nicht im Broadcast, sondern beim nächsten, der das Event lesen
wollte: das Ask-All-Fazit (#27) läuft hinter `if not stop.is_set()` und wurde in
der ausgelieferten Konfiguration (`broadcast_parallel: true`) deshalb **nie**
erreicht. Das Häkchen tat nichts, ohne Fehler, ohne Logzeile — nur der
sequenzielle Fallback funktionierte. Seit dieser Runde hat der Generator ein
eigenes `shutdown`-Event; `stop_event` wird nur noch **gelesen**, und
`test_a_finished_broadcast_leaves_the_callers_kill_switch_alone` nagelt das
fest.

**Die teurere Hälfte ist, warum kein Test das gesehen hat.** Es gab einen, der
genau diese Funktion prüfte — er stellte den Broadcast aber als Generator-Attrappe
nach, und die fasste das Event nicht an. Der Test war grün gegen ein Verhalten,
das es nicht gibt. Dieselbe Klasse wie die stille Richtung bei den Doubles (#67),
nur eine Ebene höher: **wo eine Attrappe die Nebenwirkung wegnimmt, um die es
geht, prüft der Test seine eigene Attrappe.** Für einen Zusammenbau, dessen
Korrektheit an einer Nebenwirkung hängt, gehört mindestens ein Test gegen das
**echte** Gegenstück — hier
`test_the_verdict_runs_after_the_real_parallel_broadcast`, der den wirklichen
Parallel-Broadcast fährt und nur das Fazit selbst mockt.

Und ein Nachspann darf den Hauptgang nicht mitnehmen: die Fazit-Phase liegt in
einem `try`, weil sonst eine Ausnahme darin den Schluss-Yield überspringt — die
Eingabe bliebe gesperrt und die vier Antworten wären für einen Fehler in der
Zugabe verloren.
