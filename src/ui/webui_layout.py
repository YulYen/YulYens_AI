import gradio as gr


def build_ui(
    *,
    persona_thumbnail_path_fn,
    persona_info,
    broadcast_enabled,
    project_title,
    choose_persona_txt,
    persona_btn_suffix,
    input_placeholder,
    new_chat_label,
    send_button_label,
    ask_all_button_label,
    ask_all_title,
    ask_all_input_placeholder,
    self_talk_button_label,
    self_talk_title,
    self_talk_description,
    self_talk_persona_a_label,
    self_talk_persona_b_label,
    self_talk_prompt_label,
    self_talk_start_label,
    self_talk_prompt_placeholder,
    load_label,
    save_button_label,
    advanced_label,
    model_dropdown_label,
    model_hint,
    model_choices,
    model_value,
    mic_label,
    briefing_label,
):
    with gr.Blocks() as demo:
        selected_persona_state = gr.Textbox(value="", visible=False)

        gr.HTML(
            """
                <style>
                .persona-row { gap:24px; }
                .persona-card {
                    border:1px solid #e3e7ed;
                    border-radius:10px;
                    padding:12px;
                    text-align:center;
                    height:100%;
                }
                /* Gradio-Group wickelt Inhalte in .styler; dort das Flex-Layout setzen,
                   damit die Buttons aller Karten unten bündig abschließen. */
                .persona-card > .styler {
                    display:flex;
                    flex-direction:column;
                    height:100%;
                }
                .persona-card > .styler > button { margin-top:auto; }
                /* !important: Gradios komponenten-eigene img-Styles sind spezifischer */
                .persona-card img {
                    max-width: 100%;
                    height: 150px !important;
                    object-fit: contain;
                    display:inline-block;
                }
                .persona-card .name { font-weight:600; margin:6px 0 4px; font-size:1.1rem; }
                .persona-card .desc { font-size:0.9rem; margin-bottom:8px; }
                .chat-input-row { align-items: stretch; gap:12px; }
                .new-chat-btn button { margin-top: 12px; }
                .ask-all-btn button { height: 100%; font-size: 1rem; padding: 14px 18px; }
                .ask-all-strip { justify-content: center; align-items: center; gap: 12px; }
                .ask-all-strip img { max-width: 250px; max-height: 160px; object-fit: contain; }
                .persona-header-row { justify-content: space-between; align-items: center; }
                /* Chat-Header: Abstand zwischen Bild und Text, Text vertikal mittig.
                   !important nötig, weil Gradios Row-Styles (gap:1px) sonst gewinnen. */
                .focus-row { gap:16px !important; }
                .focus-row > div { justify-content: center; }
                /* Ask-All-Ergebnisse: Abschnitt pro Persona, dezent gerahmt */
                .ask-all-results {
                    border: 1px solid #e3e7ed;
                    border-radius: 10px;
                    padding: 4px 16px 12px;
                    background: var(--background-fill-primary, #fff);
                }
                .ask-all-results h3 { margin: 14px 0 6px; }
                /* Profi-Option (Modell-Wechsel): bewusst dezent gehalten */
                .advanced-accordion { margin-top: 8px; }
                .advanced-hint { font-size: 0.85rem; opacity: 0.7; }
                /* Mikrofon (STT) kompakt neben dem Eingabefeld halten */
                .mic-input { max-height: 110px; }
                </style>
            """
        )
        gr.Markdown(f"# {project_title}")

        with gr.Group(visible=True) as grid_group:
            with gr.Row(elem_classes="persona-header-row", equal_height=True):
                gr.Markdown(choose_persona_txt)
            with gr.Row(elem_classes="persona-row", equal_height=True):
                persona_buttons = []
                for key, p in persona_info.items():
                    with gr.Column(scale=1, min_width=170):
                        with gr.Group(elem_classes="persona-card"):
                            gr.Image(
                                persona_thumbnail_path_fn(p["name"]),
                                show_label=False,
                                container=False,
                                show_download_button=False,
                                show_fullscreen_button=False,
                                elem_classes="persona-img",
                            )
                            gr.Markdown(
                                f"<div class='name'>{p['name']}</div>"
                                f"<div class='desc'>{p['description']}</div>"
                            )
                            btn = gr.Button(
                                f"{p['name']}{persona_btn_suffix}",
                                variant="secondary",
                            )
                            persona_buttons.append((key, btn))
                with gr.Column(scale=1, min_width=170):
                    with gr.Group(elem_classes="persona-card"):
                        gr.Image(
                            "static/ST.png",
                            show_label=False,
                            container=False,
                            show_download_button=False,
                            show_fullscreen_button=False,
                            elem_classes="persona-img",
                        )
                        gr.Markdown(
                            f"<div class='name'>{self_talk_title}</div>"
                            f"<div class='desc'>{self_talk_description}</div>"
                        )
                        self_talk_card_btn = gr.Button(
                            self_talk_button_label, variant="secondary"
                        )

                if broadcast_enabled:
                    with gr.Column(scale=1, min_width=170):
                        with gr.Group(elem_classes="persona-card"):
                            gr.Image(
                                "static/ALL.png",
                                show_label=False,
                                container=False,
                                show_download_button=False,
                                show_fullscreen_button=False,
                                elem_classes="persona-img",
                            )
                            gr.Markdown(
                                f"<div class='name'>{ask_all_title}</div>"
                                f"<div class='desc'>{ask_all_input_placeholder}</div>"
                            )
                            ask_all_card_btn = gr.Button(
                                ask_all_button_label, variant="primary"
                            )
                else:
                    ask_all_card_btn = None

            with gr.Row():
                with gr.Column(scale=2, min_width=300):
                    load_input = gr.File(
                        label=load_label,
                        file_types=[".json"],
                        type="filepath",
                    )
                with gr.Column(scale=3, min_width=300):
                    load_status = gr.Markdown("", visible=False)

            # Profi-Option, zugeklappt: Modell nur für diese Sitzung wechseln.
            with gr.Accordion(
                advanced_label, open=False, elem_classes="advanced-accordion"
            ):
                model_dropdown = gr.Dropdown(
                    choices=model_choices,
                    value=model_value,
                    label=model_dropdown_label,
                    interactive=len(model_choices) > 1,
                )
                gr.Markdown(model_hint, elem_classes="advanced-hint")
                model_status = gr.Markdown("", visible=False)

        with gr.Group(visible=False) as focus_group:
            with gr.Row(elem_classes="focus-row"):
                with gr.Column(scale=1):
                    focus_img = gr.Image(
                        show_label=False,
                        container=False,
                        show_download_button=False,
                        show_fullscreen_button=False,
                    )
                with gr.Column(scale=3):
                    focus_md = gr.Markdown("")
            gr.Markdown("---")

        greeting_md = gr.Markdown("", visible=False)
        chatbot = gr.Chatbot(label="", visible=False)
        with gr.Row():
            download_btn = gr.Button(
                save_button_label,
                variant="secondary",
                visible=False,
            )
            briefing_btn = gr.Button(
                briefing_label,
                variant="secondary",
                visible=False,
            )
            download_file = gr.File(visible=False)
        save_status = gr.Markdown("", visible=False)
        with gr.Row(elem_classes="chat-input-row"):
            input_box = gr.Textbox(
                show_label=False,
                placeholder=input_placeholder,
                visible=False,
                interactive=False,
                scale=5,
            )
            send_btn = gr.Button(
                send_button_label,
                variant="primary",
                visible=False,
                interactive=False,
                scale=1,
                min_width=140,
            )
            # Spracheingabe (STT, optional): unsichtbar bis eine Persona gewählt
            # ist UND faster-whisper installiert ist (WebUI.stt_available).
            mic_audio = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label=mic_label,
                visible=False,
                scale=2,
                min_width=200,
                show_download_button=False,
                waveform_options=gr.WaveformOptions(show_recording_waveform=False),
                elem_classes="mic-input",
            )
        new_chat_btn = gr.Button(
            new_chat_label, visible=False, elem_classes="new-chat-btn"
        )

        with gr.Group(visible=False) as self_talk_group:
            gr.Markdown(f"## {self_talk_title}")
            self_talk_status = gr.Markdown("", visible=False)
            with gr.Row():
                self_talk_persona_a = gr.Dropdown(
                    choices=[p["name"] for p in persona_info.values()],
                    label=self_talk_persona_a_label,
                    interactive=True,
                )
                self_talk_persona_b = gr.Dropdown(
                    choices=[p["name"] for p in persona_info.values()],
                    label=self_talk_persona_b_label,
                    interactive=True,
                )
            self_talk_prompt = gr.Textbox(
                label=self_talk_prompt_label,
                placeholder=self_talk_prompt_placeholder,
                interactive=True,
            )
            self_talk_start_btn = gr.Button(self_talk_start_label, variant="primary")

        with gr.Group(visible=False) as ask_all_group:
            gr.Markdown(f"## {ask_all_title}")
            with gr.Row(elem_classes="ask-all-strip"):
                if broadcast_enabled:
                    gr.Image(
                        "static/ALL.png",
                        show_label=False,
                        container=False,
                        show_download_button=False,
                        show_fullscreen_button=False,
                    )
                for p in persona_info.values():
                    gr.Image(
                        persona_thumbnail_path_fn(p["name"]),
                        show_label=False,
                        container=False,
                        show_download_button=False,
                        show_fullscreen_button=False,
                    )
            ask_all_status = gr.Markdown("", visible=False)
            ask_all_question = gr.Textbox(
                show_label=False,
                placeholder=ask_all_input_placeholder,
                interactive=True,
            )
            with gr.Row(elem_classes="chat-input-row"):
                ask_all_submit = gr.Button(
                    send_button_label,
                    variant="primary",
                )
                ask_all_new_chat = gr.Button(
                    new_chat_label,
                    elem_classes="new-chat-btn",
                )
            # Bewusst Markdown statt gr.Dataframe: die Dataframe-Komponente
            # verliert in Gradio 4.44 Streaming-Updates aus Generatoren
            # (Frontend friert nach den ersten Yields ein).
            ask_all_results = gr.Markdown(
                "",
                visible=False,
                elem_classes="ask-all-results",
            )
        history_state = gr.State([])
        meta_state = gr.State({})

    components = {
        "demo": demo,
        "selected_persona_state": selected_persona_state,
        "grid_group": grid_group,
        "focus_group": focus_group,
        "focus_img": focus_img,
        "focus_md": focus_md,
        "greeting_md": greeting_md,
        "chatbot": chatbot,
        "input_box": input_box,
        "send_btn": send_btn,
        "new_chat_btn": new_chat_btn,
        "download_btn": download_btn,
        "download_file": download_file,
        "save_status": save_status,
        "persona_buttons": persona_buttons,
        "history_state": history_state,
        "meta_state": meta_state,
        "ask_all_group": ask_all_group,
        "ask_all_results": ask_all_results,
        "ask_all_question": ask_all_question,
        "ask_all_submit": ask_all_submit,
        "ask_all_new_chat": ask_all_new_chat,
        "ask_all_status": ask_all_status,
        "ask_all_card_btn": ask_all_card_btn,
        "self_talk_card_btn": self_talk_card_btn,
        "self_talk_group": self_talk_group,
        "self_talk_status": self_talk_status,
        "self_talk_persona_a": self_talk_persona_a,
        "self_talk_persona_b": self_talk_persona_b,
        "self_talk_prompt": self_talk_prompt,
        "self_talk_start_btn": self_talk_start_btn,
        "load_input": load_input,
        "load_status": load_status,
        "model_dropdown": model_dropdown,
        "model_status": model_status,
        "mic_audio": mic_audio,
        "briefing_btn": briefing_btn,
    }
    return demo, components
