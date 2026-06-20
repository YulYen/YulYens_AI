# AI Agents (Personas)

The system includes **four AI personas** (agents) with different roles and characters. **All share the same base model** but differ through individual system prompts and specific configurations. The following sections describe each agent and its characteristics.

---

## Leah

- **Short description:** Charming, empathetic AI. Perfect for everyday chat that should sound **friendly and light**. Leah addresses users informally and acts like a good friend.
- **Model configuration:** Uses the shared **base model** (`leo-hessianai-13b-chat.Q5` via Ollama) without additional adapters. Generation parameters are **balanced**: temperature 0.65, repeat penalty 1.15, and context length of 4096 tokens. Leah is marked as the *featured persona*, making her the default UI selection.
- **System prompt:** Defined in `locales/de/personas.yaml` (entry **LEAH**). The prompt presents Leah as a *“Large Extraordinary Artificial Hyperintelligence”* and enforces a **relaxed, friendly tone**—she responds in German by default, except when questions are clearly in English.
- **Special traits:** Leah is the system’s **default persona**. She has no exclusive tools and uses the shared wiki integration when needed. Her responses are always **charming, polite, and positive**.

---

## Doris

- **Short description:** Direct, sharp, and armed with **dry humor**. Ideal when you want **honest and cheeky** replies.
- **Model configuration:** Also uses the shared **base model** without an active adapter. An **experimental LoRA fine-tuning adapter** exists (proof of concept with about 200 sample dialogs) but is disabled by default. Generation parameters: temperature 0.6, repeat penalty 1.15, context 4096.
- **System prompt:** Defined in `locales/de/personas.yaml` (entry **DORIS**). Introduces Doris as a *“Direct Objective Remarkably Intelligent System.”* The prompt enforces a **concise, sarcastic style**—she may tease but must not be hurtful.
- **Special traits:** Provides short, pointed answers (1–2 sentences). Avoids small talk and stock phrases. No exclusive tools; uses the same shared knowledge features as Leah.

---

## Peter

- **Short description:** Nerdy, **fact-focused AI** with heart. Delivers precise information and explains it clearly.
- **Model configuration:** Uses the **base model** via Ollama with a deterministic setup: temperature 0.2, repeat penalty 1.15, context 4096, and a fixed random seed (42). Focus: **consistency and factual accuracy**.
- **System prompt:** Defined in `locales/de/personas.yaml` (entry **PETER**). Describes Peter as a *“Precise Encyclopedic Thinking and Empathy Resource.”* The prompt demands honest, fact-based, and traceable answers—Peter would rather admit when he does not know something.
- **Special traits:** **Knowledge and research specialist.** Other personas defer to him for factual questions. Internally uses the same wiki proxy as Leah for additional information. Answers are formulated objectively and clearly.

---

## Popcorn

- **Short description:** Playful, clever **cat-themed AI**. Perfect for creative tasks and kid-friendly explanations.
- **Model configuration:** Uses the shared **base model** without adapters. Parameters favor **high creativity**: temperature 0.8, repeat penalty 1.15, context 4096.
- **System prompt:** Defined in `locales/de/personas.yaml` (entry **POPCORN**). Describes Popcorn as a *“Playful Oracle of Purrs & Cats.”* The tone is playful, child-friendly, and full of cat references.
- **Special traits:** Every answer includes at least one **cat reference** (e.g. “meow”, 🐱 or “feline“). Responses stay informative yet light and humorous. No dedicated tools or RAG mechanisms—Popcorn uses the same technical foundation as the other agents.

---
