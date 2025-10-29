# Backlog

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 18 | Terminal-UI logging fix | Write logs exclusively to files to keep the console clean | S | M | Bugfix |
| 19 | Web-UI "New conversation" in stream | ✅ Done: End streaming cleanly so that the "New conversation" button works | M | L | Bugfix |
| 20 | Internationalize personas | ✅ Done: Provide personas as well as UI text for German and English | M | L | UX/Technology |
| 21 | spaCy internationalization | Automatically use the corresponding English spaCy model when English is configured | M | M | Technical foundation |
| 22 | Structure documentation bilingually | Offer README, Features, and Backlog in both German and English | M | M | Documentation |
| 3 | Health checks/monitoring | Status page (Ollama/VRAM), simple `/healthz` endpoint plus VRAM probe | S | M | Technical foundation |
| 4 | Gradio share + basic auth | ✅ Done: Enable external testing with protection | S | M | Technical foundation |
| 5 | Model selection in the UI | Dropdown/radio for available models, explicitly selectable per persona and run | S | S | UX/Technology |
| 6 | LoRA fine-tuning pipeline | IN PROGRESS → LoRA adapter for LeoLM13B | L | XL | Research/Quality |
| 7 | Save/load chat histories | Persist sessions (JSON/DB) | M | L | Technical foundation |
| 8 | Ask-all (broadcast) | Ask the same question sequentially to Leah, Doris, Peter, and Popcorn with separate contexts | S | M | Orchestration |
| 9 | Stage mode (self-talk) | Two or more personas run n rounds of dialogue, starting with a single opening sentence | M | L | Orchestration |
| 10 | Easter egg logic | Keyword triggers an extra tagline | M | M | Cool feature |
| 12 | Karl (context summarizer) | Compress history on demand with an LLM summary instead of the current approach | L | L | Technical foundation |
| 13 | STT/TTS (speech ↔ text) MVP | Simple speech I/O | M | M | Cool feature |
| 14 | Email to/from AI | Read, compose, and send email | M | M | Integration |
| 15 | Daily briefing (IoT + RSS) | Daily short updates | M | M | Cool feature |
| 16 | Sandbox/PDF functions | Local documentation sandbox | L | M | Cool feature |
| 17 | Faster first token | Warm-up, prompt diet, stream buffer | M | L | Performance |
