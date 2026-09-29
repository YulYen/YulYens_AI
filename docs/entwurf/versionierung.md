# Versionierung und Changelog (#74)

Wo die Version steht, was ins Changelog gehört, welche Stelle springt, wie getaggt wird.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Versionierung und Changelog (#74)

Die Version steht in **`src/version.py`** und sonst nirgends; `CHANGELOG.md`
trägt sie als oberste Überschrift, `tests/test_version_consistency.py` hält
beide zusammen. Angezeigt wird sie von `--version`, in der Kopfzeile von
`--doctor` und als Feld in `/health` und `/healthz` — ohne Paket und ohne Tag
ist „welcher Stand läuft?" sonst nicht zu beantworten, und das ist die erste
Frage bei jeder Fehlermeldung.

**Baseline ist 2.0.0 (2026-08-05).** Das Changelog beginnt hier; was davor
liegt, steht *nicht* darin — das Backlog-Archiv erzählt es ausführlicher, als
ein Changelog es könnte, und eine zweite Fassung derselben Texte läuft beim
dritten Eintrag auseinander. Warum die Hauptnummer trotzdem springt: der
letzte Tag `v1.1.0` ist vom 2026-01-04, und seither ist der Vertrag mehrfach
gebrochen — `ui.web.host` stand auf `0.0.0.0`, `email_adapter.allowed_senders`
kam als Pflichtfeld dazu, und #72 hat die Aufzeichnung ohne Anmeldung still
abgeschaltet.

### ⚠️ Der Clone in der Sandbox ist flach — `git tag` lügt dort

Der erste Anlauf zu #74 stand auf der Feststellung „es gibt keinerlei
Versionierung: kein Tag, kein `__version__`, 162 Commits". Zwei Drittel davon
waren falsch, und zwar **messbar falsch, nicht strittig**: der Arbeits-Clone ist
`shallow`. `git tag` gab deshalb nichts aus, und `git log --reverse` behauptete,
das Projekt beginne am 2026-07-02. Tatsächlich: **843 Commits seit dem
2025-07-09 und drei Tags** — `v0.9.7-stable-webui`, `v1.0.0` („Erste
öffentliche Veröffentlichung", 2025-11-24) und `v1.1.0`.

Die Folge wäre teuer gewesen: `v1.0.0` ist seit November vergeben, ein Tag mit
diesem Namen hätte die erste öffentliche Veröffentlichung überschrieben.

**Merksatz:** vor jeder Aussage über die Historie — Tags, Alter, Commit-Zahl,
„gab es das schon mal?" — erst `git rev-parse --is-shallow-repository` fragen
und bei `true` `git fetch --unshallow origin`. Das ist dieselbe Klasse wie der
abbrechende mypy-Lauf in [werkzeuge.md](werkzeuge.md): die Zahl war nicht falsch berechnet, sie
war auf einem Ausschnitt berechnet, der wie das Ganze aussah.

### Was hinein gehört — und was nicht

**Nur, was jemand beim Betreiben merkt:** ein neuer Schalter in `config.yaml`,
ein geänderter Default, ein neues Bedienelement, eine entfernte Option, ein
Pflichtfeld. Interner Umbau gehört nicht hinein — #58 (Moderator umgeschrieben)
und #64d (Broadcast-Events) ändern für den Startenden nichts.

Diese Abgrenzung trägt die **Ausnahme für Prosa direkt auf `main`** ([arbeitsweise.md](arbeitsweise.md)) — seit die Dateizahl dort nicht
mehr entscheidet, ist sie sogar direkt eine der beiden Fragen: „braucht es
einen Changelog-Eintrag?" heißt „merkt es jemand beim Betreiben?" und damit
„gehört ein Blick von außen dazu?". Bräuchte *jede* Änderung eine Zeile, wäre
jede korrigierte Doku-Zeile PR-pflichtig. Die Abgrenzung hält also nicht nur
das Changelog lesbar, sondern auch den kurzen Weg offen.

### Welche Stelle springt

Der öffentliche Vertrag ist: die Keys in `config.yaml`, die Kommandozeile von
`src/launch.py`, die HTTP-Endpunkte und das Ensemble-YAML-Format. Das
Store-Schema gehört **nicht** dazu (dafür gibt es Migrationen), Locale-Keys
auch nicht.

| Stelle | wann |
|---|---|
| MAJOR | der Vertrag bricht — Pflichtfeld, geänderter Default, entfernter Schalter |
| MINOR | Neues, ohne dass Bestehendes bricht |
| PATCH | nur Behobenes |

**Eine stille Verhaltensänderung ist auch ein Bruch.** #72 ist der Beleg: die
Config blieb gültig, aber eine WebUI ohne Anmeldung zeichnete plötzlich nichts
mehr auf. Das ist die teuerste Sorte, weil den Verlust nichts anzeigt — wer sie
unter „Changed" einsortiert, versteckt sie. Eine Deprecation dagegen ist *kein*
Bruch: `briefing:` → `rss:` wird weitergelesen und warnt, das gehört unter
„Changed".

Die Stelle wird **beim Taggen** entschieden, nicht vorher: man liest den
`Unreleased`-Abschnitt und sieht es. Steht dort etwas unter „Breaking", ist es
MAJOR.

### Wer schreibt wann

**Die Zeile kommt im selben PR mit**, unter `## [Unreleased]`. Der Grund ist
nicht Vollständigkeit, sondern Perspektive: später aus den eigenen
Commit-Titeln rekonstruiert, entsteht sie aus der Sicht dessen, der es gebaut
hat — nicht dessen, der es benutzt. Dass die Commits deutsch sind und das
Changelog englisch, ist dabei ein Vorteil: eine Zeile lässt sich nicht
kopieren, ohne zu bemerken, dass `refactor(ui): …` dort nichts verloren hat.

**Getaggt wird, wenn Yul „runder Stand" sagt** — höchstens einmal die Woche,
nicht pro Merge. Der Tag (`v1.2.3`) entsteht, *nachdem* beide Dateien
übereinstimmen; er ist nicht Teil der Testprüfung, weil die CI flach auscheckt.

**Beim Taggen über die Releases-Oberfläche (geht vom Handy) zwei Handgriffe,
die man beide leicht vergisst:**

1. **Den Pre-Release-Haken wegnehmen.** GitHub überspringt Pre-Releases bei
   „latest" — `/releases/latest` antwortet dann **404**, und auf der
   Repo-Startseite steht gar kein Release, obwohl eines da ist. Bei 2.0.0
   genau so passiert: der Release hieß zuerst `v2.0.0-beta` und war markiert.
   Der Name ist der zweite Teil desselben Fehlers — `-beta` ist in SemVer
   keine Verzierung, sondern eine Vorabkennzeichnung, die *vor* `2.0.0`
   sortiert.
2. **„Generate release notes" ersetzen.** Die erzeugte PR-Liste ist die
   Entwicklersicht (bei 2.0.0 siebzig Zeilen, darunter „Codex-generated pull
   request") — also genau das, was laut den Regeln oben *nicht* an den
   Betreiber geht. Der Text ist der Changelog-Eintrag; die Zeile
   `**Full Changelog**: …compare/…` darf unten stehen bleiben, dann ist die
   Liste einen Klick entfernt statt im Weg.

Die Oberfläche legt einen **lightweight** Tag an, die älteren drei sind
annotated. Kein Handlungsbedarf — der Text lebt dann im Release-Objekt statt
im Tag-Objekt; es steht hier nur, damit die Ungleichheit niemanden beunruhigt.

**Der Konflikt-Trap aus [arbeitsweise.md](arbeitsweise.md) gilt hier auch:** zwei Branches hängen beide oben
in dieselbe Datei. Er ist kleiner, weil `Unreleased` in `Breaking`/`Added`/
`Changed`/`Fixed` zerfällt und zwei Branches selten in denselben Abschnitt
schreiben — die Gegenmaßnahme bleibt „jeder Branch frisch von `main`". Ein
Werkzeug dagegen (towncrier mit einer Schnipsel-Datei je Änderung) wäre
Zeremonie für einen Konflikt, den es bei einem Entwickler kaum gibt.

### Zwei Dinge, die man leicht umdreht

**Das Changelog ist englisch, obwohl alles andere hier deutsch ist.** Die
deutsche Ebene richtet sich an den Entwickler (Code-Kommentare, `CLAUDE.md`, `docs/entwurf/`,
`backlog.md`), die englische an den Betreiber — und der ist im Zweifel jemand
anderes. `docs/en/` und der englische README-Teil sind dieselbe Ebene. Wer das
zweisprachig macht, schreibt jeden Eintrag doppelt, für immer, ohne dass ein
Test die Fassungen zusammenhält.

**Veröffentlichte Einträge werden nicht nachgezogen** — dieselbe Regel wie bei
`docs/modellwechsel_juni_2026.md`. Ein Eintrag hält fest, was in *dieser*
Version galt; ihn anzupassen fälscht die Aufzeichnung. Ist eine Aussage
überholt, steht das im nächsten Eintrag. Deshalb steht `CHANGELOG.md` auch
nicht in `LIVING_DOCS` von `tests/test_docs_consistency.py`.
