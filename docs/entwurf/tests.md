# Tests, Browser-Rauchtest, Test-Doubles

Testaufrufe und Fixtures, was der Browser-Test sieht, warum Doubles aus `tests/doubles.py` kommen, der Guard-Korpus.

**Kein Test fragt ein echtes Modell (seit 2026-11-26).** Eval-Suite, Stoppuhr,
Blindverkostung, Injection-Sonde und die Live-Tests (`@pytest.mark.ollama`)
sind ins Lab umgezogen (`YulYen/YulYen_Lab`): sie messen Modell und Prompt,
nicht diesen Code, und ein roter Lauf dort ist ein Befund, kein Defekt. Hier
blieb, was ohne Modell eine Aussage über den Code macht — darunter der
Guard-Red-Team-Korpus (`tests/guard_redteam.yaml`).

## Tests ausführen

Die Kommandos stehen im `Makefile` (und in `CLAUDE.md`), die Fixtures in
`tests/conftest.py`. Was man dort nicht sieht:

- Marker `@pytest.mark.browser`: fährt die **laufende** WebUI im echten Chromium
  (`make test-browser`, ~100 s). Aus allen anderen Zielen und aus der CI
  ausgenommen, weil er Playwright *und* einen Browser-Build braucht; ohne
  Playwright wird sauber übersprungen
- spaCy-Modelle (`python -m spacy download de_core_news_lg`) schalten die
  Keyword-/Wiki-Tests frei; ohne Modell werden sie sauber geskippt

### Der Browser-Rauchtest prüft das, was in-process unsichtbar ist
`tests/test_web_ui_wiring.py` baut die Oberfläche ohne Server und fängt
verrutschte Bindungen. **Was das Frontend entscheidet, sieht es nicht:** ob ein
Generator seine Yields ausliefert, ob ein Klick die Seite neu lädt, ob ein
Daumen ankommt. Genau diese Klasse war im Projekt teuer — #35 (Button-Tausch als
Folge-Event kostete 3,5 s), #69 (der Theme-Link kostete die ganze Sitzung), die
Dataframe-Stolperfalle.

`tests/test_webui_browser.py` fährt deshalb die laufende App mit Dummy-Backend
im echten Chromium: Tokens kommen an, Senden↔Stop tauscht, Statuszeile
erscheint, der Theme-Umschalter lädt **nicht** neu (nachgestellt am getippten,
nicht abgeschickten Text) und überlebt trotzdem einen echten Reload, die
Verlauf-Karte fehlt ohne Anmeldung, ein Daumen landet im Vote-Log.

Zwei Dinge, die beim Bauen wehtaten und beim nächsten Mal Zeit sparen:
- **Nicht auf `networkidle` warten.** Gradio hält eine Verbindung offen, der
  Zustand tritt nie ein — `page.goto(..., wait_until="domcontentloaded")` plus
  ein Warten auf ein echtes Element.
- **Über Rollen selektieren, nicht über CSS-Klassen.** Gradio hat den Daumen
  zwischen 4.44 und 5.x von `like-button`/„like" auf `icon-button`/„Like"
  umbenannt. `get_by_role("button", name=re.compile(r"^like$", re.I))` überlebt
  beides; `exact=True` wäre case-sensitiv und genau hier zerbrechlich.
- **Die Locale des Browser-Kontexts festnageln** (`new_context(locale="en-US")`).
  Seit Gradio 6 ist das eigene Bedienchrom **übersetzt**: derselbe Daumen heißt
  auf einem deutschen System „Gefällt mir", auf einem englischen „Like" — ein
  Rollen-Selektor allein reicht also nicht mehr. Ohne die Zeile hängt das
  Testergebnis an der Spracheinstellung des Rechners, und zwar in der
  unangenehmen Richtung: auf dem Linux-Runner grün, auf Yuls Windows rot.
  Unsere eigenen Texte folgen weiter `language:` aus der Config, bleiben also
  deutsch. Nebenbei der Grund, warum der Anker im Regex zählt — „Gefällt mir"
  ist ein Präfix von „Gefällt mir nicht".

**Seit #98 fährt er auch Ask-All und den Verlauf.** Zwei Fälle, mehr nicht:
„Frage an alle" bis alle vier Antworten da sind und die Eingabe wieder frei
ist, und die Kette aufzeichnen → Verlauf öffnen → fortsetzen, am Ende gegen die
SQLite-Datei geprüft (ein Gespräch, vier Nachrichten). Für den Verlauf läuft
eine **zweite** App mit `storage.shared_without_login` — die ausgelieferte Lage
hat ohne Anmeldung keine Ablage (#72). Der App-Start ist dafür ein
Kontextmanager (`_running_app`); beide Apps leben bis zum Modulende, und weil
die Config ein Singleton ist, stehen alle Tests gegen die erste App **vor** dem
Fixture der zweiten. Wer einen weiteren Fall gegen die erste App schreibt,
setzt ihn darüber.

**Und warum das erst hier auffiel:** der Marker ist aus CI und `make check`
ausgenommen, der Test läuft also nur, wenn ihn jemand von Hand startet. Nach
dem Sprung auf Gradio 6.22 war er auf einer deutschen Windows-Kiste rot, ohne
dass irgendein Job das gemeldet hätte. Wer die Gradio-Version hebt, fährt
`pytest -m browser` einmal von Hand nach — kein anderes Gate schaut dorthin.

**Der Test ist zuerst gegen die alte Version grün zu bekommen.** Bei #61 war er
auf 4.44 grün, bevor migriert wurde — sonst ist später nicht zu unterscheiden,
ob die Migration bricht oder das Testskript.

### Gradio-Ausgaben werden per Name geprüft, nie per Position (#103)

Eine Persona-Aktion liefert ein Tupel in der Reihenfolge von
`PERSONA_OUTPUT_KEYS`. Ältere Tests griffen mit Zahlen zu (`updates[28]` für
das Mikro). Rutscht im Layout eine Komponente dazwischen, prüft so eine Zahl
**still die falsche Ausgabe** — der Test bleibt grün oder wird aus dem
falschen Grund rot. `_named(updates)` in `tests/test_web_ui.py` macht daraus
ein dict nach Namen und meldet mit `strict=True` auch eine falsche Länge.

**Ein Aufruf, ein Test.** Acht Tests prüften je ein Teilstück desselben
`_reset_ui_updates()`; zusammengelegt prüft einer alles, mit dem Namen der
Ausgabe in jeder Fehlermeldung. Per Mutation nachgewiesen, dass er genauso
anschlägt (Mikro nicht ausgeblendet → `AssertionError: mic_audio`).

**Coverage ist kein Löschkriterium.** Beim Durchsehen deckten 553 von 763
Testfunktionen keine einzige Zeile ab, die nicht auch ein anderer Test
berührt — weil Coverage misst, was *läuft*, nicht was *geprüft* wird. Ein
Randfall-Test läuft durch dieselben Zeilen wie der Normalfall. Gelöscht wird
nur, was nachweislich dasselbe prüft; die Gegenprobe ist eine unveränderte
Gesamtabdeckung.

### Test-Doubles kommen aus `tests/doubles.py` (#67)
Streamer, Guard und Factory werden **nicht** von Hand nachgebaut, sondern über
`streamer_double()`, `permissive_guard_double()` und `factory_double()` bezogen.
Alle drei bauen auf `create_autospec(…, instance=True)`.

`factory_double()` belegt `get_auth_provider()` und `get_store()` mit den echten
Produktionsvorgaben (`DisabledAuth`, `NullStore`) vor — beide sind *falsy*, und
genau dort schlägt die stille Richtung sonst zu: `gradio_auth()` wäre ein Mock
statt `None`, `store.records` ein wahrer Mock statt `False`.

Der Grund ist ein Fehler, der an einem Tag viermal zuschlug — in zwei Richtungen:

| Richtung | Vorher | Jetzt |
|---|---|---|
| **laut** | `SimpleNamespace`/eigene Stub-Klassen fielen mit `AttributeError`, sobald der Produktivcode eine neue Methode rief | jede Methode des Originals ist automatisch da |
| **still, teuer** | ein nacktes `Mock()` liefert für *jedes* Attribut ein wahrheitswertiges Mock; `getattr(streamer, "guard", None)` bekam nie `None`, der Test blieb grün, und es fiel erst tief im Guard mit `'Mock' object is not subscriptable` | ein nie gesetztes Instanzattribut fehlt ehrlich, `getattr(…, None)` ergibt `None` |

**Klassen-Annotationen an den Kollaborateuren wären der falsche Weg.** Sie würden
`guard` und `persona_options` in `dir()` heben — und damit die stille Richtung
wieder öffnen. Ein Attribut, das noch niemand gesetzt hat, *soll* fehlen.

**Was `create_autospec` nicht abfängt:** *Setzen* unbekannter Attribute bleibt
erlaubt (kein `spec_set`, sonst ließe sich `persona_options` gar nicht
vorbelegen). Ein Tippfehler in der Vorbelegung bliebe also stumm — deshalb prüft
`test_the_presets_are_attributes_a_real_streamer_actually_has` sie gegen eine
echte Instanz. Wer eine Vorbelegung ergänzt, trägt sie dort nach.

Vorbelegt ist bewusst nur das Nötigste. `stream` liefert eine **Liste**, keinen
`iter([])` — ein Iterator wäre nach dem ersten Aufruf stumm leer.

### Die Nähte, die keinen Test hatten (#96)

Drei Stellen standen nach den Fehlersuchen #87/#95 in den PRs unter „Nicht
geprüft", obwohl kein fehlendes Werkzeug schuld war — sie waren schlicht nicht
testbar gebaut:

- **Der echte Start.** `launch.main()` ist die Stelle, an der Config, Factory,
  Anmeldung und Oberfläche zusammenkommen, und hatte keinen Test.
  `tests/test_launch_start.py` startet `python -m yulyen_ai` als Prozess mit
  der ausgelieferten Config (Dummy-Backend, alles Äußere aus) und prüft die
  beiden Abbruchpfade der Anmeldung: Exit 4, lesbare Meldung, kein Stacktrace.
  Als Subprozess, weil genau das die Aussage ist — so startet der Betreiber.
  Kostet rund 3,5 s je Fall; wer einen weiteren Startpfad absichern will,
  hängt ihn an `_start()`.
- **Eine Eingabe im Terminal.** Die Schleife in `TerminalUI.launch()` hing an
  `input()`. Ihr Rumpf ist jetzt `handle_input(text) -> bool` (`False` beendet
  die Sitzung) und damit ohne Attrappe prüfbar: Kommandos, leere Eingabe und
  die Reihenfolge Guard → Wiki → Modell.
- **Ask-All mit abgelehnter Frage** — gegen einen echten Guard aus der Factory.

Dazu läuft der Browser-Rauchtest jetzt auch in der Sandbox (siehe
[arbeitsweise.md](arbeitsweise.md)). Die Suche nach dem mitgelieferten Chromium
im Test griff übrigens ins Leere: der Ordner heißt inzwischen `chrome-linux64`.
