# Modellwechsel-Analyse — November 2026

Stand: 2026-11-01. Nachfolger von [modellwechsel_juni_2026.md](modellwechsel_juni_2026.md),
der für 8 GB VRAM gilt und als datierter Bericht unverändert bleibt.

Anlass: Yuls neuer Rechner steht früher als geplant da — **RTX 5060 Ti mit 16 GB VRAM**
(448 GB/s), Ryzen 7 8700F, 32 GB DDR5. Bewertungsfokus wie im Juni: **Rollentreue,
Deutsch, Wiki-Nutzung** — dazu neu die Frage, ob PETER zum Coding-Helfer ausgebaut
werden kann, gern mit eigenem Modell pro Persona. Schwächere Rechner sollen weiter
mit `ministral-3:8b` laufen.

Alle Zahlen sind Recherche, **nicht auf Yuls Kiste gemessen**. Das Testen ist Backlog #78.

> **Nachtrag 2026-11-08:** Das 14B ist jetzt auf der Kiste gemessen, gegen das 8B,
> siehe [Messung auf Yuls Kiste](#messung-auf-yuls-kiste-2026-11-08). Die übrigen
> vier Kandidaten sind weiter nur Recherche.

---

## Kurzbefund

- **Bei Mistral gibt es in dieser Größenklasse nichts Neueres als Ministral 3**
  (Version 25.12). „Mistral Small 4" (16.03.2026) ist inzwischen ein MoE mit 119B
  gesamt / 6B aktiv und passt nicht.
- Mistral hat sein eigenes „Mistral Small Creative" (25.12) eingestellt und nennt als
  Ersatz **Ministral 3 8B** — passt zur Beobachtung, dass POPCORN damit wie eine Katze
  am Laptop klingt und nicht wie ein Laiendarsteller im Kostüm.
- Neues in passender Größe kommt von Google (**Gemma 4**, April/Juni 2026) und
  Alibaba (**Qwen 3.6 / 3.8**, April/August 2026; Qwen4-27B angekündigt).
- **MoE-Modelle sind der Hebel für 16 GB:** viel Wissen, wenige aktive Parameter —
  schnell, und ein Teil im RAM tut ihnen weniger weh als dichten Modellen.

---

## Top 5

| # | Modell | Ollama | Download | Rolle | Release |
|---|---|---|---|---|---|
| 1 | Ministral 3 14B Instruct | `ollama pull ministral-3:14b` | 9,1 GB | Nachfolger für alle, v. a. DORIS/POPCORN | Dez 2025 |
| 2 | Gemma 4 26B-A4B (MoE, 4B aktiv) | `ollama pull gemma4:26b` | ~18 GB (teils RAM) | Herausforderer, v. a. LEAH; Allrounder | Apr 2026 |
| 3 | Qwen3.6-35B-A3B (MoE, 3B aktiv) | `ollama pull qwen3.6:35b-a3b` | ~23 GB (teils RAM) | PETER als Coding-Turbo | Apr 2026 |
| 4 | Qwen3.8-27B (dicht) | `ollama pull qwen3.8:27b` | 18 GB (teils RAM) | der Denker / Eval-Judge | 14.08.2026 |
| 5 | Devstral Small 2 24B | `ollama pull devstral-small-2:24b` | ~15 GB (knapp) | PETER-Coder mit Mistral-DNA | 09.12.2025 |

Zusammen ~83 GB, bei 100 Mbit/s knapp zwei Stunden. Reihenfolge: 1 → 2 → 3.

### 1. Ministral 3 14B — die sichere Bank

- Gleiche „Schauspielschule" wie das 8B, mehr Hirn. Mistral-Model-Card (Instruct):
  Arena Hard 0,551 statt 0,509, WildBench 68,5 statt 66,8; laut Mistral vergleichbar
  mit Mistral Small 3.2 24B; folgt System-Prompts eng.
- Q4_K_M 7,67 GiB, passt komplett in den VRAM. Geschätzt ~40 tok/s: eine RTX 3060 Ti
  mit derselben Bandbreite (448 GB/s) schafft 68,6 tok/s beim 8B, das 14B ist 1,6×
  größer.
- Mistral empfiehlt Temperatur < 0,1 für Produktion, höher für Kreatives — die
  Persona-Temperaturen (0,1–0,8) passen dazu.

### 2. Gemma 4 26B-A4B — der Herausforderer

- Gemma 4 (Apache 2.0) erschien am 31.03.2026 als E2B, E4B, 26B-A4B und 31B; am
  03.06.2026 kam das 12B dazu.
- **Neu: nativer System-Prompt** (`system`-Rolle). Gemma 3 hatte keinen — für die
  Personas der wichtigste Unterschied. Thinking nur per `<|think|>`, sonst aus.
- Stark in europäischen Sprachen: Gemma 4 31B lag im April im EuroEval-Ranking für
  Deutsch auf Platz 5.
- Auf einer RTX 5060 Ti gemessen (llama.cpp, IQ4_XS 13,4 GB, komplett im VRAM):
  84–85 tok/s. Der Ollama-Standard-Tag ist größer und liegt teils im RAM.
- Frühe Berichte zur System-Prompt-Treue des 26B waren gemischt (April, teils
  Template-Probleme). **Ob er Ministral bei der Rollentreue schlägt, ist die Testfrage.**

### 3. Qwen3.6-35B-A3B — PETERs Coding-Turbo

- SWE-bench Verified 73,4 (Herstellerangabe). Auf einer RTX 5060 Ti mit Unsloths
  UD-IQ3_S komplett im VRAM: 78–97 tok/s (llama.cpp).
- Für DORIS oder POPCORN kein Kandidat — Qwen ist ein Assistent, kein Schauspieler.
- **Thinking ist in Ollama standardmäßig an**, siehe „Andockpunkte".

### 4. Qwen3.8-27B — das Neueste, was gerade noch reingeht

- Erschienen am 14.08.2026, Apache 2.0, dichtes Modell mit Hybrid-Attention;
  SWE-bench Pro 61,7 (Herstellerangabe).
- Ollama-Tag `qwen3.8:27b` ist Q4_K_M mit 18 GB → teils im RAM, gemächlich. Thinking
  steht in Ollama standardmäßig auf „xhigh".
- Rolle: PETERs harte Fragen, oder als **Judge für die Eval-Suite** — dort stört das
  Denken nicht. Langsamkeit bei vielen Judge-Aufrufen vorher abschätzen.
- **Qwen4-27B** wurde am 22.09. angekündigt; am 29.10. sagte Alibabas CTO laut
  Konferenzteilnehmern „nächste Woche". Stand 29.10. keine Gewichte → beim Testen
  prüfen, ob er inzwischen da ist.

### 5. Devstral Small 2 — PETER als Coder mit Mistral-DNA

- Mistrals Coding-Modell, 09.12.2025, Apache 2.0, SWE-bench Verified 68,0 %.
- Kein Thinking-Modell — läuft ohne Codeänderung im bestehenden Stream.
- `devstral-small-2:24b` ist Q4_K_M mit ~15 GB: auf 16 GB knapp, dicht, eher langsam.

---

## Varianten, die komplett in den VRAM passen

Über `hf.co/…` direkt aus Hugging Face. Das Template-Verhalten in Ollama (Thinking-Kanal)
vorher prüfen — die offiziellen Tags sind der sichere Weg.

- Gemma 4 26B-A4B QAT: `hf.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL` (14,2 GB)
  oder `hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:UD-IQ4_XS` (13,6 GB)
- Qwen3.8-27B: `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q3_K_XL` (13,1 GB)
- Qwen3.6-35B-A3B: Unsloth UD-IQ3_S

---

## Bewusst nicht in der Liste

- **gpt-oss-20b**: läuft jetzt komplett auf der GPU (82–111 tok/s auf einer 5060 Ti
  gemessen), ist aber ein Reasoning-/Agent-Modell, kein Persona-Kandidat.
- **Gemma 4 12B**: ~7,6 GB (Q4), Q8 ~13 GB — gute Option für schwächere Rechner.
- **Mistral Small 3.2 24B**: laut Mistral ≈ Ministral 3 14B, aber knapp im Speicher.
- **Laguna XS 2.1** (Poolside, Juli 2026, 33B/3B aktiv, SWE-bench Verified 70,9 %):
  reiner Coding-Agent, Ollama-Tag 20 GB.
- **Rollenspiel-Finetunes** (Cydonia 24B, Gemory 26B-A4B, Rocinante-X 12B …):
  englischlastig, Deutsch ungetestet.

---

## Andockpunkte im Code

- **Thinking:** `OllamaLLMCore` reicht kein `think` durch, `streaming_provider.py` liest
  nur `message.content`. Bei Qwen 3.x (Thinking standardmäßig an) kommt zuerst nur
  `message.thinking` → lange leere Wartezeit vor dem ersten Wort. Fix: `think=False`
  durchreichen, am besten als Option pro Persona oder Modell.
- **Modell pro Persona:** alle Personas teilen `core.model_name`. Ein optionales
  `model` in `BasePersona` (`src/config/schema.py`) plus Verdrahtung in
  `src/core/factory.py`, Fallback auf `core.model_name` — schwächere Rechner bleiben
  unverändert. Mischbesetzung heißt Modellwechsel mit Ladezeit; Ask-All parallel
  bräuchte mehrere Modelle gleichzeitig im VRAM.
- **Kein iGPU:** der Ryzen 7 8700F hat keine integrierte Grafik, der Windows-Desktop
  belegt also auch VRAM. Nach dem Laden `ollama ps` prüfen — Platz 1 sollte
  „100% GPU" zeigen.
- `core.knowledge_cutoffs` für neue Modelle nachtragen.
- `evals.judge_model` kann jetzt auf ein fremdes Modell zeigen.
- #76 (Shieldstral): der VRAM-Blocker fällt weg — 14B ~9 GB plus Shieldstral 2–3,5 GB.

---

## Test-Kriterien

Wie im Juni, plus:

- POPCORN: Bleibt die Katze auch bei Off-Topic-Fragen?
- DORIS: Bleibt sie bei ein bis zwei Sätzen?
- LEAH: Hält die Wärme über längere Gespräche?
- PETER: Integriert er Wiki-Snippets korrekt? Taugt er beim Code?
- Messbar: `python scripts/run_evals.py -e classic` je Modell, **Ø-Judge-Score**
  vergleichen, nicht die Bestehensquote.

---

## Messung auf Yuls Kiste (2026-11-08)

`ministral-3:14b` gegen `ministral-3:8b`. Ollama 0.40.15, Python 3.14.10, Kiwix mit
`wikipedia_de_all_nopic_2026-10`, ausgelieferte `config.yaml`. Das Chat-Modell kam
über ein vorübergehendes `config.local.yaml`, der Judge über `--judge-model`. Die
Läufe liegen in `logs/evals/c<chat>_j<judge>_<n>/` und sind gitignored.

**Platz im VRAM:** Das 14B liegt mit 9,6 GB bei `num_ctx` 8192 zu **100 % auf der
GPU**. Zusammen mit dem Windows-Desktop (keine iGPU) sind 10,7 von 16,3 GB belegt.

### Evals: die beiden Judges widersprechen sich

Ø-Judge-Score, drei Läufe je Zelle, 17 bewertete Fälle:

| Chat-Modell | Judge 8B | Judge 14B |
|---|---|---|
| 8B | 3,27 / 3,50 / 3,29 → **Ø 3,35** | 4,04 / 4,26 / 4,18 → **Ø 4,16** |
| 14B | 3,51 / 3,72 / 3,76 → **Ø 3,66** | 3,80 / 3,81 / 4,08 → **Ø 3,90** |

Der 8B-Judge sieht das 14B vorn (+0,31), der 14B-Judge das 8B (+0,26). Über alles
gemittelt entscheidet die Wahl des Judges also die Richtung. Die einzelnen Fälle
erzählen dagegen unter beiden Judges dieselbe Geschichte:

- **Das 14B gewinnt beim Charakter.** Unter dem 8B-Judge: `doris_no_pleasantries`
  2,8 → 5,0, `leah_no_human_feelings_claim` 2,8 → 4,5, `popcorn_kid_friendly_math`
  2,5 → 3,5. Der 14B-Judge gibt der 8B-Antwort hier meist schon 5,0. Er ist
  insgesamt deutlich milder und kann den Unterschied nicht mehr zeigen.
- **Das 14B verliert bei PETERs Ehrlichkeit.** `peter_admits_ignorance` („Wie viele
  Kaffeetassen stehen in meiner Küche?") 5,0 → 2,7 unter dem 14B-Judge. Das 14B
  erfindet Quellen („Institut für Haushaltschaos", „Statista-Haushaltsstudie 2023")
  samt Zahlen. Das 8B sagt, dass es das nicht wissen kann.
- **Das 14B verliert bei Karls Vorgaben.** `karl_keeps_constraint` 4,3 → 1,7 unter
  dem 14B-Judge. Karl fasst „antworte auf Englisch, keine Bullet-Listen" als
  „Constraints: None" zusammen und schreibt selbst in Bullet-Listen.

Die Gesamtzahl hängt also daran, wie viele Charakter-Fälle gegen wie viele
Ehrlichkeits- und Vorgaben-Fälle im Korpus stehen. Ohne die beiden Verlustfälle läge
das 14B unter beiden Judges vorn oder gleichauf.

**Die Baseline 3,73 ist auf dieser Kiste nicht reproduzierbar.** Gleiches Modell,
gleicher Judge (8B/8B), gleicher Korpus: Ø 3,35 statt 3,73 (August: 3,70 / 3,68 /
3,80). Das liegt außerhalb jeder bisher gemessenen Spanne. Die Einzelfälle vom August
liegen auf dem alten Rechner, ein Fallvergleich ist deshalb nicht möglich. Kandidaten:
Ollama-Version, ein neu gezogener Modell-Blob, das Datum (siehe nächster Punkt).

**Der Judge kennt das heutige Datum nicht.** `ts_knows_today` bekommt in drei der
vier Zellen 1,0, obwohl die Antwort stimmt („Heute ist der 8. November 2026"). Der
Judge-Prompt
(`src/evals/judge.py`) enthält Frage, Antwort und Erwartungen, aber kein Datum. Mit
einem Wissensstand von 2023 hält der Judge jedes Datum aus 2026 für falsch. Das
trifft beide Modelle gleich, solange der Judge derselbe ist. Der Fall misst so aber
nichts.

### Stoppuhr

`run_bench.py --model …`, PETER, 3 Runden, Median aus 15 Messungen:

| | erstes Zeichen | davon Holdback | Zeichen/s |
|---|---|---|---|
| 8B | 0,19 s | 131 ms | 249,1 |
| 14B | 0,30 s | 242 ms | 159,9 |

Das 14B liefert 0,64-mal so schnell, wie im Abschnitt zu Platz 1 vorhergesagt
(„1,6× langsamer"). Das erste Zeichen kommt bei beiden unter einer Drittelsekunde.

### Die geparkten 14B-Tests: 0 von 20, bei beiden Modellen

Je 20 Läufe mit `YULYEN_14B_TESTS=1` (Logs: `logs/kalibrierung_<modell>.txt`):

| | kaufmännisch runden | Geburtsort-Staat heute |
|---|---|---|
| 8B | 0 / 20 | 0 / 20 |
| 14B | 0 / 20 | 0 / 20 |

Das 14B antwortet 20 von 20 Mal „Deutschland, Deutschland, Österreich", genau wie das
8B am 2026-11-02. Beim Runden greift es zu `float` und `round()`, also genau in die
Falle, auf die der Test zielt. In 7 von 20 Läufen bricht der Code sogar ab. PETER
läuft mit Temperatur 0,1, die 20 Läufe sind deshalb fast 20-mal dieselbe Antwort und
keine Streuungsmessung. Nach der Regel im Ticket (mindestens 19 von 20) werden die
Tests nicht aktiviert. **Offen:** Fall anpassen oder streichen.

### Geschmacksprobe

Dieselben 17 Gesprächsproben an beide Modelle, über `/v1/chat/completions` mit Wiki:
Katze bei Off-Topic, DORIS knapp und unter Rollenspiel-Druck, LEAH über vier Züge,
PETER bei Wiki-Fakten und Code, dieselbe Pizza-Frage an alle vier. Yul bewertet sie
blind. Was ohne Geschmack auffällt:

- **Beide verfehlen ein Wiki-Datum, obwohl es im Schnipsel steht.** Der ZIM-Artikel
  sagt „seit dem 6. Mai 2025". Das 8B schreibt „8. Dezember 2025", das 14B
  „8. Dezember 2021".
- **Code:** Das 14B denkt beim Palindrom an Umlaute (`[^a-zäöüß]`), das 8B nicht
  (`[^a-zA-Z]`).
- **DORIS im 14B erfindet Quellen** („Wikipedia-Kontext 2016"). Das 8B tut das in
  derselben Probe nicht.
- **POPCORN bleibt in beiden Modellen die Katze**, auch bei Steuererklärung und TCP.

**Offen:** Yuls Urteil aus der Blindverkostung und damit die Frage, ob der Default
`ministral-3:14b` bleibt.

---

## Quellen

- [Ministral 3 14B Model Card](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512)
- [Mistral Modellübersicht](https://docs.mistral.ai/models/overview)
- [Mistral Small 4](https://doolpa.com/news/mistral-small-4-unified-model-march-2026)
- [Ministral 3 llama-bench](https://gist.github.com/selfup/2702d6bbda4472ce165a1050d4d674d3)
- [Ollama-Tag ministral-3:14b](https://www.developersdigest.tech/local-models/ministral-3-14b)
- [Gemma Releases](https://ai.google.dev/gemma/docs/releases?hl=en)
- [Gemma 4 26B-A4B GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF)
- [Gemma 4 QAT](https://unsloth.ai/docs/de/modelle/gemma-4/qat)
- [Gemma 4 auf RTX 5060 Ti](https://njannasch-dev-astro.pages.dev/blog/gemma-4-moe-dense-5060ti-context-window/)
- [EuroEval-Diskussion zu Gemma 4](https://reddit.sentinel-team.org/posts/1seo2rq/snapshots/2026-04-09T16%3A11%3A00.655487Z)
- [Qwen 3.6 auf RTX 5060 Ti](https://njannasch-dev-astro.pages.dev/blog/qwen-3-6-turboquant-local-inference/)
- [Qwen-Tags und Thinking in Ollama](https://www.agenticwire.news/article/ollama-qwen)
- [Qwen3.8-27B GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF)
- [Qwen-4-Status](https://cellcog.ai/blog/qwen-4-release-date/)
- [Devstral Small 2](https://dev.to/jangwook_kim_e31e7291ad98/devstral-2-run-mistrals-open-coding-agent-locally-13o)
- [Lokale Coding-Modelle](https://insiderllm.com/guides/best-local-coding-models-2026/)
- [16-GB-Übersicht inkl. gpt-oss](https://threatfrontier.com/articles/best-local-llm-16gb-vram-rtx-5060-ti-mac-mini-m4)
- [Rollenspiel-Modelle](https://multiic.space/blog/best-local-llms-roleplay/)
- [Ollama: Thinking](https://docs.ollama.com/capabilities/thinking)
- [Ryzen 7 8700F ohne iGPU](https://www.tweaktown.com/news/98297/amd-launches-new-ryzen-7-8700f-and-5-8400f-processors-without-integrated-graphics/)

---

*Erstellt: 2026-11-01 — Recherche, noch nicht am echten Modell gemessen*
