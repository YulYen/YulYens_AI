# Tests, Browser-Rauchtest, Test-Doubles, Eval-Suite

Testaufrufe und Fixtures, was der Browser-Test sieht, warum Doubles aus `tests/doubles.py` kommen, die Eval-Suite (#41) samt Baseline.

## Tests ausführen

Die Kommandos stehen im `Makefile` (und in `CLAUDE.md`), die Fixtures in
`tests/conftest.py`. Was man dort nicht sieht:

- Marker `@pytest.mark.ollama`: wird geskippt wenn Ollama nicht erreichbar.
  `YULYEN_TEST_MODEL` ersetzt dabei das Modell aus `config.yaml` — für
  Modellvergleiche (#78), ohne die Config anzufassen. Gilt nur für Läufe, die
  wirklich Ollama ansprechen; Dummy-Tests bleiben unberührt
- **Ein Test, der zwei Modelle unterscheiden soll, braucht eine Aufgabe, die
  trennt** (#78, 2026-11-08). Die ersten 14B-Tests schaffte keins der beiden
  Modelle (0/20); sie maßen die Aufgabe, nicht das Modell. Kandidaten deshalb
  gegen *beide* Modelle kalibrieren und nur nehmen, was das stärkere ≥ 19/20 und
  das schwächere deutlich seltener schafft (`tests/test_ai_via_api_14b.py`).
  Deutsche Aufgaben mit Zahlen klären den Dezimalpunkt: „2.675" lasen beide
  Modelle als Tausenderpunkt
- Marker `@pytest.mark.browser`: fährt die **laufende** WebUI im echten Chromium
  (`make test-browser`, ~100 s). Aus allen anderen Zielen und aus der CI
  ausgenommen, weil er Playwright *und* einen Browser-Build braucht; ohne
  Playwright wird sauber übersprungen
- spaCy-Modelle (`python -m spacy download de_core_news_lg`) schalten die
  Keyword-/Wiki-Tests frei; ohne Modell werden sie sauber geskippt

### Lokaler Gesamtlauf am 2026-11-13 (8-GB-Rechner, Windows, Python 3.12.10)

Stand `main` bei `e69f4a1` (PR #237), also einschließlich der Sandbox-PRs
#229–#237, die Ollama, spaCy und Windows nie gesehen hatten. Der andere Rechner
muss das für diesen Stand nicht wiederholen — **außer den zwei Wiki-Fällen
unten**, die hier nicht prüfbar waren.

- `python -m pytest -q -m "not browser"` mit `YULYEN_TEST_MODEL=ministral-3:8b`:
  **1397 bestanden, 4 fehlgeschlagen, 8 übersprungen.** `-m browser`: **14 von
  14 bestanden** (20 s). Das venv entsprach den Requirements ohne Nachinstallation
- **Auf einer 8-GB-Karte braucht der Lauf `YULYEN_TEST_MODEL=ministral-3:8b`.**
  Der Default ist `ministral-3:14b`, und die Tests überspringen
  `config.local.yaml`; ohne die Variable scheitern zehn Ollama-Tests mit 404
- **Nicht geprüft: `test_api_contract[case1]` und `[case2]`** (Portugal/Merz,
  Jens Spahn). Sie brauchen Kiwix mit dem ZIM `2026-10` unter dem Pfad aus
  `config.yaml` (`C:/Develop/…`); hier liegt `2026-01` unter
  `C:\wikipedia-de-offline`. Ohne Wiki antwortet das Modell aus dem Gedächtnis
  und fällt durch — die Tests überspringen in dem Fall nicht, anders als
  `test_wiki.py`
- `test_peter_antwortet_in_exakt_fuenf_woertern`: mit dem 8B 2 von 5 bestanden
  (sechs statt fünf Wörter). Modellfrage, kein Rückschritt im Code — gegen das
  14B hier nicht messbar
- **Echter Befund: Gradios Telemetrie hält einen abgebrochenen Start fest**
  (#99). `test_an_unusable_login_stops_the_start_readably[local-ohne-nutzer]`
  lief hier dreimal in Folge in den 120-s-Timeout. Die Meldung und `sys.exit(4)`
  kommen nach 3 s; der Prozess endet nicht, weil zwei nicht-daemonische
  Gradio-Threads (`version_check`, `_do_normal_analytics_request` →
  `huggingface_hub`-Telemetrie) auf eine Verbindung warten. Auf diesem Rechner
  ist IPv6 kaputt, jeder Versuch gegen `huggingface.co` läuft in den Timeout.
  Gegenprobe: mit `GRADIO_ANALYTICS_ENABLED=False` besteht der Test in 3,5 s

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

## Eval-Suite (#41)

Messbare Antwort auf „ist das Modell besser geworden?" — das Vergleichsartefakt
für #7 (LoRA). Details in [evals/ReadMe.md](../../evals/ReadMe.md).

```bash
python scripts/run_evals.py -e classic               # voll (braucht Ollama)
python scripts/run_evals.py -e classic --guard-only  # Guard-Teil, braucht kein Modell
make evals                                           # Kurzform für --guard-only
```

- Korpora als YAML in `evals/`, Code in `src/evals/` — neue Fälle per YAML, nicht per Testcode
- `checks` = deterministisch (Regex/Länge, Platzhalter `{today_de}` & Co.),
  `expect_traits` = LLM-as-judge 1–5 (4+ besteht, 3 nicht)
- **Vergleiche den Ø-Score, nicht die Bestehensquote (#41a, gemessen).** Sechs Läufe
  mit identischem Code ergaben 3–6 von 17 bestandenen Fällen (**27 % relative
  Streuung**), aber Ø 3,57–3,79 (**1,9 %**) — der Mittelwert ist vierzehnmal
  stabiler. Ursache ist die Schwelle: 5–7 der 17 Fälle liegen im Band 3,0–3,9,
  also direkt unter „4 besteht", und entscheiden sich an einem Zehntelpunkt. Wer
  Baseline gegen Adapter (#7) über die Quote vergleicht, misst Münzwürfe
- **Nachtrag 2026-11-08: die 3,73 gilt nur für den alten Rechner.** Auf der neuen
  Kiste misst dieselbe Kombination (8B/8B, gleicher Korpus) Ø 3,35 (3,27 / 3,50 /
  3,29), außerhalb jeder bisherigen Spanne. Ein Vergleich braucht deshalb **beide
  Seiten frisch auf derselben Kiste**, nie eine übernommene Zahl. Außerdem kennt
  der Judge das heutige Datum nicht und wertet richtige Datumsantworten als falsch
  (`ts_knows_today`). Details: [modellwechsel_november_2026.md](../modellwechsel_november_2026.md#messung-auf-yuls-kiste-2026-11-08)
- **Die Baseline für #7 steht bei Ø 3,73** (2026-08-07, drei Läufe: 3,70 / 3,68 /
  3,80; Quote 5–6 von 17). Modell und Judge `ministral-3:8b`, Wiki offline über
  kiwix-serve, ausgelieferte `config.yaml`. Gemessen **nach** dem Sprung auf
  Gradio 6.22 / pydantic 2.12 / FastAPI 0.141 — die Zahl liegt mitten in der
  #41a-Spanne, der Stack-Wechsel hat die Antwortqualität also nicht bewegt.
  Damit ist sie der Vergleichspunkt für den LoRA-Adapter; `leo-hessianai-13b-chat`
  liegt auf Yuls Kiste bereits neben `ministral-3:8b` in Ollama.
  Die Läufe selbst liegen in `logs/evals/` und sind **gitignored** — wer die
  Referenz braucht, findet hier die Zahl und fährt sonst neu. Nebenbei
  bestätigte der Dreierlauf #41a: Ø streute 3,2 %, die Quote 20 %
- **Judge-Bias: die Annahme hat sich nicht bestätigt.** Erwartet wurde, dass ein
  sich selbst bewertendes Modell zu nachsichtig ist. Ein fremder Judge
  (`qwen2.5:7b` statt `ministral-3:8b`) liefert Ø 3,71 — mitten in der Spanne der
  Selbstbewertungen. Damit ist der Bias für dieses Paar **nicht belegt**; für
  einen deutlich stärkeren Judge ist er weiterhin plausibel und ungemessen (hier
  beurteilte 7B ein 8B). Der Vergleich zweier Läufe mit gleichem Judge bleibt
  trotzdem die saubere Form (`report.csv`)
- Der Guard-Red-Team-Korpus läuft ohne Modell als parametrisierter Test in der CI mit
  (`tests/test_guard_redteam.py`) — Angriffsmuster gehören in `evals/guard_redteam.yaml`
- Korpus-Loader ist streng: unbekannte Keys, kaputte Regexe, doppelte IDs und
  erwartungslose Fälle fliegen beim Laden raus
- `known_gap: true` markiert eine dokumentierte Guard-Schwäche (gemeldet, kein
  Fehlschlag); ein Gegentest schlägt an, sobald die Lücke geschlossen ist. Genau
  so ist #62 abgenommen worden: `ctx_code_snippet_in_article_is_kept` fing an zu
  bestehen, also musste das Flag fallen. `KNOWN_GAP_IDS` in
  `tests/test_evals_cli.py` war danach leer und trug seit der ZIM-Messung
  (2026-08-07) wieder sechs Einträge. Seit #91 (2026-11-10) ist es **einer**: die
  fünf wirksamen Lücken haben Regeln, übrig ist der Fehlalarm
  `ok_article_quoting_an_injection` — siehe [guard.md](guard.md); der Test hält Korpus und Liste deckungsgleich
  und schlägt in beide Richtungen an
- **Der Judge-Parser liest Markdown mit, aber nicht mehr (#71):** ein reales 8B-Modell
  antwortet `1: **5** | …` statt `1: 5 | …` — formattreu, nur fett. Vorher wurde daraus
  `score=None`, also ein Durchfaller trotz sauberer Bewertung; ein Baseline-Lauf hätte
  lauter Nullen gemessen. `_SCORE_LINE` erlaubt jetzt Auszeichnung *um* die beiden
  Zahlen (`**`, `__`, Backticks, Aufzählungszeichen, `Punktzahl:`, `5/5`) — die Zeile
  muss aber weiter mit der Erwartungsnummer beginnen und die Punktzahl eine einzelne
  1–5 sein. Jede Lockerung braucht die Gegenprobe, dass Ziffern im Fließtext weiterhin
  `None` ergeben; `unscored` ist die einzige Schranke gegen einen stumm durchgewinkten
  Judge
- `expect.rule` nennt die Regel, die einen Guard-Fall fangen *soll* (#62). Nur
  `reason` zu prüfen reicht nicht: ein Fall, der von der falschen Regel gefangen
  wird, sieht sonst aus wie ein Erfolg

### Ein Messlauf misst das Modell — nicht den Ausfall, und er hinterlässt nichts (#95)

Zwei Befunde aus dem zweiten Durchgang der Fehlersuche, beide an der Naht
zwischen Eval-Suite und dem Antwortweg, den sie benutzt:

- **Der Fehlertext des Backends ist kein Fall.** `stream()` fängt
  Backend-Fehler und liefert `LLM_ERROR_MESSAGE` als Text aus. Der Runner hielt
  das für eine Antwort: Checks rot, Judge-Note 1, Ø-Score des Laufs gedrückt —
  ausgerechnet die Zahl, über die verglichen wird. `_run_case` erkennt den Text
  jetzt und meldet einen Fehler; der Fall fehlt im Durchschnitt, statt ihn zu
  verfälschen. Die Stoppuhr kennt dieselbe Regel („eine Fehlermeldung ist keine
  Bestzeit"). **Ein älterer Lauf mit Aussetzern hat einen zu niedrigen Ø** —
  im Zweifel neu fahren, nicht vergleichen.
- **Der Lauf zeichnet nicht auf.** Die Fragen gehen über den One-Shot-Provider
  (damit Guard und Wiki wie im Betrieb mitlaufen), und der schreibt in die
  Ablage. Mit aktiver Ablage standen nach jedem Lauf sämtliche Korpusfragen als
  Gespräche von `local` im Verlauf. `evals/cli.py` schaltet `storage.enabled`
  für den Prozess ab.

### Die Nähte, die keinen Test hatten (#96)

Drei Stellen standen nach den Fehlersuchen #87/#95 in den PRs unter „Nicht
geprüft", obwohl kein fehlendes Werkzeug schuld war — sie waren schlicht nicht
testbar gebaut:

- **Der echte Start.** `launch.main()` ist die Stelle, an der Config, Factory,
  Anmeldung und Oberfläche zusammenkommen, und hatte keinen Test.
  `tests/test_launch_start.py` startet `python src/launch.py` als Prozess mit
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
