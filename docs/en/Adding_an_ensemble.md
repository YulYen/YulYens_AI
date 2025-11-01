# Adding a custom ensemble

This guide explains how to create a new persona ensemble for Yul Yen's AI Orchestra. An ensemble bundles personas, their language-specific prompts, and optional media assets. You can tweak existing characters or introduce entirely new ones.

## Understand the directory layout

All ensembles live in [`ensembles/`](../../ensembles). A typical ensemble contains:

- `personas_base.yaml` – Global persona metadata (name, LLM options, defaults)
- `locales/<language>/personas.yaml` – Language-specific descriptions, prompts, and metadata
- `static/personas/<NAME>/{thumb.webp,full.webp}` – (optional) avatar images for the web UI

> 💡 Tip: The sample ensemble [`ensembles/examples/spaceship_crew`](../../ensembles/examples/spaceship_crew) shows the minimal setup without locale files or images.

## Step-by-step instructions

1. **Create a new folder**
   ```bash
   cp -r ensembles/classic ensembles/my_ensemble
   rm -rf ensembles/my_ensemble/locales/*
   ```
   Adjust the folder name (stick to lowercase letters plus `_` or `-`). Remove languages you do not plan to support.

2. **Update `personas_base.yaml`**
   - List every persona under `personas:`.
   - `name` must be unique and also matches the directory used for images.
   - `llm_options` overrides global defaults such as temperature, seed, or `num_ctx`.
   - `defaults.featured: true` marks a persona as the default selection in the web UI.

3. **Create locale files**
   - For each language you support, create a subfolder like `locales/en/`.
   - Add a `personas.yaml` file with this structure:
     ```yaml
     personas:
       LEAH:
         name: "LEAH"
         description: "Short blurb for the web UI"
         prompt: |-
           Multi-line system prompt …
     ```
   - Optional keys (e.g., `drink`, `greeting`) are forwarded to the UI unchanged.

4. **Add media (optional)**
   - Create `static/personas/<NAME>/` for every persona.
   - `thumb.webp` (square, ~256 px) is used in selection grids.
   - `full.webp` (larger, ~512–768 px) appears in the persona details view.
   - Stick to WebP for smaller files; other formats are not converted automatically.

5. **Test the ensemble**
   - Launch the project with the CLI flag:
     ```bash
     python src/launch.py -e my_ensemble
     ```
   - Alternatively, set `ensemble: "my_ensemble"` in `config.yaml` if you prefer not to pass the flag.
   - Verify that all personas show up and answer in both terminal and web UI (if enabled).

6. **Run automated tests (optional)**
   - Execute `pytest` to ensure the existing test suite still passes.
   - For CI pipelines, consider switching to the dummy backend (`core.backend: "dummy"`).

## Time budget

| Variant | Estimated time | Notes |
| --- | --- | --- |
| Without AI image generation | ~45–90 minutes | Create structure, write prompts, run smoke tests |
| With AI image generation | ~60–120 minutes | Additional time for prompting, generation, touch-ups, and WebP conversion |

The estimates assume 3–4 personas. Complex storytelling prompts or manual image editing can extend the timeline.

## Additional tips

- Keep persona names consistent across `personas_base.yaml`, locale files, and image folders.
- Track changes with version control so prompt tweaks remain traceable.
- Document persona-specific specialities (e.g., extra tools or context sources) for future maintenance.
- Review safety settings (PII filter, prompt guard) when personas intentionally push boundaries.
