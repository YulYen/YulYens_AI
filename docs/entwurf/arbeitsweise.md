# Arbeitsweise, Doku-Pflicht und Sandbox

Wie hier gearbeitet wird und warum: Branches, Doku-Durchsicht, die Ausnahme für Prosa direkt auf `main`, was in der Sandbox fehlt.

## Arbeitsweise: jeder Branch frisch von `main`

**Immer `git fetch origin main` und den neuen Branch von dort abzweigen** — nie
vom Stand des vorherigen Tickets, auch nicht, wenn dessen PR „gleich gemergt
wird". Zwei Zweige, die nacheinander entstehen, hängen sonst beide eine Zeile an
dieselbe Stelle in `backlog_archiv.md` (oben ins Archiv), und der zweite bekommt
einen Konflikt, sobald der erste drin ist. Genau so passiert, deshalb steht es
hier — der Split von Backlog und Archiv (2026-08-06) nimmt dem Fall nichts,
zwei erledigte Tickets hängen weiterhin beide oben in dieselbe Datei:

```bash
git fetch origin main
git checkout -b claude/<thema> origin/main
```

Ist ein PR bereits gemergt, wird er nicht weiterbenutzt — neue Arbeit heißt
neuer Branch von `main`.

## Doku gehört zur Änderung, nicht danach

**Vor dem Commit wird geprüft, was die Änderung an Doku veraltet — nicht auf
Nachfrage.** Der Anlass steht als Test da: `make test` bekam ein `not browser`
dazu, die Doku behielt ihr altes Kommando samt der Zeile „entspricht: make
test". Wer sie kopierte, zog sich Playwright-Tests herein. Aufgefallen ist das
erst, als jemand nachfragte.

Die Durchsicht dauert eine Minute und geht immer gleich:

| Was geändert wurde | Wo es nachgezogen werden muss |
|---|---|
| Makefile-Ziel, Testkommando, Marker | `docs/{de,en}/ReadMe.md`, `CONTRIBUTING.md` |
| Config-Schalter | beide ReadMes (Schalterliste) + `config.yaml`-Kommentar |
| Nutzerseitiges Verhalten | `docs/{de,en}/Features.md` **und** `CHANGELOG.md` unter `## [Unreleased]` |
| Entwurfsentscheidung, Stolperfalle | der passende Bereich in `docs/entwurf/`; eine Zeile in `CLAUDE.md` nur, wenn sie ohne Nachschlagen umfiele (siehe dort, „Wohin neue Regeln gehören") |
| Ticketstand | `backlog.md`; Erledigtes wandert nach `backlog_archiv.md` |
| Abhängigkeits-Pin | `requirements*.txt`-Kommentar; bei Bedarf `.pre-commit-config.yaml` |

**`tests/test_docs_consistency.py` nimmt davon den mechanischen Teil ab:** jedes
`pytest`-Kommando in der lebenden Doku muss eines sein, das der Makefile auch
benutzt, und jedes Makefile-Ziel steht in der Doku oder mit Begründung auf der
Ausnahmeliste. Beides schlägt in beide Richtungen an, wie `known_gap` im
Guard-Korpus.

**Was der Test nicht kann, ist der größere Teil.** Ob ein Absatz noch stimmt,
sagt kein `assert` — nur, ob ein Kommando noch existiert. Die englische Fassung
ist außerdem eine Übersetzung: ändert sich die deutsche, ändert sich beide.

**Datierte Berichte werden nicht nachgezogen.**
`docs/modellwechsel_juni_2026.md` hält fest, was *damals* mit welcher
Begründung entschieden wurde — warum `ministral-3:8b` und nicht LeoLM 13B, was
8 GB VRAM zulassen. Den Inhalt anzupassen fälscht die Aufzeichnung; ist eine
Aussage überholt, kommt ein datierter Hinweis davor. Der Test lässt die Datei
deshalb ausdrücklich aus (`LIVING_DOCS`).

**Aber ein Bericht ist nicht automatisch erhaltenswert.** Nebenan lag
`framework_update_juni_2026.md` und protokollierte einen Routine-Bump zweier
Patch-Versionen. Das ist ein *Arbeitsprotokoll*, keine Entscheidung: die zwei
Versionen waren überholt, alle vier dort festgehaltenen „bewusst nicht
geändert"-Beschlüsse inzwischen umgekehrt, die einzige dauerhaft nützliche
Zeile stand ohnehin hier — und **verlinkt hat ihn niemand**. Ein Dokument,
dessen sämtliche Aussagen falsch sind und auf das nichts zeigt, ist keine
Aufzeichnung, sondern Altlast; es ist gelöscht. Die Frage vor dem Hinweis
lautet also: hält das hier eine *Entscheidung* fest, oder nur, dass jemand
gearbeitet hat? `modellwechsel` besteht diese Probe (drei lebende Dokumente
verlinken darauf), `framework_update` nicht.

### Ausnahme: Prosa ohne Code darf direkt auf `main`

Eine übersichtliche Änderung, die **keinen Code anfasst** — ein Backlog-Ticket,
eine Zeile Doku, ein korrigierter Tippfehler, derselbe falsche Pfad in vier
Dateien — geht ohne Branch und ohne PR direkt auf `main`. Ein Review-Prozess
für eine Zeile Prosa kostet mehr Aufmerksamkeit, als er einbringt.

**Bis zum 2026-08-25 stand hier „genau eine Datei", und die Zahl war der
falsche Maßstab.** Der Anlass: `feedback_votes.jsonl` war von `logs/` nach
`data/` gezogen, vier beschreibende Dokumente nannten weiter den alten Ort.
Vier Dateien, je eine Zeile, viermal dieselbe Ersetzung — ein Branch, ein PR
und eine Beschreibung für etwas, das ein `grep` in einer Sekunde abnimmt.
Umgekehrt wäre eine **einzelne** Datei, in der ein ganzer Abschnitt neu
geschrieben wird, einen PR wert gewesen. Die Dateizahl war ein Stellvertreter
für „klein", und ein schlechter.

Der Maßstab sind stattdessen zwei Fragen, beide mit Nein zu beantworten:

1. **Ist Code betroffen?** Dann PR — dort sieht man die Änderung als Ganzes,
   und dort laufen Linter, Typen und Tests, bevor sie auf `main` liegt.
   `config.yaml`, Ensemble-YAML und Locale-Dateien zählen als Code: sie ändern
   das Verhalten der laufenden App.
2. **Braucht es einen `CHANGELOG.md`-Eintrag?** Dann merkt es jemand beim
   Betreiben — und was der Betreiber merkt, verdient den Blick von außen.

Sonst gilt: lässt sich die Änderung in *einem* Satz sagen und nachprüfen, geht
sie direkt. Ein Übersetzungspaar (`docs/{de,en}/…`) ist dabei **eine**
Änderung, keine zwei; die beiden Fassungen gehören ohnehin zusammen.

Im Zweifel Branch — die Ausnahme ist für den offensichtlichen Fall gedacht,
nicht für den grenzwertigen.

## Wo diese Sitzung läuft — und was dort fehlt

Claude läuft mal in einer **Sandbox** (Claude Code im Web), mal auf **Yuls
Rechner**. Der Unterschied ist keine Randnotiz: in der Sandbox fehlt fast alles,
was das Projekt zur Laufzeit braucht.

Die Tabelle dazu steht in `CLAUDE.md` — sie gehört dorthin, wo sie in jeder
Sitzung gelesen wird.

Ihre letzte Zeile ist die überraschendste: ein Tag lässt sich aus der Sandbox
nicht setzen. Das geht über die Releases-Oberfläche (siehe [versionierung.md](versionierung.md)) oder von Hand.

**Die ersten beiden Zeilen erledigt ein Hook**
(`.claude/hooks/session-start.sh`, registriert in `.claude/settings.json`): er
installiert die Abhängigkeiten und macht den Clone tief. Drei Entwurfspunkte,
die man beim Anfassen leicht umdreht:

1. **Er läuft nur remote** (`CLAUDE_CODE_REMOTE`). Auf Yuls Rechner wäre ein
   `pip install` bei jedem Sitzungsstart Lärm und im schlimmsten Fall der
   falsche Interpreter — und flach ist der Clone dort nicht. *Weil* er
   remote-only ist, darf er bash sein und Linux annehmen, obwohl das Projekt
   sonst Windows-primär ist.
2. **Er endet immer mit 0.** Ein Werkzeug, das die Sitzung am Start scheitern
   lässt, ist schlimmer als die Handarbeit, die es ersetzt.
3. **Das spaCy-Modell holt er nicht** (~575 MB). Es schaltet nur Tests frei,
   die sonst sauber übersprungen werden; der Download bei jedem Start wäre der
   schlechtere Tausch.

**`.gitignore` hatte `.claude/`** — der Hook wäre also stumm nicht mitgekommen.
Jetzt steht dort `.claude/*` mit zwei Ausnahmen: aus einem ausgeschlossenen
*Verzeichnis* lassen sich einzelne Dateien nicht zurückholen, git steigt gar
nicht erst hinein. `settings.local.json` bleibt draußen.

Was hier steht, gehört auch in den Abschnitt „Nicht geprüft" der
PR-Vorlage — dort wird danach gefragt, hier steht, was die Antwort ist.

## Das Training läuft nicht in diesem Repo (#7)

`transformers` ist im venv dieses Projekts **nicht importierbar**, und das ist
Absicht, kein Defekt: Gradio 6 verlangt `huggingface_hub>=1.0`, `transformers`
4.43 verlangt `<1.0`. Wer den ImportError „repariert", zieht `hf_hub` unter
Gradio weg und legt damit die Anwendung lahm.

Die LoRA-Strecke lebt in einem **eigenen Repository** (`YY_AI_Trainingground`,
privat) mit eigenem venv und eigenen Pins. Hier gehört nur her, was den
*Vergleich* betrifft: die Eval-Suite (#41) und der Baseline-Wert in
[tests-und-evals.md](tests-und-evals.md).

Der Satz steht hier, weil er sich zweimal aufdrängt — einmal als scheinbar
kaputte Abhängigkeit, einmal als Versuchung, „schnell ein Trainings-venv
daneben" anzulegen. Beim zweiten Mal ist es tatsächlich passiert; die
Umgebung existierte im Schwesterprojekt längst, funktionsfähig und mit
denselben Pins.
