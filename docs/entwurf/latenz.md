# Latenz: Stoppuhr, Holdback, Moderator

Die Stoppuhr (#42) und ihr erster Lauf (#42a), der Guard-Holdback (#51) mit allen Messtabellen, der Freigabe-Index über den rohen Text.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Die Stoppuhr (#42)

Die messbare Antwort auf „ist es schneller geworden?" — und das Gegenstück zur
Eval-Suite: dort Qualität, hier Zeit.

```bash
python scripts/run_bench.py -e classic                    # braucht Ollama
python scripts/run_bench.py -e classic --model <anderes>  # Modellwechsel vergleichen
python scripts/run_bench.py -e classic --holdback 0       # die Tabelle aus #51 nachfahren
python scripts/run_bench.py -e classic --backend dummy    # nur: läuft der Harness?
make bench                                                # Kurzform der ersten Zeile
```

Der Lauf schreibt `logs/bench/report.md` und `report.csv`; das CSV ist das
Artefakt, weil sich zwei Läufe dort zeilenweise gegenüberstellen lassen.

**Gemessen wird das erste *ausgelieferte* Zeichen, nicht das erste Token des
Modells.** Das ist der ganze Grund, warum das Werkzeug existiert und nicht
einfach `StreamStats` ausgelesen wird: dazwischen liegt der Guard-Holdback, und
der ist im Projekt der größte Einzelposten der wahrgenommenen Antwortzeit. Wo
beide Zahlen zu haben sind, steht die Differenz als eigene Spalte —
`t_model_first_ms` kommt aus `StreamStats`, das der Provider seit #36 ohnehin
ablegt.

**Zwei Leitkennzahlen, und die dritte Zahl ist ausdrücklich keine:** erstes
Zeichen und Zeichen/s vergleichen zwei Läufe, die **Gesamtdauer nicht** — sie
hängt vor allem daran, wie viel das Modell zu schreiben beschließt. Dieselbe
Lehre wie bei #41a, nur an anderer Stelle: wer die instabile Zahl oben
hinschreibt, vergleicht später Münzwürfe.

Sechs Entwurfsentscheidungen, die man beim Anfassen leicht umdreht:

1. **Rundenweise messen, nicht fragenweise.** Runde 1 stellt alle Fragen, dann
   Runde 2 — nicht dreimal Frage 1, dann dreimal Frage 2. Zwei unabhängige
   Gründe: eine Maschine, die im Lauf warm wird, benachteiligt sonst genau die
   Frage, die hinten steht; und dieselbe Frage direkt hintereinander trifft den
   **Prompt-Cache** des Backends, was die zweite Runde grundlos schneller macht.
   Bei nur *einer* Frage greift der zweite Schutz nicht — dann warnt der Lauf.
2. **Aufwärmrunden werden ausgewiesen, nicht weggeworfen.** Der erste Aufruf
   lädt das Modell in den VRAM und ist um Größenordnungen langsamer. Das ist
   eine eigene, interessante Zahl — sie darf nur nicht in den Median rutschen.
3. **Median, nicht Mittelwert.** Bei einer Handvoll Läufe kippt ein einzelner
   Ausreißer den Mittelwert: 100/110/5000 ms ergibt Ø 1736 und Median 110.
4. **Eine Fehlermeldung ist keine Bestzeit.** `stream()` *fängt* Backend-Fehler
   ab und liefert sie als Text aus — ein nicht erreichbares Ollama wäre sonst
   die schnellste Messung des Laufs. Der Harness hält den Antwortanfang gegen
   `LLM_ERROR_MESSAGE` (dafür ist die Konstante da) und bricht ab, wenn schon
   die *erste* Messung fehlschlägt: das ist ein Aufbaufehler, kein Ergebnis.
   Ein Aussetzer mittendrin wird dagegen aufgezeichnet und der Lauf läuft
   weiter.
5. **Die Kopfzeile trägt alles, was zwei Läufe unvergleichbar macht** — Modell,
   Backend, Messpfad, `num_ctx`, `keep_alive`, Version und vor allem der
   Holdback samt der Frage, ob er überhaupt **wirkt**: ohne aktive
   Ausgangsprüfung setzt der Moderator ihn selbst auf 0, und zwei Läufe mit
   derselben Zahl in der Config unterscheiden sich dann drastisch, ohne dass
   die Zahl es verriete.
6. **Der Default-Persona wird abgeleitet, nicht verdrahtet:** die mit der
   niedrigsten Temperatur (in `classic` also PETER). Sie liefert über mehrere
   Runden die ähnlichsten Antworten, und die Antwortlänge ist der größte
   Einzeleinfluss auf die Gesamtdauer. Abgeleitet, damit der Default auch für
   ein fremdes Ensemble stimmt.

**Zwei Messpfade, die nicht dasselbe messen.** In-process (Default) misst
Persona-Prompt, Guard, Holdback und Modell — Wiki und RSS bleiben bewusst
draußen, weil ihr Abruf je Frage um Sekunden schwankt und die Zahl dominieren
würde. `--api-url` misst den vollen Pfad über den laufenden Server, inklusive
FastAPI/SSE und allem, was dort konfiguriert ist; dafür fehlen die
Modellzeiten, die es nur in-process gibt. Der Modus steht deshalb in jeder
Kopfzeile.

**Der Fragensatz liegt in `src/bench/questions.py`, nicht in der Config.** Er
ist ein Maßstab: eine Frage zu ändern gibt die Vergleichbarkeit mit allen
früheren Läufen auf, und das soll ein Commit sein, keine Config-Zeile. Eigene
Sätze gehen über `--questions datei.txt`. Die letzte Frage ist absichtlich ein
langer Prompt mit kurzer Antwort — sie ist die einzige, die die *Prefill*-Zeit
sichtbar macht; der Wirtstext ist echter Fließtext und keine Wiederholung
desselben Satzes, weil wiederholter Text billiger zu verarbeiten ist und den
Prefill schneller aussehen ließe, als er ist.

### Was der erste Lauf ergeben hat (2026-08-30, #42a)

Gemessen auf Yuls Kiste, ausgelieferte `config.yaml`, PETER, 5 Fragen × 3
Runden, GPU sonst frei.

| | `ministral-3:8b` (Q4) | `leo-hessianai-13b-chat.Q5` |
|---|---|---|
| erstes Zeichen (Median) | **0,46 s** | 2,18 s |
| Durchsatz (Median) | **107 Zeichen/s** | 29,3 Zeichen/s |
| davon Guard-Holdback | 299 ms (**65 %**) | 1.221 ms (56 %) |
| Kaltstart (Modell in den VRAM) | 30,7 s | 30,5 s |

**Das ist die Baseline für jeden künftigen Modellwechsel** — und zugleich die
Latenz-Verifikation, die #17 offen ließ. Ihr Ergebnis ist unbequem: das
Backend ist gar nicht das Problem. Das erste Token des Modells liegt nach rund
150 ms vor, ausgeliefert wird es nach 460 ms. **Zwei Drittel der
wahrgenommenen Antwortzeit entstehen nach dem Modell, nicht in ihm.** Wer die
gefühlte Geschwindigkeit verbessern will, dreht am Holdback, nicht am
Warm-up — jede weitere Backend-Optimierung verschwindet hinter diesen 300 ms.

#### Die Holdback-Tabelle, diesmal am echten Modell

Die Tabelle aus #51 entstand gegen das getaktete Dummy-Backend. Das war
methodisch richtig (lastunabhängig), ließ aber offen, ob die Rechnung neben
echter Generierung noch gilt. Sie gilt:

| `holdback` | erstes Zeichen | Aufschlag | rechnerisch (`holdback` ÷ 107 Z/s) |
|---|---|---|---|
| 0 | 0,15 s | — | — |
| **32 (Default)** | **0,46 s** | +0,31 s | +0,30 s |
| 96 | 1,12 s | +0,97 s | +0,90 s |

Der Holdback kostet also auch am echten Modell genau das, was er rechnerisch
kostet — der Default 32 bleibt richtig gewählt.

**Ein Nebenbefund, der bei der Dummy-Messung nicht auffallen konnte:** bei
`holdback: 96` war für `q1_kurz` (85 Zeichen Antwort) `t_first` **gleich**
`t_total`. Die Antwort ist kürzer als der Holdback, also wird sie erst beim
`flush()` freigegeben — es streamt **gar nichts**, die Antwort erscheint am
Stück. Wer den Holdback hochdreht, schaltet für kurze Antworten das Streaming
ab, ohne dass irgendetwas davon berichtet.

#### Was das für #7 heißt

`leo-hessianai-13b-chat.Q5` ist **3,7-mal langsamer im Durchsatz und 4,7-mal
langsamer bis zum ersten Zeichen**. Das ist kein Randdetail für die
LoRA-Strecke, sondern ein Preisschild: ein Adapter auf LeoLM 13B muss die
Antwort*qualität* deutlich heben, um eine Vervierfachung der Wartezeit
aufzuwiegen. Nebenbei kostet der Holdback dort 1,22 s statt 0,30 s — er zählt
*Zeichen*, und ein langsamer schreibendes Modell braucht für dieselben 32
Zeichen viermal so lange. Wer auf 13B wechselt, senkt also sinnvollerweise
`security.stream_holdback_chars` mit.

**Der Kaltstart ist bei beiden Modellen rund 30 s** und hängt damit
offensichtlich nicht an der Modellgröße — bei 8 GB VRAM und 5–6 GB
Modellgewicht dominiert das Laden von der Platte. Er ist der Grund, warum
`core.warm_up` existiert.

**Der Skriptname ist `run_bench.py`, nicht `bench.py`** — wie `run_evals.py`
neben dem Paket `evals`. Ein `scripts/bench.py` heißt beim Import schlicht
`bench` und verdeckt das gleichnamige Paket unter `src/`; aufgefallen, weil
`tests/test_audit_deps.py` `scripts/` in den `sys.path` hängt und die
Testsammlung danach im Skript statt im Paket landete.

### ⚠️ Der Guard-Holdback bestimmt die wahrgenommene Antwortzeit (#51)
`_StreamModerator` (`core/streaming_provider.py`) hält die letzten
`_STREAM_HOLDBACK_CHARS` Zeichen zurück, damit ein PII-/Secret-Muster nicht über
eine Token-Grenze hinweg durchrutscht. Konsequenz: **vor `holdback` Zeichen geht
überhaupt nichts an die Anzeige.** Im Browser gemessen, 24 Zeichen/s:

| Variante | erster Token sichtbar |
|---|---|
| nackte Gradio-App (kein Guard) | 0,95 s |
| Projekt, `holdback: 96` | 4,13 s |
| Projekt, `holdback: 32` (Default) | **1,91 s** |
| Projekt, `holdback: 0` | 0,39 s |

**Am echten Modell nachgemessen (2026-08-30, #42a) — die Rechnung gilt auch
dort.** Die Tabellen hier entstanden gegen das getaktete Dummy-Backend; die
Zahlen mit `ministral-3:8b` stehen im Abschnitt „Die Stoppuhr". Kurz: 0,15 /
0,46 / 1,12 s für Holdback 0 / 32 / 96, also der rechnerische Aufschlag. Neu
dort und hier nicht sichtbar: ist die Antwort **kürzer** als der Holdback,
streamt sie gar nicht mehr, sondern erscheint am Stück.

**Auf Gradio 6.22 nachgemessen (2026-08-07) — die Tabelle gilt weiter.** Die
Zahlen oben stammen aus der 4.44-Zeit; seither sind Gradio, Starlette und das
ganze Frontend gewechselt, und eine Tabelle, die niemand nachprüft, ist
irgendwann Behauptung statt Messung. Gleicher Aufbau (im Browser, Klick bis
erstes sichtbares Zeichen, 24 Zeichen/s), 5 Läufe je Variante:

| `holdback` | 4.44 (#51) | **6.22** | rechnerisch (`holdback` ÷ 24) |
|---|---|---|---|
| 0 | 0,39 s | **0,66 s** | 0 s |
| 32 (Default) | 1,91 s | **2,02 s** | 1,33 s |
| 96 | 4,13 s | **4,78 s** | 4,00 s |

Die belastbare Aussage steht in der letzten Spalte: der **Aufschlag über die
Grundlatenz** ist 1,36 s bzw. 4,12 s — also fast exakt `holdback ÷ Tempo`, wie
es sein muss. Der Holdback kostet, was er rechnerisch kostet; daran hat der
Versionssprung nichts geändert, und der Default 32 bleibt richtig gewählt.

**Fremdlast auf der GPU stört diese Messung nicht** — nachgeprüft, weil der
erste Durchgang zufällig neben einem laufenden Spiel entstand (87 % VRAM
belegt) und der zweite auf freier Maschine (13 %). Die Mediane unterscheiden
sich um 0,02 s. Das ist keine Überraschung, sondern eine Eigenschaft des
Aufbaus: gemessen wird gegen das **Dummy-Backend** mit fest getakteten
24 Zeichen/s, es läuft also kein Modell mit. Wer denselben Aufbau je auf echtes
Ollama umstellt, verliert genau diese Robustheit — dann misst er die
Auslastung mit.

Die Grundlatenz selbst liegt 0,24 s höher als 2026 gemessen. Ob das an Gradio 6
liegt oder an der Maschine, ist **nicht** entschieden — die 4.44-Zahlen sind
nicht auf derselben Kiste entstanden. Wer daraus eine Regression ableiten will,
misst beide Versionen nebeneinander; als Größenordnung taugt es, als Befund
nicht.

Zwei Fallen im Messaufbau, beide zuerst als Latenzbefund missverstanden:

1. **Der Chat behält die vorherige Antwort.** Ein Selektor auf „Antwortblase
   mit Text" findet sie sofort und meldet 0,04 s — bei 24 Zeichen/s
   physikalisch unmöglich, und nur daran aufgefallen. Jede Antwort braucht
   eine laufende Nummer als Marker.
2. **Während des Streams heißt der Knopf „Stop".** Ein Klick auf „Senden"
   wartet dann bis zum Streamende, und alle Varianten landen bei ~8,5 s. Sah
   wie ein Latenzbefund aus, war einer des Messaufbaus.

Der Default 32 ist kein runder Wert: das längste Blocklist-Muster (AWS-Secret)
schlägt erst nach Label + 30 Zeichen an, deshalb bleibt Schlüsselmaterial erst
ab einem Holdback von 30 vollständig verdeckt. Darunter rutscht es mit durch —
festgenagelt in `test_default_holdback_keeps_key_material_hidden`.

Der Verzug entsteht **serverseitig** — der SSE-Frame auf `/queue/data` geht erst
bei +4,09 s raus, gerendert wird danach in 40 ms. Beim Suchen also nicht im
Frontend anfangen. Einstellbar über `security.stream_holdback_chars`; bei
abgeschalteten Ausgangs-Checks (`pii_protection` **und** `output_blocklist` aus)
entfällt der Holdback automatisch, weil es dann nichts zu prüfen gibt.

Wichtig für #17/#42: eine backendseitige Messung von „Zeit bis zum ersten Token"
sieht diesen Anteil **nicht** — das Modell liefert längst, die Anzeige wartet.
Genau deshalb misst die Stoppuhr (siehe oben) das erste *ausgelieferte*
Zeichen und stellt die Modellzeit daneben; die Differenz ist diese Tabelle.

**Der Holdback ist nur die eine Hälfte.** #51 hat die Zeit bis zum *ersten*
Token gemessen und daraus den Default abgeleitet — korrekt, aber unvollständig.
`_StreamModerator.feed()` rief `process_output` **pro Token über den gesamten
bisherigen Text** auf, war also quadratisch im Antwortumfang. Mit #58 behoben,
mit der ausgelieferten Config gemessen (nur `output_blocklist` aktiv):

| Antwort | vorher | jetzt |
|---|---|---|
| 200 Tokens (800 Zeichen) | 4 ms | 4 ms |
| 1000 Tokens (4.000 Zeichen) | 102 ms | 23 ms |
| 2000 Tokens (8.000 Zeichen) | 409 ms | 45 ms |
| 4000 Tokens (16.000 Zeichen) | **1.605 ms** | **85 ms** |

Der Holdback kostet weiterhin einmalig; der wachsende Anteil ist weg, weil der
Moderator nur noch ein Fenster um die Freigabegrenze prüft
(`_CONTEXT_WINDOW_CHARS`) statt alles Bisherige. `test_moderation_cost_stays_
linear_in_the_answer_length` hält das fest — es misst bewusst das *Verhältnis*,
nicht die absolute Zeit, damit es auf langsamen Runnern nicht flackert.

### ⚠️ Der Freigabe-Index läuft über den rohen Text, nicht über den maskierten
Die Maskierung ändert die Länge (`max@example.com` → `[PII]`). Zählt man mit,
wie viel vom *maskierten* Text schon raus ist, zeigt der Index nach dem ersten
Treffer auf die falsche Stelle: Modelltext verschwindet oder kommt doppelt
(belegt: aus „… Adresse [PII] und dann noch viel Text …" wurde ausgeliefert
„… Adresse vorname.nachname.abt**viel Text** …").

Deshalb zählt `_released` **rohe** Zeichen, und die Freigabegrenze darf nie
mitten in einem Treffer liegen — das prüft `BasicGuard.output_match_crossing`
und zieht sie sonst vor den Trefferanfang zurück. Nur dadurch liefert das
Maskieren eines Abschnitts *für sich* dasselbe Ergebnis wie über den ganzen
Text. Die Invariante steht als Test da: gestreamt muss herauskommen, was
`process_output` am Stück liefert — solange das Muster in den Holdback passt.
Passt es nicht, darf der Präfix durchrutschen; das ist die dokumentierte
Best-effort-Grenze und keine Regression.

**Aufgezeichnet wird, was der Moderator freigibt** — nicht der rohe Token.
Vorher sammelte `stream()` die Rohtokens, und bei `pii_protection: true` stand
im Store und im JSONL-Mitschnitt die unmaskierte Fassung, während der
Bildschirm maskiert war. Über Verlauf, Markdown-Export und JSON-Download kam
sie vollständig wieder heraus — die Maskierung war Bildschirmschoner statt
Datenschutz.
