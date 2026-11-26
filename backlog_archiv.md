# backlog_archiv.md — Erledigtes

Der abgeschlossene Teil von [backlog.md](backlog.md). Neueste Einträge oben;
die `No.`-Spalte ist dieselbe stabile ID wie im Backlog. Ein Ticket, das nur zur
Hälfte fertig ist, wird geteilt: der offene Rest behält die ID drüben, der
erledigte Teil steht hier.

**Einträge werden nicht nachgezogen.** Sie halten fest, was *damals* mit
welcher Begründung entschieden und gemessen wurde; sie anzupassen fälscht die
Aufzeichnung. Ist eine Aussage überholt, steht das im neueren Eintrag.

## Bis 3.0.0: nur der Index — der Text liegt im Tag

Bis 3.0.0 war diese Datei auf 143 KB gewachsen, mehr als die ganze
Entwurfsdoku zusammen, und wurde fast nur noch per Suche gelesen. Die vollen
Einträge stehen unverändert im Stand `v3.0.0`; hier steht, welches Ticket
wann erledigt wurde. Die Begründung eines Tickets, etwa #62:

```bash
git show v3.0.0:backlog_archiv.md | grep "^| 62 |"
```

Im Browser:
[`v3.0.0/backlog_archiv.md`](https://github.com/YulYen/YulYens_AI/blob/v3.0.0/backlog_archiv.md),
dort nach `| 62 |` suchen. Was davon heute noch als Regel gilt, steht ohnehin
in `docs/entwurf/` — die Archiv-Einträge sind das *Wie es dazu kam*.

In der Sandbox braucht `git show v3.0.0:…` den tiefen Clone; den holt der
Session-Hook.

## Erledigt seit 3.0.0

| No. | Name | Description | Category |
| --- | --- | --- | --- |
| 103 | Testsuite durchgesehen: doppelt, zersplittert, Positionszugriffe | **DONE (2026-11-26).** Yuls Frage: kann etwas weg, weil unnütz oder doppelt? **Gemessen statt geraten:** Laufzeit (kein Problem: 25 s, der langsamste Test 3,3 s), eine AST-Analyse aller 841 Testfunktionen (ohne Prüfung, identischer Körper, Dauer-Skips) und Coverage pro Test (`--cov-context=test`): welche Testpaare laufen durch nahezu dieselben Zeilen (Jaccard ≥ 0,985 — 254 Paare, 16 dateiübergreifend), die dann gelesen wurden. **Befund: die Suite ist schlank.** Gelöscht bzw. zusammengelegt: eine echte Doublette (`test_the_shipped_config_passes` ≡ `test_every_section_of_the_shipped_config_is_modelled`, wörtlich derselbe Körper); drei Factory-Tests in zwei Dateien, die dieselbe Factory mit je anderen Guard-Schaltern bauten, zu einem; zwei Alias-Tests des abgeschalteten Guards zu einem parametrisierten; acht Reset-Tests, die je ein Teilstück desselben `_reset_ui_updates()` prüften, zu einem. **Der eigentliche Fund** sind sechs weitere Tests, die per Zahl auf Gradio-Ausgaben zugriffen (`updates[28]` fürs Mikro): jetzt per Name über `_named()`, Regel in `docs/entwurf/tests.md`. Beide Zusammenlegungen per Mutation geprüft (Mikro nicht ausgeblendet, `wrongdoing_lock_turns` verschluckt → je rot). **Gegenprobe:** Gesamtabdeckung vorher und nachher identisch (5789 Anweisungen, 672 offen, 88 %). 1253 → 1243 Tests. **Nicht gelöscht, obwohl verdächtig:** 553 der 763 Testfunktionen decken keine eigene Zeile ab — Coverage misst, was läuft, nicht was geprüft wird; die gelesenen Paare prüften fast alle Verschiedenes (Normal- gegen Randfall, Liveness gegen Inhalt von `/health`, *dass* die API aufzeichnet gegen *was*). Ebenso die als „ohne Prüfung" gemeldeten Browser-Tests (sie prüfen mit Playwrights `expect`) und der einzige Dauer-Skip (Wiki gegen echtes Kiwix — läuft auf Yuls Kiste). | Quality |
| 102 | Alte Zöpfe abgeschnitten | **DONE (2026-11-26).** Der zweite Teil von Yuls Idee nach dem Lab-Umzug (#101): was keine Entscheidung mehr trägt, aus `main` heraus — der Tag `v3.0.0` ist das Backup. **Tote Dateien:** `modelfiles/` (Modelfiles für Leo, Mistral 7B, Qwen 2.5, GPT-OSS — kein Verweis), `examples/` (Terminal-Config für ein 7B, Bild-Helfer — kein Verweis), `static/unnuetzes/` (eine Kurzgeschichte), ein getracktes `logs/.gitkeep` unter einem ignorierten `logs/` (die App legt den Ordner selbst an). **Kompatibilitätspfade, die ein Major abschneiden darf:** `briefing:` als Alias für `rss:` (#73) ist weg und gilt als unbekannte Sektion. `ui.web.share_auth` (#53) war ein Rückfall-Login; ihn einfach zu streichen hätte eine Installation, die nur das kennt, nach dem Update **still ohne Anmeldung** laufen lassen — die Klasse aus #89. Deshalb bricht ein `share_auth` den Start jetzt ab (Exit 4, Meldung nennt `ui.web.auth`; geprüft per echtem Start). **Bewusst geblieben:** der Umzug der Votes von `logs/` nach `data/` (`adopt_legacy_votes`). Die anderen Pfade schützen Config, dieser schützt Daten, die sich nicht wiederholen lassen — `logs/` gilt als wegwerfbar, ein liegengebliebenes Vote-Log dort ginge beim nächsten Aufräumen verloren. Er fliegt, sobald Yul bestätigt, dass `data/feedback_votes.jsonl` auf seiner Kiste existiert. **Dieses Archiv:** 143 KB, mehr als die ganze Entwurfsdoku, fast nur per Suche gelesen. Bis 3.0.0 steht hier nur noch ein Index (Nummer, Name, Datum, Kategorie); der Text liegt unverändert im Tag, der Abrufweg steht oben. Was davon als Regel gilt, stand ohnehin schon in `docs/entwurf/`. **Bewusst nicht angefasst:** die Entwurfsdoku selbst — jede Überschrift dort ist eine Regel mit Begründung, keine Geschichte. Dazu die LoRA-Hinweise aus Features und ReadMe (das Training lebt in `YulYen/YulYens_AI_Training`). | Maintenance |
| 101 | Messen ins Lab ausgelagert | **DONE (2026-11-26).** Yuls Ziel: Getrenntes getrennt, das Orchester dünn. Ins private Repo `YulYen/YulYen_Lab` sind gezogen: Eval-Suite mit Judge, Stoppuhr, Blindverkostung, Injection-Sonde, die Korpora dazu, die zwölf Live-Tests am Modell (alle `@pytest.mark.ollama`), die beiden Modellwechsel-Berichte und die Abschnitte Eval-Suite und Stoppuhr der Entwurfsdoku — **mit ihrer Historie** (`git filter-repo` über die Pfade vor und nach der Umbenennung, 67 Commits). **Die Grenze:** was ein Modell misst, geht; was ohne Modell eine Aussage über den Code macht, bleibt. Deshalb blieb das Guard-Red-Team (`tests/guard_redteam.yaml`, Lader und Auswertung in `tests/guard_corpus.py`): es prüft den Guard, nicht ein Modell, und `KNOWN_GAP_IDS` gehört neben die Regeln. Die Live-Tests gingen, obwohl sie wie Tests aussehen — fünf Wörter, Ostersonntag, Freuds Geburtsort prüfen Modell und Prompt; die Suite hier ist seitdem deterministisch, Marker `ollama`, `ollama_config`, `YULYEN_TEST_MODEL` und `make test-all` fielen weg. **Die Naht:** das Lab installiert das Orchester editierbar aus dem Nachbarordner und importiert es an genau einer Stelle (`orchestra.py` dort, per import-linter erzwungen); `yulyen-ai` steht dort bewusst nicht als pip-Abhängigkeit (der Name ist auf PyPI frei). Dafür hier: `system_prompt_with_date` und `wiki_mode_enabled` ohne Unterstrich, `py.typed`. Das Orchester weiß nichts vom Lab; dessen CI läuft gegen `main` und wöchentlich. **Die Berichte** waren auch Betreiber-Hilfe (README: „welches Modell für meine Karte?") — das Lab ist privat, deshalb steht die Antwort jetzt als Tabelle im README, und Archiv-Links zeigen auf `v3.0.0`. Regel daraus: das Lab misst, das Orchester entscheidet — ändert eine Messung einen Default, steht die Entscheidung hier und muss ohne den privaten Bericht verständlich sein. **Bewusst nicht:** `config.yaml` an `PROJECT_ROOT` verankern. Es lag nahe (das Lab ruft das Orchester aus einem anderen Ordner), hätte aber die App aus jedem Ordner starten lassen, während `logs/` und `data/` — samt Gesprächs-Ablage — weiter im Arbeitsverzeichnis landen: eine still zweite, leere Ablage. Erst alle relativen Pfade, dann der Default. `evals:` in einer `config.local.yaml` ist seitdem ein unbekannter Key (Breaking, Changelog). `docs/entwurf/tests-und-evals.md` heißt `tests.md`; das datierte Testlauf-Protokoll vom 2026-11-13 (Ollama-Tests, kein Verweis darauf) ist weg. | Technical foundation |
| 44 (2a) | Paket `yulyen_ai`: installierbar, ein Namensraum | **DONE (2026-11-26).** Der offene Rest von Teil 2 (uv und Lockfile) bleibt als #44 im Backlog. **Anlass:** das Labor-Repo soll das Orchester importieren; ohne Paket nur über einen Nachbar-Pfad, und ein Editable-Install *ohne* Umbenennen hätte `config`, `core`, `ui`, `api` als Top-Level-Namen in fremde venvs gelegt — auf PyPI gibt es ein Paket `config`. Yuls Vorgabe: „wenig Rücksichtnahme, sauberste Lösung" — er ist praktisch der einzige Betreiber. **Gebaut:** alle Teilpakete unter `src/yulyen_ai/` (117 Dateien, rund 490 Importzeilen, rund 190 Modulpfade in Strings, meist `monkeypatch`-Ziele; die einzige Kollision mit einem Config-Pfad war `"rss.feeds.titel"` in `test_config_schema.py`). `[project]` in `pyproject.toml` mit `dynamic` Version (aus `version.py`) und Abhängigkeiten (aus `requirements.txt`) — keine zweite Liste. Start mit `python -m yulyen_ai`; `src/launch.py` ist ersatzlos weg (Bruch, im Changelog). `yulyen_ai/paths.py` ist die eine Stelle für die Projektwurzel: vorher rechnete jedes Modul selbst mit `parents[n]`, und nach dem Umzug hätte jede dieser Zahlen still auf `src/` gezeigt. Alle `sys.path.insert` in `scripts/`, `PYTHONPATH=src` in Makefile und CI und `pythonpath` in pytest sind weg — wer nicht installiert, bekommt einen klaren `ModuleNotFoundError` statt eines halb funktionierenden Checkouts. import-linter läuft auf `root_package = "yulyen_ai"`, per Mutation geprüft (Guard → core: BROKEN). **Bewusst nicht:** ein Wheel (die Daten liegen neben `src/`, siehe `paths.py`) und ein Konsolenbefehl `yulyen-ai` — der würde suggerieren, die App laufe aus jedem Verzeichnis, aber `config.yaml`, `logs/` und `data/` sind relativ zum Arbeitsverzeichnis. Erst wenn die alle an `PROJECT_ROOT` hängen, lohnt er sich. | Technical foundation |

## Bis 3.0.0 (Index)

| No. | Name | erledigt | Category |
| --- | --- | --- | --- |
| 39 | MCP-Server | 2026-11-21 | Integration/Cool |
| 99 (b–f) | classic auf gemma4:26b nachstimmen, erledigter Teil | 2026-11-21 | Quality |
| 100 (Umbau, Vergleich) | Stärkeren Eval-Judge prüfen, erledigter Teil | 2026-11-21 | Quality |
| 80 | Komplettvergleich: alte gegen neue Config, 8B gegen 14B | 2026-11-08 | Research/Quality |
| 90 | Wiki-Proxy kodiert den Suchbegriff nicht neu | 2026-11-21 | Quality |
| 78 | Neue Modelle auf 16 GB VRAM testen | 2026-11-15 | Research/Quality |
| 81 | Judge kennt das heutige Datum nicht | 2026-11-15 | Quality |
| 98 | Browser-Test: Ask-All und Verlauf | 2026-11-11 | Quality |
| 97 | `web_ui.py`: Ask-All in ein eigenes Modul | 2026-11-11 | Refactoring |
| 96 | Browser-Test in der Sandbox, Tests an den Nähten | 2026-11-11 | Quality |
| 95 | Fehlersuche, zweiter Durchgang (Evals, Event-Verdrahtung) | 2026-11-11 | Quality |
| 88 | Erst der Guard, dann das Netz — auf jedem Weg | 2026-11-11 | Security |
| 89 | Unbekannter Anmelde-Provider bricht den Start ab | 2026-11-11 | Security |
| 83 | kiwix-serve nur auf der konfigurierten Adresse | 2026-11-11 | Security |
| 94 | KI-Doku entschlackt | 2026-11-10 | Docs |
| 93 | `/healthz` hinter dem API-Schlüssel | 2026-11-10 | Security |
| 77 | Ask-All/Self-Talk zeichnen nicht auf | 2026-11-10 | Quality/Docs |
| 92 | Doku gegen Code geprüft | 2026-11-10 | Docs |
| 91 | Guard: die fünf wirksamen Lücken schließen | 2026-11-10 | Security |
| 87 | Fehlersuche über das ganze `src` | 2026-11-10 | Quality |
| 85 | Solo und Orchester: eigenes Modell je Persona | 2026-11-08 | Feature |
| 79 | Python-Untergrenze auf 3.12 heben | 2026-11-02 | Maintenance |
| 49 | Gesprächsarchiv-Volltextsuche | 2026-09-06 | Cool feature |
| 27 | Ask-All-Moderator | 2026-09-05 | Orchestration |
| 42a | Erster Messlauf der Stoppuhr am echten Modell | 2026-08-30 | Performance |
| 42 | Perf-Benchmark-Harness | 2026-08-30 | Performance |
| 75 | Register für die Kontext-Kanäle (Rest von #75) | 2026-08-16 | Technical foundation |
| 60b | Injektions-Probe als wiederholbares Artefakt | 2026-08-07 | Quality/Security |
| 75 | Antwortwege: Ask-All und Self-Talk zeichnen bewusst nicht auf | 2026-08-05 | Technical foundation |
| 64e | CI: Python-Matrix (Teil 2 von #64e) | 2026-08-04 | Quality |
| 56 | `web_ui.py` zerlegen | 2026-08-04 | Technical foundation |
| 61a | Gradio 6.x — der Rest der Sicherheitsstrecke | 2026-08-03 | Security/Maintenance |
| 41a | Baseline-Lauf der Eval-Suite | 2026-08-02 | Research/Quality |
| 61 | Gradio 5.x-Migration | 2026-08-02 | Security/Maintenance |
| 60a | Guard-Regeln nur für abgerufenen Fremdtext | 2026-08-02 | Security |
| 60 | Injizierter Fremdkontext in die `user`-Rolle | 2026-08-02 | Security |
| 63 | Schema rekursiv + Anmeldung fail-closed (aufgeteilt) | 2026-08-01 | Technical foundation |
| 74 | CHANGELOG und Versionierung | 2026-08-05 | Technical foundation |
| 73 | RSS als Kontextquelle statt Briefing-Knopf | 2026-08-02 | Integration/Quality |
| 14 | E-Mail-Adapter härten (war: Restpunkte) | 2026-08-02 | Integration/Security |
| 65 | Vote-Kanal an die Ablage anschliessen | 2026-08-01 | Data |
| 66 | Schema-Pruefung rekursiv (Rest von #63) | 2026-08-01 | Technical foundation |
| 64 | Review-Kleinkram (Sammelticket Runde 2) | 2026-08-01 | Quality |
| 70 | Startseite: Yul-Yen-Fotos von den Funktionskarten nehmen | 2026-08-01 | UX |
| 69 | **BUG: Theme-Wechsel wirft die Sitzung weg** | 2026-08-01 | UX/Bug |
| 71 | Judge-Parser verträgt keine Markdown-Auszeichnung | 2026-08-01 | Quality |
| 72 | Ohne Anmeldung keine Gesprächs-Ablage | 2026-08-01 | Security |
| 62 | Guard-Regelwerk überarbeiten | 2026-08-01 | Security/Quality |
| 67 | Test-Doubles gegen die echte Schnittstelle absichern | 2026-08-01 | Quality |
| 59 | Ablage = Gespräch statt LLM-Aufruf | 2026-08-01 | Technical foundation |
| 58 | `_StreamModerator` neu schreiben | 2026-08-01 | Security/Performance |
| 57 | Review-Befunde Runde 2 (externes Review) | — | **DONE (2026-07-31): externes Review über das ganze Projekt, dann die sieben Befunde umgesetzt, die chirurgisch und ohne echtes Modell abnehmbar sind; der Rest ist als #58–#64 ticketiert, #14 wurde erweitert und hochgestuft.** |
| 55 | Review-Befunde („Oberfellpfleger 4.0") | 2026-07-31 | Technical foundation |
| 51 | WebUI: ~4 s Verzug bis der erste Token im Browser erscheint | 2026-07-30 | Performance |
| 50 | Guard: Braces-Injection nach Leerzeichen | 2026-07-30 | Security |
| 34 | Audio plattformübergreifend | 2026-07-30 | Technology |
| 45 | CI-Ausbau | 2026-07-30 | Technical foundation |
| 37 | OpenAI-kompatible API | 2026-07-30 | Integration |
| 35 | Stream-Steuerung: Stop + Regenerate | 2026-07-30 | UX |
| 41 | Eval-Suite (Charakter, Qualität, Guard) | 2026-07-30 | Quality |
| 6 | Model selection in the UI | 2026-07-07 | UX/Technology |
| 13 | STT MVP | 2026-07-08 | Cool feature |
| 15 | Daily briefing (RSS-Teil) | 2026-07-09 | Cool feature |
| 33 | TTS im WebUI | 2026-07-11 | Cool feature |
| 40 | Feedback-Daumen (V1) | 2026-07-30 | Quality/Data |
| 29 | Spaceship-Crew sichtbar machen | 2026-07-30 | Docs/UX |
| 18 | Wrongdoing guardrail (violence/weaponization) | — | Security/Robustness |
| 19 | Drei-Zeitstempel-Transparenz | — | Quality/Correctness |
| 2 | Web-UI "New conversation" in stream | — | Bugfix |
| 9 | Ask-all (broadcast): WebUI Wiki + Streaming | — | Orchestration |
| 20 | Ask-all results table polish | 2026-07-04 | UX/Technology |
| 5 | Health checks/monitoring | — | Technical foundation |
| 21 | Setup-Doktor / Preflight-Check | — | Technical foundation |
| 22 | Kiwix/ZIM aktualisieren + Anleitung | 2026-07-05 | Integration/Docs |
| 23 | Ask-All: Broadcast parallelisieren | 2026-07-05 | Orchestration/UX |
| 17 | Faster first token | 2026-07-07 | Performance |
| 12 | Karl (context summarizer) | — | Technical foundation |
| 32 | Wiki-Quellen-Transparenz | 2026-07-30 | UX/Trust |
| 32a | Quellen-Anzeige für Ask-All und Terminal | 2026-07-30 | UX/Trust |
| 52 | mypy für src/core | 2026-07-30 | Technical foundation  **Nachtrag (2026-08-04): auf das ganze `src` ausgeweitet.** Der Anlass war ein Fund, der wichtiger ist als die Ausweitung: ein Lauf über `src/ui` meldete genau *einen* Fehler — „Source file found twice under different module names" mit dem Zusatz `errors prevented further checking`. **Die Zahl 1 war kein Qualitätsurteil, sondern ein Abbruch.** Ursache ist `mypy_path = "src"`: damit ist `src/ui/webui_format.py` als `webui_format` *und* als `ui.webui_format` erreichbar. `explicit_package_bases = true` löst es auf, danach waren es 46. Vier Module (`wiki`, `rss`, `security`, `stt`) waren ohne eine Zeile Änderung sauber — nur nie geprüft. Insgesamt 55 Befunde behoben, **ohne** eine Prüfung abzuschalten. Neu ist außerdem ein zweiter Lauf `--platform win32`: mypy wertet `sys.platform` statisch aus, der `winsound`-Zweig war auf dem Linux-Runner ungeprüfter toter Code — bei einem Windows-primären Projekt die falsche Richtung. Der Lauf hat sofort einen Befund geliefert, den Linux nie sehen konnte. |
| 36 | WebUI-Politur | 2026-07-30 | UX |
| 43 | Config-/Ensemble-Validierung | 2026-07-30 | Technical foundation |
| 53 | Identitäts-Naht für die Web-UI | 2026-07-31 | Technical foundation |
| 28 | Gast-Persona (V1) | 2026-07-31 | UX/Cool |
| 54 | Gesprächs-Persistenz statt Logfile-Missbrauch | 2026-07-31 | Technical foundation |
| 25 | Konversations-Management im WebUI | 2026-07-31 | UX |
