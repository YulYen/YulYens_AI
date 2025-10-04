import gradio as gr
import logging
from functools import partial
from pathlib import Path
from typing import Dict, List

from config.personas import system_prompts, get_drink
from core.streaming_provider import lookup_wiki_snippet, inject_wiki_context
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty
from fastapi.staticfiles import StaticFiles


_ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
_PERSONA_ASSETS_DIR = _ASSETS_ROOT / "personas"

class WebUI:
    """
    Web-Chat-Oberfläche mit Gradio.
    Bietet grafische Persona-Auswahl (mit Avatar) und einen laufenden Chatverlauf im Browser.
    Wiki-Hinweise und -Snippets werden analog zur Terminal-UI verarbeitet (Hinweis nur sichtbar, Snippet als Kontext).
    Antworten des KI-Modells werden tokenweise gestreamt und direkt im UI aktualisiert.
    """
    def __init__(self, factory, config, keyword_finder,
                 wiki_snippet_limit, wiki_mode, proxy_base,
                 web_host, web_port,
                 wiki_timeout):
        self.streamer = None  # wird später gesetzt
        self.keyword_finder = keyword_finder
        self.cfg = config
        self.factory = factory
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.web_host = web_host
        self.web_port = int(web_port)
        self.wiki_timeout = wiki_timeout
        self.bot = None  # wird später gesetzt
        self.texts = getattr(config, "texts", {}) or {}
        self._t = getattr(config, "t", getattr(self.texts, "format", None))
        if self._t is None:
            self._t = lambda key, **kwargs: key
        self._persona_assets = self._load_persona_assets()

    @staticmethod
    def _load_persona_assets() -> Dict[str, Dict[str, str]]:
        assets: Dict[str, Dict[str, str]] = {}

        for persona_dir in sorted(_PERSONA_ASSETS_DIR.glob("*")):
            if not persona_dir.is_dir():
                continue

            key = persona_dir.name.lower()
            assets[key] = {
                "thumb": f"/assets/personas/{persona_dir.name}/thumb.webp",
                "full": f"/assets/personas/{persona_dir.name}/full.webp",
            }

        return assets

    def _reset_conversation_state(self):
        return []
    
    def _handle_context_warning(self, llm_history, chat_history):

        if not context_near_limit(llm_history, self.streamer.persona_options):
            return False

        drink = get_drink(self.bot)
        warn = self._t(
            "context_wait_message", persona_name=self.bot, drink=drink
        )

        chat_history.append((None, warn))

        persona_options = getattr(self.streamer, "persona_options", {}) or {}

        num_ctx_value = persona_options.get("num_ctx")

        ctx_limit = None
        if num_ctx_value is not None:
            try:
                ctx_limit = int(num_ctx_value)
            except (TypeError, ValueError):
                logging.warning(
                    "Ungültiger 'num_ctx'-Wert für Persona %r: %r",
                    self.bot,
                    num_ctx_value,
                )

        if ctx_limit and ctx_limit > 0:
            llm_history[:] = karl_prepare_quick_and_dirty(
                llm_history, ctx_limit
            )
        else:
            logging.warning(
                "Überspringe 'karl_prepare_quick_and_dirty' für Persona %r: num_ctx=%r",
                self.bot,
                num_ctx_value,
            )

        return True


    # Streaming der Antwort (UI wird fortlaufend aktualisiert)
    def _stream_reply(self, message_history, chat_history):
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            yield None, chat_history + [(None, reply)], message_history

        # Abschluss: finalen Reply in den Verlauf übernehmen
        chat_history.append((None, reply))
        message_history.append({"role": "assistant", "content": reply})
        yield None, chat_history, message_history


    def respond_streaming(self, user_input, chat_history, history_state):

        # Schutz: Persona noch nicht gewählt → UI verhindert das, aber doppelt hält besser
        if not self.bot:
            yield "", chat_history, history_state
            return


        # 1) Eigener Verlauf für LLM ohne UI-Hinweise (und ggf. komprimiert, wenn nötig)
        llm_history = list(history_state or [])

        # 2) Eingabefeld leeren und User-Input zeigen im Chatfenster
        logging.debug("User input received (%d chars)", len(user_input))
        chat_history.append((user_input, None ))
        yield "", chat_history, llm_history


        # 3) Wiki-Hinweis + Snippet (Top-Treffer)
        wiki_hint, title, snippet = lookup_wiki_snippet(
            user_input,
            self.bot,
            self.keyword_finder,
            self.wiki_mode,
            self.proxy_base,
            self.wiki_snippet_limit,
            self.wiki_timeout,
        )

        if wiki_hint:
            # UI-Hinweis anzeigen (nicht ins LLM-Kontextfenster einfügen)
            chat_history.append((None, wiki_hint))
            yield None, chat_history, llm_history

        # 4) Optional: Wiki-Kontext injizieren
        if snippet:
            inject_wiki_context(llm_history, title, snippet)

        # 5) Nutzerfrage ans LLM
        user_message = {"role": "user", "content": user_input}
        llm_history.append(user_message)

        # 6) Kontext-Komprimierung bei Bedarf inkl. Info in Chat-History
        if self._handle_context_warning(llm_history, chat_history):
            yield None, chat_history, llm_history

        # 7) Antwort streamen
        yield from self._stream_reply(llm_history, chat_history)


    def _build_ui(self, project_title, choose_persona_txt, persona_info,
                  input_placeholder, new_chat_label):
        with gr.Blocks() as demo:
            demo.app.mount(
                "/assets",
                StaticFiles(directory=str(_ASSETS_ROOT), html=False),
                name="assets",
            )

            selected_persona_state = gr.Textbox(value="", visible=False)
            gr.Markdown(f"# {project_title}")

            gallery_items: List[List[str]] = []
            persona_keys: List[str] = []
            for key, persona in persona_info.items():
                thumb_path = persona.get("thumb_path")
                if not thumb_path:
                    continue
                gallery_items.append([thumb_path, persona["name"]])
                persona_keys.append(key)

            with gr.Group(visible=True) as grid_group:
                gr.Markdown(choose_persona_txt)
                with gr.Row(equal_height=True):
                    persona_gallery = gr.Gallery(
                        value=gallery_items,
                        show_label=False,
                        columns=3,
                        allow_preview=False,
                        elem_id="persona-gallery",
                    )
                    with gr.Column(scale=1, min_width=320):
                        with gr.Group(visible=False) as focus_group:
                            focus_img = gr.Image(show_label=False, container=False)
                            focus_md = gr.Markdown("")

            greeting_md = gr.Markdown("", visible=False)
            chatbot = gr.Chatbot(label="", visible=False)
            txt = gr.Textbox(show_label=False, placeholder=input_placeholder,
                             visible=False, interactive=False)
            clear = gr.Button(new_chat_label, visible=False)
            history_state = gr.State(self._reset_conversation_state())

        components = {
            "demo": demo,
            "selected_persona_state": selected_persona_state,
            "grid_group": grid_group,
            "persona_gallery": persona_gallery,
            "persona_keys": persona_keys,
            "focus_group": focus_group,
            "focus_img": focus_img,
            "focus_md": focus_md,
            "greeting_md": greeting_md,
            "chatbot": chatbot,
            "txt": txt,
            "clear": clear,
            "history_state": history_state,
        }
        return demo, components

    def _persona_selected_updates(self, persona_key, persona, greeting_template, model_name, input_placeholder):
        display_name = persona["name"].title()
        greeting = greeting_template.format(
            persona_name=display_name, model_name=model_name
        )
        focus_text = f"### {persona['name']}\n{persona['description']}"
        full_image_path = persona.get("full_path")

        return (
            gr.update(value=persona_key),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(value=full_image_path, visible=True),
            gr.update(value=focus_text, visible=True),
            gr.update(value=greeting, visible=True),
            gr.update(value=[], label=display_name, visible=True),
            gr.update(
                value="", visible=True, interactive=True,
                placeholder=input_placeholder
            ),
            gr.update(visible=True),
            self._reset_conversation_state(),
        )

    def _reset_ui_updates(self):
        return (
            gr.update(value=""),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(value=None, visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value=[], label="", visible=False),
            gr.update(value="", visible=False, interactive=False),
            gr.update(visible=False),
            self._reset_conversation_state(),
        )

    def _on_persona_gallery_select(
        self,
        select_data,
        persona_keys,
        persona_info,
        greeting_template,
        model_name,
        input_placeholder,
    ):
        persona_key = None

        if select_data is not None:
            value = getattr(select_data, "value", None)
            if isinstance(value, (list, tuple)) and value:
                candidate = value[-1]
                if isinstance(candidate, str):
                    persona_key = candidate.lower()

            if persona_key is None:
                index = getattr(select_data, "index", None)
                if isinstance(index, int) and 0 <= index < len(persona_keys):
                    persona_key = persona_keys[index]

        if not persona_key:
            logging.warning("Keine gültige Persona für Auswahl: %s", select_data)
            return self._reset_ui_updates()

        return self._on_persona_selected(
            persona_key,
            persona_info=persona_info,
            greeting_template=greeting_template,
            model_name=model_name,
            input_placeholder=input_placeholder,
        )

    def _on_persona_selected(self, key, persona_info, greeting_template, model_name, input_placeholder):
        persona = persona_info.get(key)
        if not persona:
            self.bot = None
            self.streamer = None
            return self._reset_ui_updates()

        self.bot = persona["name"]
        self.streamer = self.factory.get_streamer_for_persona(self.bot)
        return self._persona_selected_updates(
            key, persona, greeting_template, model_name, input_placeholder
        )

    def _on_reset_to_start(self):
        self.bot = None
        self.streamer = None
        return self._reset_ui_updates()

    def _bind_events(self, components, persona_info, model_name,
                     greeting_template, input_placeholder):
        selected_persona_state = components["selected_persona_state"]
        grid_group = components["grid_group"]
        persona_gallery = components["persona_gallery"]
        persona_keys = components["persona_keys"]
        focus_group = components["focus_group"]
        focus_img = components["focus_img"]
        focus_md = components["focus_md"]
        greeting_md = components["greeting_md"]
        chatbot = components["chatbot"]
        txt = components["txt"]
        clear = components["clear"]
        history_state = components["history_state"]

        persona_outputs = [
            selected_persona_state,
            grid_group,
            focus_group,
            focus_img,
            focus_md,
            greeting_md,
            chatbot,
            txt,
            clear,
            history_state,
        ]

        persona_gallery.select(
            fn=partial(
                self._on_persona_gallery_select,
                persona_keys=persona_keys,
                persona_info=persona_info,
                greeting_template=greeting_template,
                model_name=model_name,
                input_placeholder=input_placeholder,
            ),
            inputs=[],
            outputs=persona_outputs,
            queue=False,
        )

        txt.submit(
            fn=self.respond_streaming,
            inputs=[txt, chatbot, history_state],
            outputs=[txt, chatbot, history_state],
            queue=True,
        )

        clear.click(
            fn=self._on_reset_to_start,
            inputs=[],
            outputs=persona_outputs,
            queue=False,
        )

    def _start_server(self, demo):
        launch_kwargs = {
            "server_name": self.web_host,
            "server_port": self.web_port,
            "show_api": False,
        }

        ui_cfg = getattr(self.cfg, "ui", None)
        if ui_cfg is not None:
            if isinstance(ui_cfg, dict):
                web_cfg = ui_cfg.get("web") or {}
            else:
                web_cfg = getattr(ui_cfg, "web", {}) or {}

            if web_cfg.get("share"):
                auth_cfg = web_cfg.get("share_auth") or {}
                username = auth_cfg.get("username") or ""
                password = auth_cfg.get("password") or ""

                if username and password:
                    launch_kwargs.update({
                        "share": True,
                        "auth": (username, password),
                    })
                else:
                    logging.warning(
                        "Gradio-Share deaktiviert: Zugangsdaten fehlen trotz 'ui.web.share: true'."
                    )

        demo.launch(**launch_kwargs)

    def launch(self):
        ui = self.texts
        model_name = self.cfg.core.get("model_name")
        project_title = ui.get("project_name")
        choose_persona_txt = ui.get("choose_persona")
        new_chat_label = ui.get("new_chat")
        input_placeholder = ui.get("input_placeholder")
        greeting_template = ui.get("greeting")
        persona_info: Dict[str, Dict[str, str]] = {}
        for persona in system_prompts:
            key = persona["name"].lower()
            persona_entry = dict(persona)
            assets = self._persona_assets.get(key)

            if assets:
                persona_entry["thumb_path"] = assets["thumb"]
                persona_entry["full_path"] = assets["full"]
            else:
                persona_entry["thumb_path"] = None
                persona_entry["full_path"] = None

            persona_info[key] = persona_entry

        demo, components = self._build_ui(
            project_title,
            choose_persona_txt,
            persona_info,
            input_placeholder,
            new_chat_label,
        )
        # Gradio 4.x verlangt, dass Events innerhalb eines Blocks-Kontexts
        # gebunden werden. Durch das erneute Öffnen des Demos als Kontext
        # können wir die bestehende Struktur beibehalten und trotzdem die
        # Events korrekt registrieren.
        with demo:
            self._bind_events(
                components,
                persona_info,
                model_name,
                greeting_template,
                input_placeholder,
            )
        self._start_server(demo)
