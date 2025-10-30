# KI-Agenten (Personas)

Das System beinhaltet **vier KI-Personas** (Agenten) mit unterschiedlichen Rollen und Charakteren. **Alle nutzen dasselbe Basismodell**, unterscheiden sich aber durch individuelle System-Prompts und spezifische Konfigurationen. Im Folgenden werden alle vier Agenten und ihre Eigenschaften erläutert.

_The system includes **four AI personas** (agents) with different roles and characters. **All share the same base model** but differ through individual system prompts and specific configurations. The following sections describe each agent and its characteristics._

---

## Leah

- **Kurzbeschreibung:** Charmante, empathische KI. Ideal für Alltag und Gespräche, die **freundlich und leicht** klingen sollen. Leah spricht den Nutzer in der Du-Form an und agiert wie eine gute Freundin.

  _Short description: Charming, empathetic AI. Perfect for everyday chat that should sound **friendly and light**. Leah addresses users informally and acts like a good friend._

- **Modellkonfiguration:** Verwendet das gemeinsame **Basismodell** (`leo-hessianai-13b-chat.Q5` über Ollama) ohne zusätzliche Adapter. Die Generierungs-Parameter sind **ausgewogen eingestellt**: Temperatur 0,65, Repeat Penalty 1,15 und Kontextlänge 4096 Token. Leah ist als *featured persona* definiert, also Standard-Auswahl in der UI.

  _Model configuration: Uses the shared **base model** (`leo-hessianai-13b-chat.Q5` via Ollama) without additional adapters. Generation parameters are **balanced**: temperature 0.65, repeat penalty 1.15, and context length of 4096 tokens. Leah is marked as the *featured persona*, making her the default UI selection._

- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **LEAH**). Der Prompt stellt Leah als *“Large Extraordinary Artificial Hyperintelligence”* vor und enthält Regeln für einen **lockeren, freundlichen Ton** – sie antwortet grundsätzlich auf Deutsch, außer bei klar englischen Fragen.

  _System prompt: Defined in `locales/de/personas.yaml` (entry **LEAH**). The prompt presents Leah as a *“Large Extraordinary Artificial Hyperintelligence”* and enforces a **relaxed, friendly tone**—she responds in German by default, except when questions are clearly in English._

- **Besonderheiten:** Leah ist die **Standard-Persona** des Systems. Keine exklusiven Tools; nutzt bei Bedarf die Wiki-Integration. Ihre Antworten sind stets **charmant, höflich und positiv** formuliert.

  _Special traits: Leah is the system’s **default persona**. She has no exclusive tools and uses the shared wiki integration when needed. Her responses are always **charming, polite, and positive**._

---

## Doris

- **Kurzbeschreibung:** Direkt, spitz und mit **trockenem Humor**. Perfekt, wenn man **ehrliche und freche** Antworten bekommen möchte.

  _Short description: Direct, sharp, and armed with **dry humor**. Ideal when you want **honest and cheeky** replies._

- **Modellkonfiguration:** Nutzt ebenfalls das gemeinsame **Basismodell** ohne aktiven Adapter. Ein **experimenteller LoRA-Feintuning-Adapter** existiert (Proof-of-Concept, ca. 200 Beispieldialoge), ist aber im Standard deaktiviert. Generierungs-Parameter: Temperatur 0,6, Repeat Penalty 1,15, Kontext 4096.

  _Model configuration: Also uses the shared **base model** without an active adapter. An **experimental LoRA fine-tuning adapter** exists (proof of concept with about 200 sample dialogs) but is disabled by default. Generation parameters: temperature 0.6, repeat penalty 1.15, context 4096._

- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **DORIS**). Vorgestellt als *“Direct Objective Remarkably Intelligent System”*. Der Prompt legt einen **knappen, sarkastischen Stil** fest – Doris darf necken, aber nicht verletzen.

  _System prompt: Defined in `locales/de/personas.yaml` (entry **DORIS**). Introduces Doris as a *“Direct Objective Remarkably Intelligent System.”* The prompt enforces a **concise, sarcastic style**—she may tease but must not be hurtful._

- **Besonderheiten:** Kurze, pointierte Antworten (1–2 Sätze). Meidet Smalltalk und Floskeln. Keine exklusiven Tools; greift wie Leah auf gemeinsame Wissensfunktionen zu.

  _Special traits: Provides short, pointed answers (1–2 sentences). Avoids small talk and stock phrases. No exclusive tools; uses the same shared knowledge features as Leah._

---

## Peter

- **Kurzbeschreibung:** Nerdige, **faktenorientierte KI** mit Herz. Liefert präzise Infos und erklärt sie verständlich.

  _Short description: Nerdy, **fact-focused AI** with heart. Delivers precise information and explains it clearly._

- **Modellkonfiguration:** Nutzt das **Basismodell** über Ollama mit deterministischer Konfiguration: Temperatur 0,2, Repeat Penalty 1,15, Kontext 4096 und fester Zufalls-Seed (42). Fokus: **Konsistenz und Faktentreue**.

  _Model configuration: Uses the **base model** via Ollama with a deterministic setup: temperature 0.2, repeat penalty 1.15, context 4096, and a fixed random seed (42). Focus: **consistency and factual accuracy**._

- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **PETER**). Beschrieben als *“Precise Encyclopedic Thinking and Empathy Resource”*. Der Prompt fordert ehrliche, faktenbasierte und nachvollziehbare Antworten – Peter gibt lieber zu, wenn er etwas nicht weiß.

  _System prompt: Defined in `locales/de/personas.yaml` (entry **PETER**). Describes Peter as a *“Precise Encyclopedic Thinking and Empathy Resource.”* The prompt demands honest, fact-based, and traceable answers—Peter would rather admit when he does not know something._

- **Besonderheiten:** **Spezialist für Wissen und Recherche**. Wird von anderen Personas bei faktischen Fragen herangezogen. Nutzt intern denselben Wiki-Proxy wie Leah für Zusatzinformationen. Antworten sind sachlich und verständlich formuliert.

  _Special traits: **Knowledge and research specialist.** Other personas defer to him for factual questions. Internally uses the same wiki proxy as Leah for additional information. Answers are formulated objectively and clearly._

---

## Popcorn

- **Kurzbeschreibung:** Verspielte, clevere **Katzen-KI**. Ideal für kreative Aufgaben und kindgerechte Erklärungen.

  _Short description: Playful, clever **cat-themed AI**. Perfect for creative tasks and kid-friendly explanations._

- **Modellkonfiguration:** Greift auf das gemeinsame **Basismodell** zurück, ohne Adapter. Parameter auf **hohe Kreativität** ausgelegt: Temperatur 0,8, Repeat Penalty 1,15, Kontext 4096.

  _Model configuration: Uses the shared **base model** without adapters. Parameters favor **high creativity**: temperature 0.8, repeat penalty 1.15, context 4096._

- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **POPCORN**). Beschrieben als *“Playful Oracle of Purrs & Cats”*. Sprachstil: spielerisch, kindgerecht, mit Katzen-Anspielungen.

  _System prompt: Defined in `locales/de/personas.yaml` (entry **POPCORN**). Describes Popcorn as a *“Playful Oracle of Purrs & Cats.”* The tone is playful, child-friendly, and full of cat references._

- **Besonderheiten:** Jede Antwort enthält mindestens eine **Katzen-Referenz** (z. B. „miau“, 🐱 oder „katzig“). Antworten bleiben informativ, aber leicht und humorvoll. Keine eigenen Tools oder RAG-Mechanismen – Popcorn nutzt dieselbe technische Basis wie die anderen Agenten.

  _Special traits: Every answer includes at least one **cat reference** (e.g. ”meow”, 🐱 or “feline“). Responses stay informative yet light and humorous. No dedicated tools or RAG mechanisms—Popcorn uses the same technical foundation as the other agents._

---
