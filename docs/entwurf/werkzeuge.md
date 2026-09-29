# Werkzeuge, CI und Pinning

Code-Stil, mypy-Abbruch, import-linter, `make check`, CI-Jobs, Versions-Pins, Audit-Job und die PATH-Shadowing-Falle in allen Fassungen.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Code-Stil

- **Black** mit `line-length = 88`
- **Ruff** Regeln: E, F, I (Imports), UP (pyupgrade), ISC
- `make format` → Black + Ruff-Fix
- `make lint` → Ruff check only
- Keine Docstrings für einfache Methoden, kurze Inline-Kommentare nur wenn nötig

### ⚠️ Ein Prüfer, der abbricht, meldet *weniger* Fehler — nicht keine

mypy lief lange über drei Module. Ein Lauf über `src/ui` meldete genau **einen**
Fehler, und zwar diesen: „Source file found twice under different module names",
mit dem Zusatz `errors prevented further checking`. Die Zahl 1 war kein
Qualitätsurteil, sondern ein **Abbruch** — nach der ersten Meldung hat mypy
aufgehört zu schauen. Tatsächlich waren es 46.

Ursache ist `mypy_path = "src"` in Kombination mit den Importen des Projekts
(`from ui.session import …`): `src/ui/webui_format.py` ist damit auf zwei Wegen
erreichbar, als `webui_format` und als `ui.webui_format`. mypy weigert sich
dann weiterzuarbeiten. `explicit_package_bases = true` sagt ihm, wo die
Paketwurzel liegt.

**Die Lehre ist allgemeiner als mypy:** eine niedrige Fehlerzahl kann bedeuten,
dass wenig kaputt ist — oder dass wenig geprüft wurde. Dieselbe Klasse wie der
immer-rote Audit-Job (#61), nur andersherum: dort war die Farbe wertlos, weil
sie sich nie änderte, hier war die Zahl wertlos, weil sie nicht zu Ende gezählt
wurde. Wer ein Prüfwerkzeug einhängt, sieht **einmal** nach, wie viele Dateien
es tatsächlich angefasst hat (`checked N source files`).

**`--platform win32` ist kein Luxus.** mypy wertet `if sys.platform == "win32"`
statisch aus: auf dem Linux-Runner ist der `winsound`-Zweig toter Code und wird
nie geprüft. Bei einem Windows-primären Projekt ist das die falsche Richtung —
die Tests haben seit #45 eine Windows-Matrix, die Typprüfung hatte keine. Der
zweite Lauf braucht keinen Windows-Runner, nur die Annahme, und hat sofort einen
Befund geliefert, den der Linux-Lauf nie sehen konnte (typeshed gibt
`SND_FILENAME` als `Literal[131072]`, das folgende `|=` macht ein `int` daraus).

Was dabei **nicht** passieren darf: eine Prüfung abschalten, damit die Zahl
sinkt. Alle 55 Befunde sind behoben, nicht stummgeschaltet; wo ein `cast` steht
(Mail-Adapter) oder ein `Any` (`WebUI.texts`), steht die Begründung daneben —
ein `Any` ohne Grund ist ein Stummschalter, genau wie ein Allowlist-Eintrag
ohne Grund.

### Schichten sind ein Vertrag, keine Absichtserklärung (import-linter)

CLAUDE.md sagt seit langem in Prosa, was wohin gehört. Ein Import, der das
verletzt, fällt trotzdem niemandem auf — er funktioniert ja. `lint-imports`
(Verträge in `pyproject.toml` unter `[tool.importlinter]`) macht daraus einen
roten Job, der den konkreten Pfad nennt, inklusive der indirekten:
`wiki.lookup -> security.tinyguard -> ui.session`.

Fünf Verträge, jeder mit einem Grund:

| Vertrag | Warum |
|---|---|
| Der Guard hängt an nichts außer der Config | Er wird von Wiki, RSS, Streamer und API gerufen. Eine Regel, die ihren Aufrufer kennt, ist keine Regel mehr |
| Die Konfiguration kennt niemanden | Sonst wird jeder Start eine Frage der Import-Reihenfolge |
| Oberflächen liegen oben | Drei benannte Ausnahmen: die AppFactory *baut* UI, WebUI und One-Shot-Provider |
| Wiki weiß nichts von RSS (und umgekehrt) | Zwei Kontextquellen; sonst wandert die Guard-Regel der einen in die andere und gilt bald nur halb |

**Bewusst `forbidden`-Verträge statt strenger Schichtung.** Die echten
Aufwärts-Abhängigkeiten sind damit *benannte* Ausnahmen mit Begründung
(`core.factory -> ui.web_ui` und zwei weitere), statt die Schichtung unmöglich
zu machen. Der Wert liegt genau darin: eine **vierte** solche Abhängigkeit fällt
auf, statt sich stillschweigend anzuschließen.

Zwei Dinge, die beim Einbau aufgefallen sind:

1. **Der Linter sieht, was `grep` nicht sieht.** Beim ersten Lauf fand er zwei
   Importe, die in keiner Dateikopf-Suche auftauchen: **verzögerte Importe
   innerhalb von Funktionen** (`security.tinyguard` holt sich lazy die
   Config-Texte, `core.factory` den One-Shot-Provider). Beide sind legitim und
   im Code begründet — aber ein Vertrag, der nur die Dateiköpfe kennt, hätte
   sie nie gesehen.
2. **Eine Mutationsprobe, die nicht greift, sieht aus wie ein blindes Gate.**
   Mein erster Versuch, einen verbotenen Import einzuschleusen, blieb grün — ich
   hätte fast auf „der Linter prüft gar nichts" geschlossen. Tatsächlich hatte
   mein `replace` die Importzeile nicht getroffen, die Mutation war nie im
   Code. **Vor dem Schluss „das Gate ist blind" also nachsehen, ob die Mutation
   überhaupt drinsteht.** Richtig eingesetzt schlug der Vertrag sofort an.

### `make check` — ein Kommando vor dem Push

`make check` fährt `lint`, `lint-imports`, `types` und `test` nacheinander und
stoppt beim ersten Fehler; die Reihenfolge ist nach Laufzeit sortiert, damit das
Billige zuerst fehlschlägt. Bewusst **ohne** `audit` (braucht Netz) und ohne
`test-browser` (braucht einen Browser-Build) — beides läuft getrennt, und ein
Ziel, das ohne Netz fehlschlägt, würde bald umgangen.

### CI-Jobs (`.github/workflows/ci.yml`)
| Job | Was er prüft |
|---|---|
| **Format, lint & Schichten** | `black --check` + `ruff check`, beide als Modul (PATH-Falle unten), dazu `lint-imports` — die Schichtenverträge (siehe unten). Statische Prüfungen, alle in Sekunden |
| **Tests (3 Jobs)** | Volle Suite ohne `ollama`-Marker. Zwei Achsen, **kein** Kreuzprodukt: Ubuntu+Windows auf 3.10 (die versprochene Untergrenze — das Projekt läuft Windows-primär, Pfad-/`winsound`-Probleme fielen auf reinem Linux nie auf, #45) plus Ubuntu auf 3.13 (die neueste Fassung, #64e). Coverage nur im ersten Job |
| **Typen (mypy)** | `python -m mypy` — blockierend über das **ganze** `src` (Konfiguration in `pyproject.toml`). Dazu ein zweiter Lauf `--platform win32`: mypy wertet `sys.platform` statisch aus, der `winsound`-Zweig wäre auf dem Linux-Runner sonst ungeprüfter toter Code |
| **Tests mit spaCy-Modell** | `de_core_news_lg` per `actions/cache` (versionierter Key), dann gezielt `test_spacy_keywords.py` + `test_wiki.py` — die liefen sonst nur als Skips |

Coverage steht als Zahl in der Job-Summary (kein externer Badge-Dienst, der
Account + Token bräuchte). mypy läuft seit #52 blockierend, seit dieser Runde über das
gesamte `src`; `make types` ist die lokale Kurzform und fährt beide Läufe.

### Pre-commit / Versions-Pinning (wichtig!)
CI (`.github/workflows/ci.yml`) prüft `black --check .` + `ruff check .`. **Black/Ruff
sind in `requirements-dev.txt` gepinnt** (aktuell `black==24.4.2`, `ruff==0.16.1`) —
exakt dieselben Versionen in `.pre-commit-config.yaml`. Eine **abweichende lokale
Black-Version formatiert anders und lässt die CI fehlschlagen.** Daher:

```bash
pip install -r requirements-dev.txt   # gepinnte Tool-Versionen ins venv
pre-commit install                    # Hook aktivieren (einmalig pro Clone)
```

Danach formatiert jeder Commit automatisch mit der CI-Version (Hook läuft isoliert,
unabhängig von sonstigen venv-Versionen). Tool-Versionen nur bewusst und **synchron**
in `requirements-dev.txt` **und** `.pre-commit-config.yaml` ändern.

#### Der Audit-Job ist grün für Bekanntes und rot für Neues (#61)
`scripts/audit_deps.py` (lokal `make audit`) hält `pip-audit` gegen
`audit_allowlist.yaml`. Nacktes `pip-audit` stünde dauerhaft rot: Gradio 5.50
deckelt `pillow<12.0` und `starlette<1.0`, die behobenen Fassungen liegen
darüber und sind innerhalb von 5.x nicht erreichbar. **Ein Job, der immer rot
ist, wird ignoriert** — und entwertet dabei die Farbe der übrigen Jobs mit.
Genau das war der erste Anlauf: `continue-on-error` hält den Workflow grün,
die Kachel am PR bleibt trotzdem rot.

Der Abgleich schlägt in **beide** Richtungen an, wie `known_gap` im
Guard-Korpus: ein Befund, der nicht in der Liste steht, ist rot (er braucht
eine Entscheidung); ein Eintrag, den pip-audit nicht mehr meldet, ist ebenfalls
rot (er ist erledigt und muss raus, sonst trägt die Liste bald Altlasten statt
Beschlüsse). **Wer einen Eintrag ergänzt, schreibt die Begründung dazu und was
ihn auflöst** — ein Eintrag ohne Grund ist ein Stummschalter, und
`test_audit_deps.py` besteht darauf.

Nebenbefund, der die ganze Liste erklärte: **alle 30 getragenen Befunde hingen
an Gradios eigenen Deckeln** (`pillow<12.0`, `starlette<1.0`). Mit dem Sprung
auf Gradio 6.22 (#61a) sind sie sämtlich weg — auch PYSEC-2026-211, für das es
unter 5.x gar keine Fassung gab. **Die Liste ist jetzt leer**, und der Abgleich
hat das selbst eingefordert: stehengebliebene Einträge sind rot.

#### ⚠️ Zweite Fassung derselben Falle: ein Werkzeug als Laufzeit-Abhängigkeit
`gradio` führt **`ruff` als eigene Abhängigkeit** und fordert `>=0.9.3`. Der Pin
`ruff==0.4.10` war damit unerfüllbar — und `pip install` sagt das nicht
deutlich, sondern zieht eine passende Version über den Pin. Lokal lief plötzlich
0.16.1 gegen eine Konfiguration, die für 0.4 geschrieben war, und meldete zehn
Befunde in Dateien, die niemand angefasst hatte.

Merksatz: **wenn ein gepinntes Werkzeug plötzlich anders urteilt, zuerst
`python -m <tool> --version` gegen den Pin halten** — nicht die Meldungen
einzeln erklären wollen. Die Ursache ist die Version, in beiden Fassungen: über
den PATH (unten) oder über die Abhängigkeiten (hier).

#### ⚠️ Bekannte Falle: PATH-Shadowing (ist schon mehrfach passiert!)
Black/Ruff **immer als Modul aufrufen**, nie als nacktes Binary:

```bash
python -m black .        # statt: black .
python -m ruff check .   # statt: ruff check .
```

Grund: In Sandboxes/CI-Runnern/Systemen liegt oft ein **anderes, neueres Black
im PATH** (z. B. `/root/.local/bin/black`), das das pip-installierte, gepinnte
24.4.2 verdeckt. Neuere Black-Versionen formatieren Multiline-Strings anders
("hugging" von `gr.HTML("""…""")`) → lokal sieht alles sauber aus, aber
`black --check .` in der CI schlägt fehl. Vor dem Formatieren im Zweifel
`python -m black --version` gegen den Pin in `requirements-dev.txt` prüfen
(`black --version` zeigt ggf. das falsche PATH-Binary!). Das Makefile ruft
bewusst `python -m black`/`python -m ruff` auf.

**Dritte Fassung derselben Falle, gleiche Woche: `pytest`.** Der Makefile rief
Black, Ruff und mypy längst als Modul auf — `pytest` aber nackt. Beim Bau von
`make check` fiel es sofort auf: `ModuleNotFoundError: No module named
'requests'`, während `python -c "import requests"` daneben anstandslos lief. Ein
`pytest` im PATH kann auf einen **anderen Interpreter** zeigen als `python`;
dann fehlen plötzlich Pakete, die installiert sind. Alle Testziele rufen
deshalb jetzt `python -m pytest`.

**Und eine vierte Fassung, die keine PATH-Falle ist, aber dieselbe Form hat:
lokal installiert ≠ in der CI installiert.** Der mypy-Job installierte nur
`requirements-dev.txt`; solange nur `src/core` geprüft wurde, genügte das. Mit
dem erweiterten Prüfbereich meldete er 12-mal `import-not-found` statt zu
prüfen — lokal war alles grün, weil hier alles installiert ist. Merksatz: **wer
einen CI-Job ändert, stellt seine Installationsmenge nach, nicht nur sein
Kommando** (ein `python -m venv` und zwei `pip install` reichen).
