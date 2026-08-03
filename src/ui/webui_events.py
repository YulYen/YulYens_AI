"""Die Gradio-Events der WebUI verdrahten (#56).

333 Zeilen reine Verkabelung — sie sagen nichts darüber, *was* ein Handler
tut, nur welcher Knopf ihn ruft und welche Komponenten er bedient. Zwischen
der Handler-Logik machten sie die Klasse unlesbar; hier stehen sie am Stück
und lassen sich als Ganzes überfliegen.

Der Ort ist auch der ehrliche: `webui_layout.py` **baut** die Oberfläche,
dieses Modul **verbindet** sie, `web_ui.py` beantwortet die Klicks. Drei
Fragen, drei Dateien.

Die teuren Fehler sitzen genau hier — ein Ausgabe-Key, der in
``PERSONA_OUTPUT_KEYS`` fehlt, ein `cancels` auf ein `queue=False`-Event (das
verhindert den App-Start komplett, #35), eine `inputs=`-Liste, die nicht mehr
zur Signatur passt. Das Netz dafür ist `tests/test_web_ui_wiring.py`, und es
prüft **jede** hier gebundene Bindung.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from ui.webui_layout import (
    ASK_ALL_OUTPUT_KEYS,
    PERSONA_OUTPUT_KEYS,
    STREAM_CONTROL_KEYS,
    STREAM_OUTPUT_KEYS,
)

if TYPE_CHECKING:  # pragma: no cover - nur für die Typprüfung
    from ui.web_ui import WebUI


def bind_events(
    ui: WebUI,
    components: dict[str, Any],
    persona_info: dict[str, dict[str, Any]],
    greeting_template: str,
    input_placeholder: str,
) -> None:
    chatbot = components["chatbot"]
    input_box = components["input_box"]
    send_btn = components["send_btn"]
    new_chat_btn = components["new_chat_btn"]
    download_btn = components["download_btn"]
    download_file = components["download_file"]
    save_status = components["save_status"]
    history_state = components["history_state"]
    meta_state = components["meta_state"]
    ask_all_results = components["ask_all_results"]
    ask_all_question = components["ask_all_question"]
    ask_all_submit = components["ask_all_submit"]
    ask_all_new_chat = components["ask_all_new_chat"]
    ask_all_card_btn = components["ask_all_card_btn"]
    ask_all_outputs = [components[key] for key in ASK_ALL_OUTPUT_KEYS]
    self_talk_card_btn = components["self_talk_card_btn"]
    self_talk_status = components["self_talk_status"]
    self_talk_persona_a = components["self_talk_persona_a"]
    self_talk_persona_b = components["self_talk_persona_b"]
    self_talk_prompt = components["self_talk_prompt"]
    self_talk_start_btn = components["self_talk_start_btn"]
    load_input = components["load_input"]
    load_status = components["load_status"]
    model_dropdown = components["model_dropdown"]
    model_status = components["model_status"]
    mic_audio = components["mic_audio"]
    briefing_btn = components["briefing_btn"]
    read_aloud_btn = components["read_aloud_btn"]
    tts_audio = components["tts_audio"]
    stop_btn = components["stop_btn"]
    regenerate_btn = components["regenerate_btn"]

    # Same order as the update dicts resolved via _as_persona_outputs()
    persona_outputs = [components[key] for key in PERSONA_OUTPUT_KEYS]

    # Parameter, die aus `inputs=` kommen, stehen bewusst ohne Default da:
    # ein Handler, der stillschweigend auf einen leeren Nutzer zurückfällt,
    # schreibt Gespräche unter der falschen Identität weg.
    user_state = components["user_state"]
    # Persona, Streamer und Kill-Switches dieser Browser-Sitzung (siehe
    # ui/session.py). Steht bewusst als *erster* Input jedes Handlers, der
    # sie braucht — die Reihenfolge hier ist die Parameterreihenfolge dort.
    session_state = components["session_state"]

    # Identität einmal pro Browser-Sitzung einsammeln (#53).
    components["demo"].load(
        fn=ui._on_page_load, inputs=[], outputs=[user_state], queue=False
    )

    for key, btn in components["persona_buttons"]:
        btn.click(
            fn=partial(
                ui._on_persona_selected,
                key=key,
                persona_info=persona_info,
                greeting_template=greeting_template,
                input_placeholder=input_placeholder,
            ),
            inputs=[session_state, user_state],
            outputs=persona_outputs,
            queue=False,
        )

    load_input.upload(
        fn=partial(
            ui._on_load_conversation,
            persona_info=persona_info,
            input_placeholder=input_placeholder,
        ),
        inputs=[session_state, load_input],
        outputs=persona_outputs,
        queue=False,
    )

    # Profi-Option: .change feuert nur bei Nutzer-Interaktion, nicht beim
    # Initialwert; bewusst außerhalb der PERSONA_OUTPUT_KEYS gehalten.
    model_dropdown.change(
        fn=ui._on_model_selected,
        inputs=[session_state, model_dropdown, components["conversation_state"]],
        outputs=[model_status],
        queue=False,
    )

    # queue=True: die Whisper-Transkription dauert Sekunden (erste
    # Aufnahme lädt zusätzlich das Modell).
    mic_audio.stop_recording(
        fn=ui._on_mic_recorded,
        inputs=[mic_audio, input_box],
        outputs=[input_box, mic_audio],
        queue=True,
    )

    # Stream-Steuerung (#35): die Button-Updates reisen in denselben Yields
    # mit (siehe _with_stream_controls) — ein vorgeschaltetes Event hätte den
    # ersten Token um Sekunden verzögert. Aus demselben Grund hängen auch die
    # Quellen (#32) an denselben Yields.
    stream_buttons = [components[key] for key in STREAM_CONTROL_KEYS]
    stream_outputs = [
        *(components[key] for key in STREAM_OUTPUT_KEYS),
        *stream_buttons,
    ]

    input_submit_evt = input_box.submit(
        fn=ui.respond_streaming_with_controls,
        inputs=[session_state, input_box, chatbot, history_state],
        outputs=stream_outputs,
        queue=True,
    )

    send_click_evt = send_btn.click(
        fn=ui.respond_streaming_with_controls,
        inputs=[session_state, input_box, chatbot, history_state],
        outputs=stream_outputs,
        queue=True,
    )

    # Kein `cancels`: der Kill-Switch beendet den Generator geordnet, damit
    # die Teilantwort im Verlauf bleibt.
    stop_btn.click(
        fn=ui._on_stop_stream,
        inputs=[session_state],
        outputs=stream_buttons,
        queue=False,
    )

    regenerate_evt = regenerate_btn.click(
        fn=ui.regenerate_with_controls,
        inputs=[session_state, chatbot, history_state],
        outputs=stream_outputs,
        queue=True,
    )

    download_btn.click(
        fn=ui._on_download_conversation,
        inputs=[session_state, history_state, meta_state],
        outputs=[download_file, save_status],
        queue=False,
    )

    briefing_evt = briefing_btn.click(
        fn=ui.respond_briefing_with_controls,
        inputs=[session_state, chatbot, history_state],
        outputs=stream_outputs,
        queue=True,
    )

    # queue=True: die Piper-Synthese längerer Antworten dauert Sekunden
    read_aloud_btn.click(
        fn=ui._on_read_aloud,
        inputs=[session_state, history_state],
        outputs=[tts_audio],
        queue=True,
    )

    # Binding .like() auto-enables the thumb buttons on the chatbot (#40).
    # history_state muss mit: nur daran lässt sich eine echte Antwort von
    # einer Hinweis-Bubble unterscheiden (siehe _on_chat_like).
    chatbot.like(
        fn=ui._on_chat_like,
        inputs=[
            session_state,
            chatbot,
            meta_state,
            history_state,
            components["conversation_state"],
        ],
        outputs=[],
        queue=False,
    )

    if ask_all_card_btn is not None:
        ask_all_card_btn.click(
            fn=ui._on_show_ask_all,
            inputs=[session_state],
            outputs=persona_outputs,
            queue=False,
        )

    if components["history_card_btn"] is not None:
        components["history_card_btn"].click(
            fn=ui._on_show_history,
            inputs=[session_state, user_state],
            outputs=persona_outputs,
            queue=False,
        )

    # user_state gehört in *jeden* Verlauf-Handler: die Gesprächs-ID kommt
    # vom Client und wird von Gradio nicht gegen die Auswahlliste geprüft.
    components["history_pick"].change(
        fn=ui._on_history_selected,
        inputs=[components["history_pick"], user_state],
        outputs=[components["history_preview"]],
        queue=False,
    )

    components["history_open_btn"].click(
        fn=partial(
            ui._on_history_open,
            persona_info=persona_info,
            input_placeholder=input_placeholder,
        ),
        inputs=[session_state, components["history_pick"], user_state],
        outputs=persona_outputs,
        queue=False,
    )

    components["history_export_btn"].click(
        fn=ui._on_history_export,
        inputs=[session_state, components["history_pick"], user_state],
        outputs=[components["history_file"]],
        queue=False,
    )

    components["history_delete_btn"].click(
        fn=ui._on_history_delete,
        inputs=[
            components["history_pick"],
            components["history_confirm"],
            user_state,
        ],
        outputs=[
            components["history_pick"],
            components["history_preview"],
            components["history_status"],
            components["history_file"],
            components["history_confirm"],
        ],
        queue=False,
    )

    components["guest_card_btn"].click(
        fn=ui._on_show_guest,
        inputs=[session_state],
        outputs=persona_outputs,
        queue=False,
    )

    components["guest_start_btn"].click(
        fn=partial(
            ui._on_start_guest,
            greeting_template=greeting_template,
            input_placeholder=input_placeholder,
        ),
        inputs=[
            session_state,
            components["guest_name"],
            components["guest_prompt"],
            components["guest_temperature"],
            user_state,
        ],
        outputs=persona_outputs,
        queue=False,
    )

    if self_talk_card_btn is not None:
        self_talk_card_btn.click(
            fn=ui._on_show_self_talk,
            inputs=[session_state],
            outputs=persona_outputs,
            queue=False,
        )

    self_talk_stream_evt = self_talk_start_btn.click(
        fn=ui._on_start_self_talk,
        inputs=[
            session_state,
            self_talk_persona_a,
            self_talk_persona_b,
            self_talk_prompt,
        ],
        outputs=[
            self_talk_status,
            chatbot,
            history_state,
            input_box,
            send_btn,
            new_chat_btn,
            meta_state,
            load_status,
        ],
        queue=False,
    ).then(
        fn=ui._run_self_talk_stream,
        inputs=[session_state, chatbot, history_state],
        outputs=[chatbot, history_state],
        queue=True,
    )

    ask_all_submit_evt = ask_all_submit.click(
        fn=ui._on_submit_ask_all,
        inputs=[session_state, ask_all_question, ask_all_results],
        outputs=ask_all_outputs,
        queue=True,
    )

    ask_all_question_evt = ask_all_question.submit(
        fn=ui._on_submit_ask_all,
        inputs=[session_state, ask_all_question, ask_all_results],
        outputs=ask_all_outputs,
        queue=True,
    )

    # "New conversation" bricht laufende Streams aktiv ab (#2): das Schließen
    # des Generators löst über GeneratorExit das finally in
    # YulYenStreamingProvider.stream aus, das den LLM-Stream beendet.
    new_chat_btn.click(
        fn=ui._on_reset_to_start,
        inputs=[session_state],
        outputs=persona_outputs,
        queue=False,
        cancels=[
            input_submit_evt,
            send_click_evt,
            self_talk_stream_evt,
            briefing_evt,
            regenerate_evt,
        ],
    )

    ask_all_new_chat.click(
        fn=ui._on_reset_to_start,
        inputs=[session_state],
        outputs=persona_outputs,
        queue=False,
        cancels=[ask_all_submit_evt, ask_all_question_evt],
    )
