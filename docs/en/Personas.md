# AI Agents (Personas)

> ℹ️ **Translation notice (2026-07-04):** This document is an English translation of [`docs/de/Personas.md`](../de/Personas.md). For the authoritative German source, please refer to that file.

The system includes **four AI personas** (agents) with different roles and characters. **All share the same base model** — configured in `config.yaml` under `core.model_name` (currently `ministral-3:14b`) — but differ through individual system prompts and specific generation parameters (defined in `ensembles/classic/personas_base.yaml`). The following sections describe each agent and its characteristics.

---

## Leah

- **Short description:** Charming, empathetic AI. Perfect for everyday chat that should sound **friendly and light**. Leah addresses users informally and acts like a good friend.
- **Model configuration:** Uses the shared **base model** (via Ollama) without additional adapters. Generation parameters are **balanced**: temperature 0.55, Ollama's default repeat penalty, and a context length of 16384 tokens. Leah is marked as the *featured persona*, making her the default UI selection.
- **System prompt:** Defined in `ensembles/classic/locales/{de,en}/personas.yaml` (entry **LEAH**). The prompt presents Leah as a *“Large Extraordinary Artificial Hyperintelligence”* and enforces a **relaxed, friendly tone**—she responds in German by default, except when questions are clearly in English.
- **Special traits:** Leah is the system’s **default persona**. She has no exclusive tools and uses the shared wiki integration when needed. Her responses are always **charming, polite, and positive**.

---

## Doris

- **Short description:** Direct, sharp, and armed with **dry humor**. Ideal when you want **honest and cheeky** replies.
- **Model configuration:** Also uses the shared **base model** without an active adapter. An **experimental LoRA fine-tuning adapter** exists as a proof of concept (about 200 sample dialogs) outside this repository; it is not wired in here. Generation parameters: temperature 0.5, context 16384.
- **System prompt:** Defined in `ensembles/classic/locales/{de,en}/personas.yaml` (entry **DORIS**). Introduces Doris as a *“Direct Objective Remarkably Intelligent System.”* The prompt enforces a **concise, sarcastic style**—she may tease but must not be hurtful.
- **Special traits:** Provides short, pointed answers (1–2 sentences). Avoids small talk and stock phrases. No exclusive tools; uses the same shared knowledge features as Leah.

---

## Peter

- **Short description:** Nerdy, **fact-focused AI** with heart. Delivers precise information and explains it clearly.
- **Model configuration:** Uses the **base model** via Ollama with a near-deterministic setup: very low temperature of 0.1, context 16384. Focus: **consistency and factual accuracy**.
- **System prompt:** Defined in `ensembles/classic/locales/{de,en}/personas.yaml` (entry **PETER**). Describes Peter as a *“Precise Encyclopedic Thinking and Empathy Resource.”* The prompt demands honest, fact-based, and traceable answers—Peter would rather admit when he does not know something.
- **Special traits:** **Knowledge and research specialist.** The other personas point users to him for factual questions — they do not call him; the user switches. Internally uses the same wiki proxy as Leah for additional information. Answers are formulated objectively and clearly.

---

## Popcorn

- **Short description:** Playful, clever **cat-themed AI**. Perfect for creative tasks and kid-friendly explanations.
- **Model configuration:** Uses the shared **base model** without adapters. Parameters favor **high creativity**: temperature 0.7, context 16384.
- **System prompt:** Defined in `ensembles/classic/locales/{de,en}/personas.yaml` (entry **POPCORN**). Describes Popcorn as a *“Playful Oracle of Purrs & Cats.”* The tone is playful, child-friendly, and full of cat references.
- **Special traits:** Every answer includes at least one **cat reference** (e.g. “meow”, 🐱 or “feline“). Responses stay informative yet light and humorous. No dedicated tools or RAG mechanisms—Popcorn uses the same technical foundation as the other agents.

---
