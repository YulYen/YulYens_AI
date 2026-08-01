# Eval-Suite (#41)

Messbare Antwort auf die Frage „ist das Modell besser geworden?" — gebraucht
für #7 (LoRA), wo Baseline und Adapter verglichen werden müssen.

Die Korpora liegen hier als YAML, der Code in `src/evals/`. Neue Fälle werden
durch Bearbeiten der YAML-Dateien ergänzt, nicht durch neuen Testcode.

## Starten

```bash
# Voller Lauf (braucht Ollama): Antworten + Checks + Judge + Report
python scripts/run_evals.py -e classic

# Nur der Guard-Red-Team-Korpus — braucht kein Modell, kein Netz
python scripts/run_evals.py -e classic --guard-only

# Ohne Judge (nur deterministische Checks), einzelne Persona
python scripts/run_evals.py -e classic --no-judge --personas PETER
```

Report landet als `report.md` (lesen) und `report.csv` (zwei Läufe
vergleichen) in `logs/evals/`, konfigurierbar über `evals.out_dir`.
Exit-Code 1, wenn etwas fehlgeschlagen ist — damit taugt der Lauf als Gate.

`make evals` ist die Kurzform für den Guard-Teil.

## Was hier liegt

| Datei | Inhalt |
|---|---|
| `personas/*.yaml` | Goldene Fragen pro Persona; eine Datei pro Persona |
| `behaviour/three_timestamps.yaml` | Verhaltensbeweis für die drei Zeitstempel (#19) |
| `karl_summary.yaml` | Qualität der Karl-Zusammenfassungen (#12) |
| `guard_redteam.yaml` | Angriff → erwartetes Guard-Verhalten (#18) |

## Zwei Arten von Erwartung

**`checks`** sind deterministisch und brauchen keinen Judge — sie tragen alles,
was mechanisch prüfbar ist:

```yaml
checks:
  must_match: ["(?i)paris"]      # Regex, muss vorkommen
  must_not_match: ["(?i)gerne"]  # Regex, darf nicht vorkommen
  max_chars: 400
  min_chars: 40
```

In Mustern sind Platzhalter erlaubt, die zur Laufzeit ersetzt werden:
`{today_iso}`, `{today_de}`, `{day}`, `{month_de}`, `{year}`. Nötig für die
Zeitstempel-Fälle, deren erwartete Antwort vom Tag des Laufs abhängt.

**`expect_traits`** sind die Dinge, die kein Regex sieht („klingt sarkastisch",
„erfindet keine Fakten"). Die bewertet der LLM-Judge einzeln von 1 bis 5;
4 und 5 gelten als erfüllt, 3 ist „teilweise" und bewusst kein Bestehen.

Ein Fall ohne `checks` **und** ohne `expect_traits` wird beim Laden abgelehnt —
er würde immer bestehen und falsche Sicherheit erzeugen. Unbekannte Keys
ebenfalls: ein Tippfehler in `expct_traits` soll nicht stillschweigend die
halbe Erwartung verschlucken.

## Judge-Bias, ausdrücklich

Per Default bewertet dasselbe Modell seine eigenen Antworten, und Modelle sind
mit sich selbst nachsichtig. **Absolute Scores bedeuten wenig.** Aussagekräftig
ist nur der Vergleich zweier Läufe mit identischem Judge und identischem
Korpus — genau der Fall bei Baseline vs. LoRA-Adapter. Wer ein zweites lokales
Modell hat, setzt `evals.judge_model` darauf.

Antwortet der Judge nicht im vorgegebenen Format, wird die betroffene
Erwartung als `unscored` geführt — nie als bestanden.

**Formattreue heißt nicht Textgleichheit (#71).** Ein 8B-Modell hält das Format
ein und schreibt trotzdem `1: **5** | …` statt `1: 5 | …`. Der Parser toleriert
deshalb Auszeichnung *um* die beiden Zahlen herum (`**`, `__`, Backticks,
Aufzählungszeichen, `Punktzahl:`, `5/5`), aber nichts darüber hinaus: Die Zeile
muss mit der Nummer der Erwartung beginnen und die Punktzahl eine einzelne 1–5
sein. Wer das Muster weiter aufmacht, legt in `tests/test_evals_runner.py` die
Gegenprobe daneben — sonst wird aus „Insgesamt 5 von 5 Erwartungen erfüllt"
eine Bewertung, und `unscored` verliert seine Bedeutung.

## Guard-Red-Team

Läuft ohne Modell und ist deshalb Teil der normalen Testsuite:
`tests/test_guard_redteam.py` macht aus jedem Fall einen parametrisierten Test.
Neue Angriffsmuster gehören in die YAML.

**Drei Stufen, weil der Guard drei Kanäle hat:**

| `stage` | Was geprüft wird | Erwartung |
|---|---|---|
| `input` | die Frage des Nutzers | `ok`, `reason` |
| `output` | die Antwort des Modells | `ok`, `reason`, `blocked`, `masked` |
| `context` | abgerufener Fremdtext (Wikipedia-Snippet, RSS-Meldung) | `injected`, `reason` |

`context` ist der Kanal, den der Guard lange gar nicht gesehen hat: der Text
geht als **`system`**-Nachricht in den Prompt, also mit mehr Gewicht als die
Frage des Nutzers, und stammt aus Quellen, die niemand Zeile für Zeile gelesen
hat. Dort gelten **andere** Regeln als am Eingang — verworfen wird nur bei
`prompt_injection` und `wrongdoing`; PII ist ausdrücklich erlaubt, weil
Impressen und Kontaktangaben in Artikeln normal sind.

Zwei Sonderfälle im Report:

- **`known_gap: true`** — eine dokumentierte Schwäche. Der Fall sagt, was der
  Guard *sollte*, tut es aber heute nicht; braucht zwingend eine `note` mit
  Begründung. Wird gemeldet, aber nicht als Fehlschlag gezählt. Fängt der Guard
  den Fall irgendwann doch, schlägt `test_known_gaps_are_still_gaps` fehl und
  erinnert daran, das Flag zu entfernen.
- **übersprungen** — der zuständige Schutz ist in `config.yaml` ausgeschaltet
  (z. B. `security.pii_protection: false`). Kein Guard-Fehler, aber eine
  ehrliche Aussage über das laufende Setup: diese Angriffe kämen durch.

## Grenzen

- Der Judge braucht ein erreichbares Modell; ohne Ollama läuft nur
  `--guard-only`.
- Die Persona- und Verhaltensfälle prüfen Stil und Vorgabentreue, nicht
  Faktenwissen im Breiten — dafür wäre ein ganz anderer Korpus nötig.
- Die Zeitstempel-Fälle setzen `core.include_date: true` voraus.
