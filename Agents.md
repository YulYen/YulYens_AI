# KI-Agenten (Personas)

Das System beinhaltet **vier KI-Personas** (Agenten) mit unterschiedlichen Rollen und Charakteren. **Alle nutzen dasselbe Basismodell**, unterscheiden sich aber durch individuelle System-Prompts und spezifische Konfigurationen. Im Folgenden werden alle vier Agenten und ihre Eigenschaften erläutert.

---

## Leah

- **Kurzbeschreibung:** Charmante, empathische KI. Ideal für Alltag und Gespräche, die **freundlich und leicht** klingen sollen. Leah spricht den Nutzer in der Du-Form an und agiert wie eine gute Freundin.  
- **Modellkonfiguration:** Verwendet das gemeinsame **Basismodell** (`leo-hessianai-13b-chat.Q5` über Ollama) ohne zusätzliche Adapter. Die Generierungs-Parameter sind **ausgewogen eingestellt**: Temperatur 0,65, Repeat Penalty 1,15 und Kontextlänge 4096 Token. Leah ist als *featured persona* definiert, also Standard-Auswahl in der UI.  
- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **LEAH**). Der Prompt stellt Leah als *“Large Extraordinary Artificial Hyperintelligence”* vor und enthält Regeln für einen **lockeren, freundlichen Ton** – sie antwortet grundsätzlich auf Deutsch, außer bei klar englischen Fragen.  
- **Besonderheiten:** Leah ist die **Standard-Persona** des Systems. Keine exklusiven Tools; nutzt bei Bedarf die Wiki-Integration. Ihre Antworten sind stets **charmant, höflich und positiv** formuliert.

---

## Doris

- **Kurzbeschreibung:** Direkt, spitz und mit **trockenem Humor**. Perfekt, wenn man **ehrliche und freche** Antworten bekommen möchte.  
- **Modellkonfiguration:** Nutzt ebenfalls das gemeinsame **Basismodell** ohne aktiven Adapter. Ein **experimenteller LoRA-Feintuning-Adapter** existiert (Proof-of-Concept, ca. 200 Beispieldialoge), ist aber im Standard deaktiviert. Generierungs-Parameter: Temperatur 0,6, Repeat Penalty 1,15, Kontext 4096.  
- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **DORIS**). Vorgestellt als *“Direct Objective Remarkably Intelligent System”*. Der Prompt legt einen **knappen, sarkastischen Stil** fest – Doris darf necken, aber nicht verletzen.  
- **Besonderheiten:** Kurze, pointierte Antworten (1–2 Sätze). Meidet Smalltalk und Floskeln. Keine exklusiven Tools; greift wie Leah auf gemeinsame Wissensfunktionen zu.

---

## Peter

- **Kurzbeschreibung:** Nerdige, **faktenorientierte KI** mit Herz. Liefert präzise Infos und erklärt sie verständlich.  
- **Modellkonfiguration:** Nutzt das **Basismodell** über Ollama mit deterministischer Konfiguration: Temperatur 0,2, Repeat Penalty 1,15, Kontext 4096 und fester Zufalls-Seed (42). Fokus: **Konsistenz und Faktentreue**.  
- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **PETER**). Beschrieben als *“Precise Encyclopedic Thinking and Empathy Resource”*. Der Prompt fordert ehrliche, faktenbasierte und nachvollziehbare Antworten – Peter gibt lieber zu, wenn er etwas nicht weiß.  
- **Besonderheiten:** **Spezialist für Wissen und Recherche**. Wird von anderen Personas bei faktischen Fragen herangezogen. Nutzt intern denselben Wiki-Proxy wie Leah für Zusatzinformationen. Antworten sind sachlich und verständlich formuliert.

---

## Popcorn

- **Kurzbeschreibung:** Verspielte, clevere **Katzen-KI**. Ideal für kreative Aufgaben und kindgerechte Erklärungen.  
- **Modellkonfiguration:** Greift auf das gemeinsame **Basismodell** zurück, ohne Adapter. Parameter auf **hohe Kreativität** ausgelegt: Temperatur 0,8, Repeat Penalty 1,15, Kontext 4096.  
- **System-Prompt:** Definiert in `locales/de/personas.yaml` (Eintrag **POPCORN**). Beschrieben als *“Playful Oracle of Purrs & Cats”*. Sprachstil: spielerisch, kindgerecht, mit Katzen-Anspielungen.  
- **Besonderheiten:** Jede Antwort enthält mindestens eine **Katzen-Referenz** (z. B. „miau“, 🐱 oder „katzig“). Antworten bleiben informativ, aber leicht und humorvoll. Keine eigenen Tools oder RAG-Mechanismen – Popcorn nutzt dieselbe technische Basis wie die anderen Agenten.

---
