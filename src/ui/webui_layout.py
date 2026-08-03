import json

import gradio as gr
from ui.session import SessionContext

# Theme-Umschalter (#69). Der Wechsel läuft **vollständig im Browser** — genau
# das ist der Fix: die Vorgängerfassung waren zwei `<a href="?__theme=…">`, also
# ein voller Seitenreload. Der bringt einen neuen `session_hash`, und damit ist
# jeder `gr.State` (Persona, Streamer, `conversation_state`, Gast) neu — ein
# kosmetischer Klick warf getippten Text und das laufende Gespräch weg.
#
# Im mitgelieferten Gradio-Bundle ist Dark-Mode nichts weiter als die Klasse
# `dark` am `<body>` (Funktion `Ue` in `assets/Index-*.js`). Die setzen wir
# selbst; der Server erfährt davon nichts und muss es auch nicht.
THEME_STORAGE_KEY = "yulyen-theme"
THEME_TOGGLE_ELEM_ID = "theme-toggle"


def _js_str(value: str) -> str:
    """String -> JS-Literal. `ensure_ascii=False` haelt Emoji lesbar im Skript."""
    return json.dumps(value, ensure_ascii=False)


def _theme_helpers_js(light_label: str, dark_label: str) -> str:
    """Gemeinsamer Rumpf beider Skripte — beide müssen für sich lauffähig sein.

    Der Umschalter darf sich nicht darauf verlassen, dass das Lade-Skript
    vorher lief: sonst wäre ein Klick vor dem Ende des Ladens wirkungslos.
    """
    return f"""
        const KEY = {_js_str(THEME_STORAGE_KEY)};
        // Der Knopf bietet immer den *anderen* Zustand an.
        const OTHER_LABEL = {{
            dark: {_js_str(light_label)},
            light: {_js_str(dark_label)},
        }};
        const current = () =>
            document.body.classList.contains("dark") ? "dark" : "light";
        const apply = (mode) => {{
            const dark = mode === "dark";
            document.body.classList.toggle("dark", dark);
            // Eingebettet hängt Gradio die Klasse ans <gradio-app> statt an
            // den Body; beides zu setzen ist billiger als die Fallunterscheidung.
            const app = document.querySelector("gradio-app");
            if (app) app.classList.toggle("dark", dark);
            const host = document.getElementById({_js_str(THEME_TOGGLE_ELEM_ID)});
            const btn =
                host && (host.tagName === "BUTTON" ? host : host.querySelector("button"));
            if (btn) btn.textContent = OTHER_LABEL[mode];
        }};
        const remember = (mode) => {{
            // Privater Modus wirft hier — die Wahl gilt dann nur für diese Seite.
            try {{ localStorage.setItem(KEY, mode); }} catch (e) {{}}
        }};
        const remembered = () => {{
            try {{
                const stored = localStorage.getItem(KEY);
                return stored === "dark" || stored === "light" ? stored : null;
            }} catch (e) {{ return null; }}
        }};
    """


def theme_restore_js(light_label: str, dark_label: str) -> str:
    """Läuft beim Laden der Seite — seit Gradio 6 über `launch(js=…)`.

    **Bewusst ein reiner Anweisungsblock, keine Pfeilfunktion.** Gradio 5
    erwartete am Blocks-Konstruktor ein `() => {…}` und rief es auf; Gradio 6
    führt den String direkt aus und **ignoriert eine Pfeilfunktion
    stillschweigend** — sie wird ausgewertet, aber nie gerufen. Im Browser
    gemessen: mit Pfeilfunktion lief der Rumpf null Mal, als nackter Block
    einmal. Der Umschalter am Knopf (`theme_toggle_js`) braucht weiterhin die
    Funktionsform, denn dort ist es ein Event-Handler.

    Der `setTimeout` ist kein Zieren: Gradio setzt sein eigenes Theme während
    der Initialisierung. Wer davor schreibt, verliert oder flackert.
    """
    return f"""
        {_theme_helpers_js(light_label, dark_label)}
        setTimeout(function () {{ apply(remembered() || current()); }}, 0);
    """


def theme_toggle_js(light_label: str, dark_label: str) -> str:
    """Läuft beim Klick auf den Umschalter — ohne Serverrunde, ohne Reload."""
    return f"""
        () => {{
            {_theme_helpers_js(light_label, dark_label)}
            const next = current() === "dark" ? "light" : "dark";
            remember(next);
            apply(next);
        }}
    """


# Icons der Funktionskarten (#70). Vorher stand `static/YUL_YEN.png` **zweimal**
# auf der Startseite — als Bild der Karte „Gast anlegen" und der Karte
# „Verlauf". Beide sind Funktionen, keine Personen; dasselbe Porträt zweimal
# neben den vier Persona-Karten liest sich wie zwei weitere Gesprächspartner.
# `ST.png` und `ALL.png` waren nicht dasselbe Bild, aber dieselbe Sorte Fehler:
# gezeichnete Figuren neben gezeichneten Figuren. Die vier Funktionskarten
# tragen jetzt Strich-Icons, die vier Persona-Karten ihre Porträts — der
# Unterschied ist damit auf einen Blick sichtbar (das ist die Diagnose aus #68).
#
# Inline-SVG statt `gr.Image`: skaliert scharf, nimmt über `currentColor` das
# Theme mit (#69) und spart pro Karte eine Gradio-Komponente samt Datei-Endpunkt.
# `aria-hidden`, weil direkt darunter derselbe Sachverhalt als Text steht —
# ein Screenreader soll ihn nicht zweimal vorlesen.
CARD_ICONS = {
    # Zwei Sprechblasen, die einander antworten.
    "self_talk": """
        <rect x="2.75" y="4" width="12.5" height="9" rx="2.5"/>
        <path d="M6.5 13v3.2L10 13"/>
        <rect x="8.75" y="11" width="12.5" height="9" rx="2.5"/>
        <path d="M17.5 20v3.2L14 20"/>
    """,
    # Theatermaske.
    "guest": """
        <path d="M4 3.75h16v7.25a8 8 0 0 1-16 0V3.75z"/>
        <path d="M8.5 9.25h2M13.5 9.25h2"/>
        <path d="M9 13.5c.9 1 2 1.5 3 1.5s2.1-.5 3-1.5"/>
    """,
    # Archivkasten mit Deckel.
    "history": """
        <rect x="2.75" y="3.75" width="18.5" height="4.5" rx="1.25"/>
        <path d="M4.75 8.25v11a1.25 1.25 0 0 0 1.25 1.25h12a1.25 1.25 0 0 0 1.25-1.25v-11"/>
        <path d="M10 12.5h4"/>
    """,
    # Eine Frage, die sich auf mehrere verteilt.
    "ask_all": """
        <rect x="7" y="2.5" width="10" height="7.5" rx="2.25"/>
        <path d="M12 10v3"/>
        <path d="M4.5 17.5v-3a1.5 1.5 0 0 1 1.5-1.5h12a1.5 1.5 0 0 1 1.5 1.5v3"/>
        <path d="M12 13v4.5"/>
        <rect x="2.5" y="17.5" width="4" height="4" rx="1.25"/>
        <rect x="10" y="17.5" width="4" height="4" rx="1.25"/>
        <rect x="17.5" y="17.5" width="4" height="4" rx="1.25"/>
    """,
}


def card_icon_html(name: str) -> str:
    """Das Icon einer Funktionskarte als fertiges Inline-SVG.

    Ein unbekannter Name ist ein Tippfehler und soll hier auffallen, nicht als
    leere Karte im Browser.
    """
    return (
        '<div class="card-icon">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">'
        f"{CARD_ICONS[name]}"
        "</svg>"
        "</div>"
    )


# Single source of truth for the order of the "switch view" output components.
# Every handler bound to these outputs builds a dict keyed by these names and
# resolves it via as_persona_outputs() — never by positional index.
PERSONA_OUTPUT_KEYS = (
    "selected_persona_state",
    "grid_group",
    "focus_group",
    "focus_img",
    "focus_md",
    "greeting_md",
    "chatbot",
    "input_box",
    "send_btn",
    "new_chat_btn",
    "download_btn",
    "download_file",
    "save_status",
    "history_state",
    "meta_state",
    "ask_all_group",
    "ask_all_results",
    "ask_all_question",
    "ask_all_submit",
    "ask_all_new_chat",
    "ask_all_status",
    "load_status",
    "self_talk_group",
    "self_talk_status",
    "self_talk_persona_a",
    "self_talk_persona_b",
    "self_talk_prompt",
    "self_talk_start_btn",
    "mic_audio",
    "briefing_btn",
    "read_aloud_btn",
    "tts_audio",
    "stop_btn",
    "regenerate_btn",
    "sources_accordion",
    "sources_md",
    "ask_all_sources_accordion",
    "ask_all_sources_md",
    "status_md",
    "guest_group",
    "guest_status",
    "conversation_state",
    "history_group",
    "history_status",
    "history_pick",
    "history_preview",
    "history_confirm",
)

# Ausgaben jedes streamenden Handlers, in dieser Reihenfolge. Die Quellen (#32)
# reisen bewusst in denselben Yields mit statt als eigenes .then()-Event davor —
# das hätte den ersten Token um Sekunden verzögert (siehe _with_stream_controls).
STREAM_OUTPUT_KEYS = (
    "input_box",
    "chatbot",
    "history_state",
    "sources_accordion",
    "sources_md",
    "status_md",
)

# Was _with_stream_controls hinter STREAM_OUTPUT_KEYS anhängt.
STREAM_CONTROL_KEYS = ("send_btn", "stop_btn", "regenerate_btn")

# Reihenfolge der Ask-All-Ausgaben — dieselbe, die _ask_all_state aufbaut.
ASK_ALL_OUTPUT_KEYS = (
    "ask_all_question",
    "ask_all_status",
    "ask_all_results",
    "ask_all_submit",
    "ask_all_new_chat",
    "ask_all_sources_accordion",
    "ask_all_sources_md",
)


def as_persona_outputs(updates: dict) -> tuple:
    """Ein benanntes Update-Dict in die Reihenfolge von PERSONA_OUTPUT_KEYS bringen.

    Die Keys stehen hier statt bei den Handlern, weil die Komponenten, die sie
    benennen, hier gebaut werden: ein Key ohne Komponente fällt so beim Lesen
    einer Datei auf statt beim Klicken im Browser.
    """
    unknown = set(updates) - set(PERSONA_OUTPUT_KEYS)
    if unknown:
        raise KeyError(f"Unknown persona-output keys: {sorted(unknown)}")
    return tuple(updates[key] for key in PERSONA_OUTPUT_KEYS)


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
    read_aloud_label,
    stop_label,
    regenerate_label,
    sources_label,
    theme_light_label,
    theme_dark_label,
    guest_card_label,
    guest_title,
    guest_description,
    guest_name_label,
    guest_prompt_label,
    guest_prompt_placeholder,
    guest_temperature_label,
    guest_start_label,
    history_card_label,
    history_title,
    history_description,
    history_pick_label,
    history_open_label,
    history_export_label,
    history_delete_label,
    history_confirm_label,
    file_exchange_enabled,
    history_enabled,
):
    # Kein `js=` mehr am Blocks-Konstruktor: Gradio 6 hat die Parameter nach
    # `launch()` verschoben. Es *warnt* zwar, aber `demo.js` bleibt `None` —
    # das Lade-Skript des Theme-Umschalters (#69) hörte damit still auf zu
    # wirken. Gemeldet hat das nur der Verdrahtungstest; im Browser wäre es
    # als „Theme wird nach dem Neuladen vergessen" aufgefallen, also spät.
    # Das Skript reicht `WebUI._start_server` an `launch()` weiter.
    with gr.Blocks() as demo:
        selected_persona_state = gr.Textbox(value="", visible=False)

        gr.HTML(
            """
                <style>
                .persona-row { gap:24px; }
                .persona-card {
                    border:1px solid var(--border-color-primary, #e3e7ed);
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
                /* Icons der Funktionskarten (#70): dieselbe Höhe wie die
                   Porträts der Persona-Karten, sonst schließen die Buttons
                   nicht mehr bündig ab. `currentColor` nimmt das Theme mit. */
                .card-icon {
                    height: 150px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .card-icon svg {
                    height: 96px;
                    width: 96px;
                    color: var(--body-text-color, currentColor);
                    opacity: 0.75;
                }
                .persona-card:hover .card-icon svg { opacity: 1; }
                /* In der Ask-All-Leiste steht das Icon neben Porträts — dort
                   ist die Kartenhöhe nicht der Maßstab. */
                .ask-all-strip .card-icon { height: auto; }
                .ask-all-strip .card-icon svg { height: 72px; width: 72px; }
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
                    border: 1px solid var(--border-color-primary, #e3e7ed);
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
                /* Vorlesen-Player (TTS): schmal, ohne Beschriftung */
                .tts-audio { max-height: 80px; }
                /* Quellen (#32): der injizierte Text kann lang sein — scrollen
                   lassen, statt den Chat nach unten zu schieben. */
                .wiki-sources .wiki-sources-body { max-height: 420px; overflow-y: auto; }
                .wiki-sources blockquote {
                    font-size: 0.9rem;
                    white-space: pre-wrap;
                    opacity: 0.85;
                }
                /* Statuszeile (#36): Kennzahlen, keine Ansage — klein und leise */
                .chat-status {
                    font-size: 0.8rem;
                    opacity: 0.7;
                    font-family: var(--font-mono, monospace);
                }
                /* Theme-Umschalter (#36/#69): dezent oben rechts, stört den Kopf
                   nicht. Ein Knopf statt zweier Links — er zeigt an, wohin es
                   geht, statt beide Zustände gleichzeitig anzubieten. */
                .theme-switch { justify-content: flex-end; }
                .theme-switch button {
                    flex: 0 0 auto;
                    width: auto;
                    min-width: 0;
                    font-size: 0.85rem;
                    padding: 4px 12px;
                    opacity: 0.75;
                }
                .theme-switch button:hover { opacity: 1; }
                </style>
            """
        )
        # Theme-Umschalter (#69). Der Startwert ist eine Annahme — der Server
        # weiß nicht, was der Browser gerade anzeigt; `theme_restore_js` setzt
        # die Beschriftung beim Laden gerade.
        with gr.Row(elem_classes="theme-switch"):
            theme_toggle_btn = gr.Button(
                theme_dark_label,
                size="sm",
                variant="secondary",
                elem_id=THEME_TOGGLE_ELEM_ID,
            )
        # Bewusst hier gebunden statt in `_bind_events`: es gibt keinen
        # Python-Handler, der gebunden werden könnte. `fn=None` heißt für
        # Gradio "nur das Skript, keine Serverrunde" (`backend_fn: false`) —
        # und genau daran hängt der Fix: kein Request, kein Reload, keine
        # neue Sitzung.
        theme_toggle_btn.click(
            fn=None,
            inputs=None,
            outputs=None,
            js=theme_toggle_js(theme_light_label, theme_dark_label),
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
                                buttons=[],
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
                        gr.HTML(card_icon_html("self_talk"))
                        gr.Markdown(
                            f"<div class='name'>{self_talk_title}</div>"
                            f"<div class='desc'>{self_talk_description}</div>"
                        )
                        self_talk_card_btn = gr.Button(
                            self_talk_button_label, variant="secondary"
                        )

                with gr.Column(scale=1, min_width=170):
                    with gr.Group(elem_classes="persona-card"):
                        gr.HTML(card_icon_html("guest"))
                        gr.Markdown(
                            f"<div class='name'>{guest_title}</div>"
                            f"<div class='desc'>{guest_description}</div>"
                        )
                        guest_card_btn = gr.Button(
                            guest_card_label, variant="secondary"
                        )

                # Ohne Ablage keine Verlauf-Karte (#72) — sie könnte sich nie füllen.
                if history_enabled:
                    with gr.Column(scale=1, min_width=170):
                        with gr.Group(elem_classes="persona-card"):
                            gr.HTML(card_icon_html("history"))
                            gr.Markdown(
                                f"<div class='name'>{history_title}</div>"
                                f"<div class='desc'>{history_description}</div>"
                            )
                            history_card_btn = gr.Button(
                                history_card_label, variant="secondary"
                            )
                else:
                    history_card_btn = None

                if broadcast_enabled:
                    with gr.Column(scale=1, min_width=170):
                        with gr.Group(elem_classes="persona-card"):
                            gr.HTML(card_icon_html("ask_all"))
                            gr.Markdown(
                                f"<div class='name'>{ask_all_title}</div>"
                                f"<div class='desc'>{ask_all_input_placeholder}</div>"
                            )
                            ask_all_card_btn = gr.Button(
                                ask_all_button_label, variant="primary"
                            )
                else:
                    ask_all_card_btn = None

            with gr.Row(visible=file_exchange_enabled):
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
                        buttons=[],
                    )
                with gr.Column(scale=3):
                    focus_md = gr.Markdown("")
            gr.Markdown("---")

        greeting_md = gr.Markdown("", visible=False)
        # `messages` seit #61a: das Paarformat ist in Gradio 5 deprecated und
        # in 6 ersatzlos weg — den Parameter `type` gibt es dort nicht mehr,
        # er steht hier also nicht. Der Vote-Index (#65) hängt daran:
        # `evt.index` ist ein flacher Index, kein `[row, col]`; siehe
        # `_on_chat_like`. `buttons` ersetzt `show_copy_button` (Gradio 6).
        chatbot = gr.Chatbot(label="", visible=False, buttons=["copy"])
        # Quellen-Transparenz (#32): zugeklappt direkt unter dem Chat. Zeigt den
        # Text, den das Modell tatsächlich als Kontext bekommen hat — inklusive
        # der Länge, damit ein an wiki.snippet_limit gekürzter Artikel als
        # solcher erkennbar ist.
        with gr.Accordion(
            sources_label, open=False, visible=False, elem_classes="wiki-sources"
        ) as sources_accordion:
            sources_md = gr.Markdown("", elem_classes="wiki-sources-body")
        # Statuszeile (#36): Kontext-Füllstand und Tempo der letzten Antwort.
        status_md = gr.Markdown("", visible=False, elem_classes="chat-status")
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
            read_aloud_btn = gr.Button(
                read_aloud_label,
                variant="secondary",
                visible=False,
            )
            # Regenerate steht bei den Sekundär-Aktionen; Stop gehört in die
            # Eingabezeile, weil es den laufenden Stream betrifft (#35).
            regenerate_btn = gr.Button(
                regenerate_label,
                variant="secondary",
                visible=False,
            )
            download_file = gr.File(visible=False)
        save_status = gr.Markdown("", visible=False)
        tts_audio = gr.Audio(
            visible=False,
            autoplay=True,
            interactive=False,
            show_label=False,
            buttons=[],
            elem_classes="tts-audio",
        )
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
            # Nimmt den Platz von send_btn ein, solange gestreamt wird.
            stop_btn = gr.Button(
                stop_label,
                variant="stop",
                visible=False,
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
                buttons=[],
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

        # Gast-Persona (#28): lebt nur in der Sitzung — kein YAML, kein Reload.
        with gr.Group(visible=False) as guest_group:
            gr.Markdown(f"## {guest_title}")
            guest_status = gr.Markdown("", visible=False)
            guest_name = gr.Textbox(label=guest_name_label, interactive=True)
            guest_prompt = gr.Textbox(
                label=guest_prompt_label,
                placeholder=guest_prompt_placeholder,
                lines=5,
                interactive=True,
            )
            guest_temperature = gr.Slider(
                minimum=0.0,
                maximum=1.5,
                value=0.7,
                step=0.05,
                label=guest_temperature_label,
                interactive=True,
            )
            guest_start_btn = gr.Button(guest_start_label, variant="primary")

        # Verlauf (#25) auf der Ablage aus #54 — bewusst ein Dropdown statt
        # gr.Dataframe: die Komponente verlor in Gradio 4.44 Updates aus
        # Generatoren und verfälschte mit Mess-Zeilen die Browser-Tests.
        # Unter Gradio 5 ist das **nicht nachgemessen** — der Wechsel stünde
        # ohnehin nur zur Debatte, wenn jemand einen Grund dafür hätte.
        with gr.Group(visible=False) as history_group:
            gr.Markdown(f"## {history_title}")
            history_status = gr.Markdown("", visible=False)
            history_pick = gr.Dropdown(
                choices=[], label=history_pick_label, interactive=True
            )
            history_preview = gr.Markdown("", elem_classes="wiki-sources-body")
            with gr.Row():
                history_open_btn = gr.Button(history_open_label, variant="primary")
                history_export_btn = gr.Button(history_export_label)
                history_delete_btn = gr.Button(history_delete_label, variant="stop")
            # Löschen ist endgültig — ein Häkchen statt eines Zwei-Klick-Tanzes
            # mit wechselnder Beschriftung, das sich niemand merken muss.
            history_confirm = gr.Checkbox(label=history_confirm_label, value=False)
            history_file = gr.File(visible=False)

        with gr.Group(visible=False) as ask_all_group:
            gr.Markdown(f"## {ask_all_title}")
            with gr.Row(elem_classes="ask-all-strip"):
                if broadcast_enabled:
                    # Dasselbe Icon wie auf der Karte — die Porträts daneben
                    # zeigen, *wer* antwortet, das Icon *was* passiert.
                    gr.HTML(card_icon_html("ask_all"), elem_classes="strip-icon")
                for p in persona_info.values():
                    gr.Image(
                        persona_thumbnail_path_fn(p["name"]),
                        show_label=False,
                        container=False,
                        buttons=[],
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
            # verlor in Gradio 4.44 Streaming-Updates aus Generatoren
            # (Frontend fror nach den ersten Yields ein). Unter Gradio 5 nicht
            # nachgemessen; Markdown trägt hier ohnehin.
            ask_all_results = gr.Markdown(
                "",
                visible=False,
                elem_classes="ask-all-results",
            )
            # Eigenes Accordion statt des Einzelchat-Accordions (#32a): das
            # sitzt außerhalb dieser Gruppe und stünde hier über dem Block.
            with gr.Accordion(
                sources_label, open=False, visible=False, elem_classes="wiki-sources"
            ) as ask_all_sources_accordion:
                ask_all_sources_md = gr.Markdown("", elem_classes="wiki-sources-body")
        history_state = gr.State([])
        meta_state = gr.State({})
        # Identität der Browser-Sitzung, beim Laden gefüllt (#53).
        user_state = gr.State("")
        # Laufendes Gespräch in der Ablage (#54) — überlebt einen
        # Streamer-Neubau, etwa beim Modellwechsel.
        conversation_state = gr.State("")
        # Persona, Streamer und Kill-Switches dieser Browser-Sitzung. Gradio
        # legt pro Sitzung eine eigene Kopie des Default-Werts an, deshalb
        # reicht es, das Objekt als Input durchzureichen und in-place zu
        # ändern — am WebUI-Singleton wären sie für alle Browser dieselben.
        session_state = gr.State(SessionContext())

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
        "user_state": user_state,
        "conversation_state": conversation_state,
        "session_state": session_state,
        "guest_card_btn": guest_card_btn,
        "guest_group": guest_group,
        "guest_status": guest_status,
        "guest_name": guest_name,
        "guest_prompt": guest_prompt,
        "guest_temperature": guest_temperature,
        "guest_start_btn": guest_start_btn,
        "history_card_btn": history_card_btn,
        "history_group": history_group,
        "history_status": history_status,
        "history_pick": history_pick,
        "history_preview": history_preview,
        "history_open_btn": history_open_btn,
        "history_export_btn": history_export_btn,
        "history_delete_btn": history_delete_btn,
        "history_confirm": history_confirm,
        "history_file": history_file,
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
        "read_aloud_btn": read_aloud_btn,
        "tts_audio": tts_audio,
        "stop_btn": stop_btn,
        "regenerate_btn": regenerate_btn,
        "sources_accordion": sources_accordion,
        "sources_md": sources_md,
        "ask_all_sources_accordion": ask_all_sources_accordion,
        "ask_all_sources_md": ask_all_sources_md,
        "status_md": status_md,
        "theme_toggle_btn": theme_toggle_btn,
    }
    return demo, components
