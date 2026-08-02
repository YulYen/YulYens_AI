"""Verdrahtungstest für die Gradio-Events der WebUI.

Die Handler selbst sind gut getestet, ihre **Verkabelung** war es nicht:
`webui_layout.py` lag bei 2 % Deckung, `_bind_events` bei 0 %. Genau dort
entstehen aber die teuren Fehler — ein Ausgabe-Key, der in
``PERSONA_OUTPUT_KEYS`` fehlt, ein `cancels` auf ein `queue=False`-Event (das
verhindert den App-Start komplett, #35) oder ein Handler, dessen Signatur nicht
mehr zu seiner `inputs`-Liste passt. All das fällt erst im Browser auf.

Der Test baut die echte Oberfläche in-process: `launch()` läuft komplett durch,
nur `_start_server` wird abgefangen. Kein Server, kein Browser, kein Netz.
"""

import inspect
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from config.config_singleton import Config
from core.factory import AppFactory
from gradio.utils import get_function_params
from ui import web_ui as web_ui_module
from ui.web_ui import (
    ASK_ALL_OUTPUT_KEYS,
    PERSONA_OUTPUT_KEYS,
    STREAM_CONTROL_KEYS,
    STREAM_OUTPUT_KEYS,
    WebUI,
)
from ui.webui_layout import (
    THEME_STORAGE_KEY,
    THEME_TOGGLE_ELEM_ID,
    card_icon_html,
    theme_restore_js,
)


def _build_wired(storage_cfg: dict):
    """Baut die echte WebUI und verdrahtet sie — ohne Server."""
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "warm_up": False})
    cfg.override("wiki", {"mode": False})  # kein spaCy-Modell nötig
    cfg.override("ui", {"type": "web"})
    cfg.override("storage", storage_cfg)

    captured: dict = {}
    real_build_ui = web_ui_module.build_ui

    def _spy_build_ui(**kwargs):
        demo, components = real_build_ui(**kwargs)
        captured["components"] = components
        return demo, components

    ui = AppFactory().get_ui()
    with (
        patch.object(web_ui_module, "build_ui", _spy_build_ui),
        patch.object(
            WebUI,
            "_start_server",
            lambda self, demo: captured.__setitem__("demo", demo),
        ),
        warnings.catch_warnings(record=True) as caught,
    ):
        warnings.simplefilter("always")
        ui.launch()

    return SimpleNamespace(
        ui=ui,
        demo=captured["demo"],
        components=captured["components"],
        warnings=[str(w.message) for w in caught],
    )


@pytest.fixture(scope="module")
def wired(tmp_path_factory):
    """Die volle Oberfläche — mit Ablage, sonst fehlt der halbe Verlauf.

    Die Ablage steht hier bewusst auf *an*: ohne sie gibt es seit #72 keine
    Verlauf-Karte, und dieser Test prüfte deren Bindungen dann gar nicht mehr.
    Sie liegt in einem tmp-Verzeichnis und braucht ``shared_without_login``,
    weil die ausgelieferte Config keine Anmeldung hat.
    """
    store_file = tmp_path_factory.mktemp("store") / "conversations.sqlite3"
    yield _build_wired(
        {
            "enabled": True,
            "path": str(store_file),
            "shared_without_login": True,
        }
    )
    Config.reset_instance()


def test_the_app_still_starts_without_a_store(tmp_path):
    """Ohne Ablage fällt die Verlauf-Karte weg — und nichts bindet an sie.

    Der teure Fehler wäre ein `.click()` auf die nicht gebaute Karte: das
    scheitert erst beim Verdrahten, also beim Start der App.
    """
    try:
        wired = _build_wired({"enabled": False})
        assert wired.components["history_card_btn"] is None
        wired.demo.validate_queue_settings()
    finally:
        Config.reset_instance()


def _named_events(wired):
    """Alle gebundenen Events mit einem lesbaren Namen davor."""
    for fn in wired.demo.fns.values():
        if fn.fn is None:
            continue
        yield getattr(fn.fn, "__name__", repr(fn.fn)), fn


def test_every_event_targets_components_of_this_app(wired):
    """Ein Input/Output aus einem fremden Blocks-Kontext ist ein Laufzeitfehler."""
    known = set(wired.demo.blocks)
    for name, fn in _named_events(wired):
        for block in list(fn.inputs) + list(fn.outputs):
            assert block._id in known, f"{name}: Komponente gehört nicht zur App"


def test_every_handler_accepts_its_bound_inputs(wired):
    """Signatur und `inputs=`-Liste müssen zusammenpassen.

    Gradio warnt hier nur auf der Konsole und ruft den Handler trotzdem auf —
    der `TypeError` kommt dann erst beim Klick. `get_function_params` filtert
    die von Gradio selbst gefüllten Parameter (`gr.Request`, `gr.EventData`)
    heraus, deshalb ist der Vergleich exakt.
    """
    for name, fn in _named_events(wired):
        params = get_function_params(fn.fn)
        # Gradios interne Tupelbreite hat sich zwischen 4.44 und 5.x geändert
        # (3 → 4 Felder). Nur das zweite Feld interessiert hier, deshalb wird
        # positionsweise statt entpackend gelesen — das überlebt die nächste
        # Erweiterung ebenfalls.
        required = sum(1 for param in params if not param[1])
        takes_varargs = any(
            p.kind is inspect.Parameter.VAR_POSITIONAL
            for p in inspect.signature(fn.fn).parameters.values()
        )
        count = len(fn.inputs)
        assert (
            count >= required
        ), f"{name}: braucht {required} Argumente, bekommt {count}"
        if not takes_varargs:
            assert count <= len(
                params
            ), f"{name}: nimmt höchstens {len(params)} Argumente, bekommt {count}"


def test_gradio_reports_no_argument_mismatch(wired):
    """Dieselbe Prüfung aus Gradios Sicht — dessen Warnung darf nicht fallen."""
    mismatches = [w for w in wired.warnings if "arguments for function" in w]
    assert not mismatches, mismatches


def test_cancels_only_target_queued_events(wired):
    """`cancels` auf ein `queue=False`-Event lässt die App gar nicht erst starten.

    Gradio prüft das in `launch()` — den überspringt der Test, also hier
    ausdrücklich. Genau dieser Fehler ist bei #35 passiert.
    """
    wired.demo.validate_queue_settings()


def test_streaming_handlers_are_queued(wired):
    """Ein Generator-Handler ohne Queue liefert im Browser nur den letzten Yield."""
    for name, fn in _named_events(wired):
        if inspect.isgeneratorfunction(fn.fn):
            assert fn.queue, f"{name}: streamt, ist aber nicht gequeuet"


# ---- Die Ausgabelisten (die eigentliche Fehlerquelle) -----------------------


@pytest.mark.parametrize(
    "keys",
    [PERSONA_OUTPUT_KEYS, STREAM_OUTPUT_KEYS, STREAM_CONTROL_KEYS, ASK_ALL_OUTPUT_KEYS],
    ids=["persona", "stream", "stream_controls", "ask_all"],
)
def test_output_key_lists_name_existing_components(wired, keys):
    missing = [key for key in keys if key not in wired.components]
    assert not missing, f"Keys ohne Komponente: {missing}"


def test_reset_updates_covers_every_persona_output_key(wired):
    """Ein fehlender Key hier heißt: die Komponente behält ihren alten Zustand.

    So ist in dieser Session ein gesetztes Lösch-Häkchen über einen
    Ansichtswechsel hinweg stehen geblieben — `history_confirm` fehlte in der
    Liste.
    """
    assert set(wired.ui._reset_updates()) == set(PERSONA_OUTPUT_KEYS)


def test_persona_selected_updates_fills_every_slot(wired):
    """Die Persona-Auswahl muss jeden Slot der 47er-Liste bedienen."""
    persona = {"name": "LEAH", "description": "Test", "prompt": "Du bist LEAH."}
    updates = wired.ui._persona_selected_updates(
        "leah", persona, "Hallo {persona_name} ({model_name})", "Frag mich was"
    )
    assert len(updates) == len(PERSONA_OUTPUT_KEYS)


def test_gradio_hands_every_browser_session_its_own_context(wired):
    """Die Sitzungstrennung hängt an Gradios Kopierverhalten — also hier prüfen.

    Der Zwilling dieses Tests in `test_web_ui.py` prüft nur, dass der Default
    `deepcopy`-fähig ist: eine Bedingung, aber **meine** Annahme. Ob Gradio
    tatsächlich pro Sitzung kopiert, steht hier — sonst bliebe der Test grün,
    während sich die Sitzungen wieder still vermischen.
    """
    from gradio.state_holder import StateHolder

    holder = StateHolder()
    holder.set_blocks(wired.demo)
    state_id = wired.components["session_state"]._id

    a = holder["sitzung-a"][state_id]
    b = holder["sitzung-b"][state_id]
    a.bot = "LEAH"
    a.tmp_files["download"] = "/tmp/a.json"

    assert a is not b
    assert b.bot is None
    assert b.tmp_files == {}
    # Und dieselbe Sitzung bekommt ihr Objekt wieder — sonst wäre jede
    # In-place-Änderung nach dem nächsten Event weg.
    assert holder["sitzung-a"][state_id] is a


def test_persona_outputs_are_bound_in_list_order(wired):
    """Die Reihenfolge der gebundenen Outputs ist die von PERSONA_OUTPUT_KEYS.

    Die Handler liefern ein Dict und lösen es über `_as_persona_outputs` auf —
    stimmt die Bindungsreihenfolge nicht, landen die Updates an der falschen
    Komponente, ohne dass irgendetwas fehlschlägt.
    """
    expected = [wired.components[key]._id for key in PERSONA_OUTPUT_KEYS]
    persona_events = [
        fn
        for _name, fn in _named_events(wired)
        if len(fn.outputs) == len(PERSONA_OUTPUT_KEYS)
    ]
    assert persona_events, "kein Handler auf der Persona-Ausgabeliste gefunden"
    for fn in persona_events:
        assert [block._id for block in fn.outputs] == expected


# ---- Theme-Umschalter (#69) ------------------------------------------------


def _theme_events(wired):
    toggle_id = wired.components["theme_toggle_btn"]._id
    return [
        fn
        for fn in wired.demo.fns.values()
        if any(target == toggle_id for target, _event in fn.targets)
    ]


def test_the_theme_switch_never_navigates(wired):
    """Der eigentliche Fix: kein `?__theme=`-Link mehr irgendwo im Layout.

    Ein solcher Link ist eine Navigation, also ein voller Reload — neuer
    `session_hash`, und damit sind Persona, Streamer, `conversation_state`
    und getippter Text weg. Im Browser nachgestellt: ein Klick warf den
    ungesendeten Satz weg und landete zurück auf der Startseite.
    """
    rendered = [
        str(getattr(block, "value", "") or "") for block in wired.demo.blocks.values()
    ]
    offenders = [html for html in rendered if "__theme" in html]
    assert not offenders, offenders


def test_the_theme_toggle_runs_without_a_server_round_trip(wired):
    """`fn=None` + `js=` heißt für Gradio: nur das Skript, kein Request.

    Daran hängt alles — sobald hier ein Python-Handler steht, gibt es wieder
    eine Serverrunde, und mit ihr die Wege zurück zum alten Verhalten.
    """
    events = _theme_events(wired)
    assert len(events) == 1, f"erwartet genau ein Event, gefunden: {len(events)}"
    event = events[0]
    assert event.fn is None, "der Umschalter darf keinen Backend-Handler haben"
    assert event.js, "ohne js passiert beim Klick gar nichts"
    assert not event.inputs and not event.outputs


def test_the_page_restores_the_remembered_theme_on_load(wired):
    """Ohne das Lade-Skript gilt die Wahl nur bis zum nächsten Neuladen."""
    assert wired.demo.js, "gr.Blocks(js=…) fehlt"
    assert THEME_STORAGE_KEY in wired.demo.js
    # Gradio setzt sein eigenes Theme während der Initialisierung; wer davor
    # schreibt, verliert. Deshalb muss die Wiederherstellung aufgeschoben sein.
    assert "setTimeout" in wired.demo.js


def test_both_scripts_stand_on_their_own(wired):
    """Der Klick darf nicht davon abhängen, dass das Lade-Skript schon lief.

    Sonst wäre ein früher Klick wirkungslos — und zwar stumm.
    """
    toggle_js = _theme_events(wired)[0].js
    for script in (toggle_js, wired.demo.js):
        assert "const apply =" in script
        assert "classList.toggle" in script


def test_the_toggle_offers_the_other_state(wired):
    """Ein Knopf, der den *anderen* Zustand anbietet — nicht beide nebeneinander.

    Der alte Umschalter zeigte zwei blasse Links ohne Hinweis, welcher gerade
    gilt. Die Beschriftung wechselt jetzt mit dem Theme, deshalb müssen beide
    Texte im Skript stehen.
    """
    button = wired.components["theme_toggle_btn"]
    assert button.elem_id == THEME_TOGGLE_ELEM_ID
    light, dark = "☀️ Hell", "🌙 Dunkel"
    assert button.value == dark  # hell ist der Startzustand -> Dunkel anbieten
    for script in (_theme_events(wired)[0].js, wired.demo.js):
        assert light in script and dark in script


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_only_a_known_value_is_restored(mode):
    """Was aus dem `localStorage` kommt, ist Fremdeingabe wie jede andere."""
    script = theme_restore_js("Hell", "Dunkel")
    assert f'stored === "{mode}"' in script


# ---- Icons der Funktionskarten (#70) ---------------------------------------


def _rendered_html(wired):
    import gradio as gr

    return [
        str(block.value or "")
        for block in wired.demo.blocks.values()
        if isinstance(block, gr.HTML)
    ]


def _card_icons(wired):
    # Auf das div prüfen, nicht auf den Klassennamen — sonst zählt der
    # Stylesheet-Block mit, der `.card-icon` ebenfalls enthält.
    return [html for html in _rendered_html(wired) if '<div class="card-icon">' in html]


def _image_basenames(wired):
    """Die Dateinamen aller gerenderten Bilder.

    Gradio kopiert Ausgabedateien in seinen Cache, der Pfad ist dort gehasht —
    der Dateiname bleibt aber stehen, und nur der interessiert hier.
    """
    import os

    import gradio as gr

    names = []
    for block in wired.demo.blocks.values():
        if not isinstance(block, gr.Image) or not block.value:
            continue
        value = block.value
        path = value.get("path", "") if isinstance(value, dict) else str(value)
        names.append(os.path.basename(path))
    return names


def test_no_portrait_stands_on_a_function_card(wired):
    """`YUL_YEN.png` stand zweimal auf der Startseite — auf zwei *Funktionen*.

    Dasselbe Porträt zweimal neben den vier Persona-Karten liest sich wie zwei
    weitere Gesprächspartner. Genau die Verwechslung, die #68 beschreibt.
    """
    # Übrig bleiben dürfen nur Persona-Porträts aus dem Ensemble.
    offenders = [
        name
        for name in _image_basenames(wired)
        if name not in {"thumb.webp", "full.webp"}
    ]
    assert not offenders, offenders


def test_every_function_card_carries_its_own_icon(wired):
    """Vier Funktionen, vier verschiedene Icons.

    Zweimal dasselbe Icon wäre derselbe Fehler wie zweimal dasselbe Foto —
    nur in Strichzeichnung.
    """
    icons = _card_icons(wired)
    assert len(icons) == 5, f"erwartet 4 Karten + Ask-All-Leiste, gefunden {len(icons)}"
    assert len(set(icons)) == 4, "zwei Karten teilen sich ein Icon"


def test_the_icons_follow_the_theme(wired):
    """`currentColor` statt fester Farbe — sonst verschwinden sie im Dunkelmodus."""
    for icon in _card_icons(wired):
        assert 'stroke="currentColor"' in icon
        # Direkt darunter steht derselbe Sachverhalt als Text; ein Screenreader
        # soll ihn nicht zweimal vorlesen.
        assert 'aria-hidden="true"' in icon


def test_the_personas_keep_their_portraits(wired):
    """Nicht überkorrigieren: bei den Personas *ist* das Porträt der Sinn."""
    portraits = [name for name in _image_basenames(wired) if name == "thumb.webp"]
    assert len(portraits) >= 4, portraits


def test_an_unknown_icon_name_fails_loudly():
    """Ein Tippfehler soll hier auffallen, nicht als leere Karte im Browser."""
    with pytest.raises(KeyError):
        card_icon_html("verlaufff")
