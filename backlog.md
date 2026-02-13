# backlog.md

| No. | Name | Description | Effort | Benefit | Category |
| --- | --- | --- | --- | --- | --- |
| 2 | Web-UI "New conversation" in stream | Done? End streaming cleanly so that the "New conversation" button works | M | L | Bugfix |
| 5 | Health checks/monitoring | Status page (Ollama/VRAM), simple `/healthz` endpoint plus VRAM probe | S | M | Technical foundation |
| 6 | Model selection in the UI | Dropdown/radio for available models, explicitly selectable per persona and run | S | S | UX/Technology |
| 7 | LoRA fine-tuning pipeline | IN PROGRESS → LoRA adapter for LeoLM13B | L | XL | Research/Quality |
| 9 | Ask-all (broadcast): Finetuning | Wiki missing, streaming in webUI, TerminalUI-Flow | S | M | Orchestration |
| 11 | Easter egg logic | Keyword triggers an extra tagline | M | M | Cool feature |
| 12 | Karl (context summarizer) | Compress history on demand with an LLM summary instead of the current approach | L | L | Technical foundation |
| 13 | STT MVP | Simple speech Input | M | M | Cool feature |
| 14 | Email to/from AI | Read, compose, and send email | M | M | Integration |
| 15 | Daily briefing (IoT + RSS) | Daily short updates | M | M | Cool feature |
| 16 | Sandbox/PDF functions | Local documentation sandbox | L | M | Cool feature |
| 17 | Faster first token | Warm-up, prompt diet, stream buffer | M | L | Performance |
| 18 | Wrongdoing guardrail (violence/weaponization) | Add a minimal deterministic guardrail for violent wrongdoing requests (e.g., weapons/explosives/attack instructions). Implement as pre-LLM input check + session lock (once triggered, keep blocking follow-ups like “it’s for a novel”). Provide safe alternative response templates and add unit tests for common bypass patterns. | S | M | Security/Robustness |