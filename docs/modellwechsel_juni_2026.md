# Modellwechsel-Analyse — Juni 2026

Kontext: Yul Yen's AI Orchestra läuft lokal mit 4 Personas (LEAH, DORIS, PETER, POPCORN)
auf einer GPU mit 8 GB VRAM. Bewertungsfokus: **Prompt-Treue, Persona-Integrität,
Wiki-Snippet-Integration** — nicht rohe Benchmarks.

---

## Aktueller Stand

| Parameter | Wert |
|---|---|
| Modell | `ministral-3:8b` (Ministral 8B, vermutl. Q4 oder Q5) |
| Context | 8192 Token |
| VRAM-Auslastung | ~5,1 GB (Q4) / ~6,3 GB (Q5_K_M) |
| Backend | Ollama |
| Sprache | Deutsch (primary) |

### Warum Ministral 8B gut funktioniert

Mistral-Architektur ist von Haus aus stark auf **Instruction-Adherence** trainiert.
Das zeigt sich konkret:

- POPCORN verhält sich wie eine Katze — nicht wie ein Chatbot, der auf Katze macht
- Wiki-Snippets werden korrekt in Antworten integriert, ohne Persona zu brechen
- LeoLM 13B (Vergleich): größer, deutschsprachig, aber schlechtere Prompt-Treue wegen
  Finetuning-Kompromissen auf Llama-2-Basis

---

## Bewertungsmatrix Kandidaten

> Legende: ★★★★★ = sehr gut / ★★★☆☆ = mittel  
> VRAM-Angaben: Q4_K_M-Quant, Inference only

| Modell | VRAM | Prompt-Treue | Wiki-Nutzung | Deutsch | Speed | Gesamtbewertung |
|---|---|---|---|---|---|---|
| **Ministral 8B** *(Referenz)* | ~5,1 GB | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ | Referenz |
| **Qwen2.5 7B-Instruct** | ~4,5 GB | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | **Top-Kandidat** |
| **Qwen3 8B** (non-thinking) | ~5,0 GB | unbekannt¹ | soll stark sein | sehr gut | ★★★★☆ | Prüfenswert |
| **Mistral Nemo 12B** @ Q3 | ~5,8 GB | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | kein klarer Gewinn |
| **LeoLM 7B** | ~4,3 GB | ★★★☆☆ | ★★★☆☆ | ★★★★★ | ★★★★☆ | Nein² |
| **LeoLM 13B** | ~8,1 GB³ | ★★★☆☆ | ★★★☆☆ | ★★★★★ | ★★★☆☆ | War schlechter |
| **Gemma 3 9B** | ~5,8 GB | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | Knapp, kein Vorteil |
| **Phi-4 Mini** | ~2,5 GB | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★★★ | Zu schwach für Rollen |

¹ Qwen3 neu, noch wenig Erfahrung im Persona-/Rollenkontext  
² Gleicher Kompromiss wie LeoLM 13B — Sprachfähigkeit auf Kosten von IF  
³ Passt bei Q4 grenzwertig in 8 GB, bei Q5 kaum noch

---

## Top-Kandidat: Qwen2.5 7B-Instruct

### Argumente dafür

- **Instruction-Following** laut Alibaba-Benchmarks auf Augenhöhe mit Mistral 8B,
  teils darüber bei komplexen Multi-Constraint-Prompts
- **Multilingual** deutlich stärker als Mistral-Linie — relevant für deutsche
  Redewendungen, Dialektmischung, Stilsicherheit pro Persona
- **VRAM-Budget**: ~4,5 GB lässt 3,5 GB Puffer — erlaubt Q6_K_M für mehr Qualität
  oder gibt Luft für Kiwix + spaCy
- **Wiki-Injection**: Qwen2.5 priorisiert kontextuelle Anweisungen sehr präzise,
  was für die Snippet-Nutzung ideal ist

### Argumente dagegen

- 7B statt 8B — ob das in der Persona-Tiefe spürbar ist, ist Praxistest-Sache
- Ministral ist bereits sehr gut; der Gewinn könnte marginal sein

### Ollama-Befehl

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
# oder höhere Quant mit dem gesparten VRAM-Budget:
ollama pull qwen2.5:7b-instruct-q6_K
```

In `config.yaml`:
```yaml
core:
  model_name: "qwen2.5:7b-instruct-q4_K_M"
```

---

## Zweiter Kandidat: Höhere Quantisierung von Ministral selbst

Bevor ein Modellwechsel: lohnt es sich, bei Ministral 8B von Q4 auf Q5_K_M zu wechseln?

| Quant | VRAM | Qualitätsgewinn | Empfehlung |
|---|---|---|---|
| Q4_K_M | ~5,1 GB | Basis | aktuell vermutlich |
| Q5_K_M | ~6,1 GB | +spürbar (Tonalität, Nuancen) | **guter erster Schritt** |
| Q6_K | ~6,9 GB | +nochmals besser | nur wenn 7 GB sicher frei |
| Q8_0 | ~8,5 GB | theoretisch maximal | zu riskant für 8 GB |

```bash
ollama pull mistral:8b-instruct-q5_K_M
```

**Fazit:** Q5_K_M von Ministral ist der risikoärmste Upgrade-Pfad — gleiches Modell,
mehr Gewicht, bessere Nuancen. Kein Persona-Regression-Risiko.

---

## Dritter Kandidat: Qwen3 8B (Beobachtungsliste)

Qwen3 erschien Anfang 2025 und bringt eine neue Architektur mit optionalem
Thinking-Modus. Für Personas ist der **non-thinking Modus** relevant (schnell, direkt).

- Stärker auf Reasoning als Qwen2.5, unklar ob Persona-Adherence besser
- Noch wenig Community-Erfahrung für Rollenspiel/Persona-Setups
- **Strategie:** Beobachten, in 2-3 Monaten nochmal evaluieren

```bash
ollama pull qwen3:8b  # non-thinking via system-prompt-Flag oder Modell-Default
```

---

## Abgelehnte Kandidaten

### Deutsch-Finetunes (LeoLM, em_german, …)

Das LeoLM-13B-Experiment hat gezeigt: **Sprachfähigkeit und Prompt-Treue sind
Gegensätze beim Finetuning auf Llama-2-Basis.** POPCORN maunzt auf Befehl statt
aus Überzeugung. Kein Deutsch-Finetune in dieser Klasse ist ein Upgrade.

### Größere Modelle (13B+)

Mistral Small 3.1 24B, LeoLM 13B, Phi-4 14B — alle zu groß für entspannte 8-GB-Inference.
Grenzseitige Fits (Q3) erkaufen sich Qualitätsverluste durch aggressive Quantisierung.

---

## Empfohlene Test-Reihenfolge

1. **Ministral 8B Q5_K_M** — risikolos, sofortiger Qualitätstest
2. **Qwen2.5 7B-Instruct Q4_K_M** — echter Vergleichstest, 3-4 Gespräche pro Persona
3. **Qwen2.5 7B-Instruct Q6_K** — wenn Schritt 2 gut, höhere Quant mit dem VRAM-Puffer
4. **Qwen3 8B** — in einigen Monaten nochmal prüfen

### Test-Kriterien

- POPCORN: Bleibt die Katze auch bei Off-Topic-Fragen?
- PETER: Integriert er Wiki-Snippet-Fakten korrekt ohne zu halluzinieren?
- LEAH: Hält die Wärme über längere Gespräche?
- Broadcast-Modus: Keine Persona bricht aus der Rolle

---

*Erstellt: Juni 2026 — basierend auf Praxiserfahrung mit dem Ensemble*
