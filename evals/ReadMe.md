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

**Den Wiki-Proxy startet der volle Lauf selbst**, wenn `wiki.mode` aktiv ist —
ein separates Fenster braucht es nicht. Kommt er nicht hoch, steht das als
Warnung im Report, statt dass still ohne Wikipedia gemessen wird: zwei Läufe,
die sich nur darin unterscheiden, ob der Proxy lief, sähen sonst wie eine
Modelländerung aus. `--guard-only` startet ihn nicht — dieser Lauf soll ohne
alles auskommen.

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

## Die Leitkennzahl ist der Ø-Score, nicht die Bestehensquote (#41a)

Der Report führt bewusst mit dem **Ø Judge-Score**, und das ist gemessen: sechs
Läufe mit **identischem Code** ergaben 3 bis 6 von 17 bestandenen Fällen
(27 % relative Streuung), aber Ø 3,57 bis 3,79 (**1,9 %**). Der Mittelwert ist
vierzehnmal stabiler.

Die Ursache steht als eigene Zeile im Report: 5 bis 7 der 17 Fälle liegen im
Band **3,0–3,9**, also direkt unter „4 besteht", und kippen an einem
Zehntelpunkt. In der Fälle-Tabelle sind sie mit `~` markiert. Wer Baseline
gegen Adapter (#7) über die Quote vergleicht, misst Münzwürfe.

## Judge-Bias, ausdrücklich

Per Default bewertet dasselbe Modell seine eigenen Antworten. **Absolute Scores
bedeuten wenig**, aussagekräftig ist nur der Vergleich zweier Läufe mit
identischem Judge und identischem Korpus — genau der Fall bei Baseline vs.
LoRA-Adapter. Wer ein zweites lokales Modell hat, setzt `evals.judge_model`
darauf.

**Die naheliegende Vermutung hat sich allerdings nicht bestätigt.** Erwartet
wurde, dass ein sich selbst bewertendes Modell zu nachsichtig ist; gemessen
liefert ein fremder Judge (`qwen2.5:7b` statt `ministral-3:8b`) Ø 3,71 — mitten
in der Spanne der Selbstbewertungen. Für dieses Paar ist der Bias also **nicht
belegt**. Für einen deutlich stärkeren Judge bleibt er plausibel und ungemessen
(hier beurteilte ein 7B-Modell ein 8B-Modell). Der Vergleich mit identischem
Judge ist die saubere Form — nicht, weil der Bias erwiesen wäre, sondern weil
er sich so ohnehin herauskürzt.

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
| `input` | die Frage des Nutzers | `ok`, `reason`, `rule` |
| `output` | die Antwort des Modells | `ok`, `reason`, `rule`, `blocked`, `masked` |
| `context` | abgerufener Fremdtext (Wikipedia-Snippet, RSS-Meldung) | `injected`, `reason`, `rule` |

`context` ist der Kanal, den der Guard lange gar nicht gesehen hat: der Text
stammt aus Quellen, die niemand Zeile für Zeile gelesen hat, und ging bis #60
sogar als `system`-Nachricht in den Prompt — mit mehr Gewicht als die Frage des
Nutzers. Heute steht er als markierter, zitierter `user`-Block dort. **Die
Rollenverschiebung allein wirkt nicht** (am 8B-Modell gemessen: eine im Artikel
versteckte Anweisung wurde in 15 von 15 Fällen befolgt, gleich in welcher
Rolle) — was wirkt, ist der Guard. Dort gelten **andere** Regeln als am
Eingang: verworfen wird nur bei `prompt_injection` und `wrongdoing`; PII ist
ausdrücklich erlaubt, weil Impressen und Kontaktangaben in Artikeln normal
sind. Umgekehrt greifen hier Regeln, die am Eingang fehl am Platz wären — ein
Artikel darf die Persona nicht umdefinieren, der Nutzer schon (Gast-Persona,
Self-Talk).

**`rule` nennt die Regel, die den Fall fangen soll (#62), und ist keine
Zierde.** Nur `reason` zu prüfen reicht nicht: ein Fall, der von der *falschen*
Regel geblockt wird, sähe sonst aus wie ein Erfolg. Genau das kam beim Umbau
heraus — `ctx_weapon_instructions_in_article` wurde nie von der
Anleitungsregel gefangen, sondern von der Bau-Regel davor.

**Wer eine Injection-Regel ergänzt, legt den Satz daneben, den sie *nicht*
treffen darf** (`ok_…`). Ohne diese Gegenprobe ist eine Verschärfung nicht
messbar: die Recall-Seite meldet sich von selbst, die Precision-Seite nie.

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
