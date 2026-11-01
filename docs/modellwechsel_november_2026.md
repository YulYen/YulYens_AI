# Modellwechsel-Analyse — November 2026

Stand: 2026-11-01. Nachfolger von [modellwechsel_juni_2026.md](modellwechsel_juni_2026.md),
der für 8 GB VRAM gilt und als datierter Bericht unverändert bleibt.

Anlass: Yuls neuer Rechner steht früher als geplant da — **RTX 5060 Ti mit 16 GB VRAM**
(448 GB/s), Ryzen 7 8700F, 32 GB DDR5. Bewertungsfokus wie im Juni: **Rollentreue,
Deutsch, Wiki-Nutzung** — dazu neu die Frage, ob PETER zum Coding-Helfer ausgebaut
werden kann, gern mit eigenem Modell pro Persona. Schwächere Rechner sollen weiter
mit `ministral-3:8b` laufen.

Alle Zahlen sind Recherche, **nicht auf Yuls Kiste gemessen**. Das Testen ist Backlog #78.

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
