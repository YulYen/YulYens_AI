# Latenz: Holdback, Moderator

Warum kein Modell denkt, der Guard-Holdback (#51) mit seinen Messtabellen, der Freigabe-Index über den rohen Text.

Die **Stoppuhr** (#42), mit der das gemessen wird, und ihre Läufe leben seit
2026-11-26 im Lab (`python -m yulyen_lab bench`, `docs/stoppuhr.md` dort).
Ihre Regel gilt weiter: verglichen werden erstes ausgeliefertes Zeichen und
Zeichen/s, nie die Gesamtdauer.

## Kein Modell denkt hier (#78)

Reasoning-Modelle (Qwen 3.x, Gemma 4) schicken ihre Überlegung in
`message.thinking` voraus, der Streamer liest nur `message.content`. Das erste
ausgelieferte Zeichen käme also erst nach dem Nachdenken, und nichts davon wäre
zu sehen. `OllamaLLMCore` schickt deshalb bei **jeder** Anfrage `think=False`.
Einen Schalter gibt es bewusst nicht — wer das Denken zeigen will, muss zuerst
den Streamer `thinking` lesen lassen.

**Warum an jedes Modell, nicht nur an die mit der Fähigkeit (2026-11-15).**
Bis dahin fragte der Kern je Modell `show().capabilities` und schickte
`think=False` nur bei `thinking` — aus Vorsicht, weil ungemessen war, ob jede
Server-Fassung den Parameter bei anderen Modellen annimmt. Daran scheiterte
Googles QAT-Fassung von Gemma 4
(`hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf`): Sie meldet die Fähigkeit
nicht, denkt aber — 618 Tokens Überlegung für fünf Wörter, im Live-Test zwei
leere Antworten und dreifache Laufzeit. Auf Ollama 0.40.16 nehmen alle sieben
Modelle auf der Kiste `think=False` an, auch die ohne Fähigkeit (`ministral-3`,
`devstral-small-2`); abgewiesen wird nur `think=True`. **Was ein Modell über
sich meldet, ist kein Beleg dafür, was es tut.**

Gemessen auf der Kiste (2026-11-15): qwen3.8:27b und qwen3.6:35b liegen beim
ersten Zeichen bei 1,5 bzw. 0,7 s, also in derselben Größenordnung wie das 14B
(0,33 s) — das Denken ist aus.

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
Zahlen mit `ministral-3:8b` stehen im Lab (`docs/stoppuhr.md`). Kurz: 0,15 /
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
Genau deshalb misst die Stoppuhr (im Lab) das erste *ausgelieferte*
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
