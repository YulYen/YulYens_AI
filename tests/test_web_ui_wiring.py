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


@pytest.fixture(scope="module")
def wired():
    """Die echte WebUI, gebaut und verdrahtet — ohne Server."""
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "warm_up": False})
    cfg.override("wiki", {"mode": False})  # kein spaCy-Modell nötig
    cfg.override("ui", {"type": "web"})
    cfg.override("storage", {"enabled": False})

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

    yield SimpleNamespace(
        ui=ui,
        demo=captured["demo"],
        components=captured["components"],
        warnings=[str(w.message) for w in caught],
    )
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
        required = sum(1 for _n, has_default, _d in params if not has_default)
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
