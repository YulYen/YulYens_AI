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
    broadcast_table_persona_label,
    broadcast_table_answer_label,
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
                }
                .persona-card img {
                    max-width: 100%;
                    height: auto;
                    display:inline-block;
                }
                .persona-card .name { font-weight:600; margin:6px 0 4px; font-size:1.1rem; }
                .persona-card .desc { font-size:0.9rem; margin-bottom:8px; }
                .chat-input-row { align-items: stretch; gap:12px; }
                .new-chat-btn button { margin-top: 12px; }
                .ask-all-btn button { height: 100%; font-size: 1rem; padding: 14px 18px; }
                .ask-all-strip { justify-content: center; gap: 12px; }
                .ask-all-strip img { max-width: 250px; max-height: 250px; object-fit: contain; }
                .persona-header-row { justify-content: space-between; align-items: center; }
                </style>
            """
        )
        gr.Markdown(f"# {project_title}")

        with gr.Group(visible=True) as grid_group:
            with gr.Row(elem_classes="persona-header-row", equal_height=True):
                gr.Markdown(choose_persona_txt)
                ask_all_btn = None
            with gr.Row(elem_classes="persona-row", equal_height=True):
                persona_buttons = []
                for key, p in persona_info.items():
                    with gr.Column(scale=1, min_width=220):
                        with gr.Group(elem_classes="persona-card"):
                            gr.Image(
                                persona_thumbnail_path_fn(p["name"]),
                                show_label=False,
                                container=False,
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
                with gr.Column(scale=1, min_width=220):
                    with gr.Group(elem_classes="persona-card"):
                        gr.Markdown(
                            f"<div class='name'>{self_talk_title}</div>"
                            f"<div class='desc'>{self_talk_description}</div>"
                        )
                        self_talk_card_btn = gr.Button(
                            self_talk_button_label, variant="secondary"
                        )

                if broadcast_enabled:
                    with gr.Column(scale=1, min_width=220):
                        with gr.Group(elem_classes="persona-card"):
                            gr.Image(
                                "static/ALL.png",
                                show_label=False,
                                container=False,
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

        with gr.Group(visible=False) as focus_group:
            with gr.Row():
                with gr.Column(scale=1):
                    focus_img = gr.Image(show_label=False, container=False)
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
            download_file = gr.File(visible=False)
        save_status = gr.Markdown("", visible=False)
        with gr.Row(elem_classes="chat-input-row"):
            input_box = gr.Textbox(
                show_label=False,
                placeholder=input_placeholder,
                visible=False,
                interactive=False,
            )
            send_btn = gr.Button(
                send_button_label,
                variant="primary",
                visible=False,
                interactive=False,
            )
        new_chat_btn = gr.Button(new_chat_label, visible=False, elem_classes="new-chat-btn")


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
                    )
                for p in persona_info.values():
                    gr.Image(
                        persona_thumbnail_path_fn(p["name"]),
                        show_label=False,
                        container=False,
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
            ask_all_results = gr.Dataframe(
                headers=[broadcast_table_persona_label, broadcast_table_answer_label],
                visible=False,
                datatype=["str", "str"],
                wrap=True,
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
        "ask_all_btn": ask_all_btn,
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
    }
    return demo, components
