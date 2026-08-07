"""Rauchtest der WebUI im echten Browser (#61-Vorarbeit).

`test_web_ui_wiring.py` prüft die Verkabelung in-process — es fängt einen
verrutschten Ausgabe-Key oder ein `cancels` auf ein `queue=False`-Event. Was es
nicht sehen kann, ist alles, was **das Frontend** entscheidet: ob ein Generator
seine Yields tatsächlich ausliefert, ob ein Klick die Seite neu lädt, ob eine
Datei durchgereicht wird. Genau diese Klasse von Fehlern ist im Projekt teuer
erkauft worden (#35 Button-Tausch, #69 Theme ohne Reload, die
Dataframe-Stolperfalle) und genau sie bricht bei einem Gradio-Versionssprung.

Der Test läuft deshalb gegen eine **laufende** App mit Dummy-Backend. Er ist
bewusst ein Rauchtest: wenige, dafür belegbare Aussagen über Verhalten, das wir
nicht verlieren wollen.

Ausführen: ``pytest -m browser``. Ohne Playwright oder ohne Chromium wird
sauber übersprungen — dieselbe Konvention wie ``@pytest.mark.ollama``.
"""

from __future__ import annotations

import glob
import json
import re
import sys
import threading
import time
import warnings
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import gradio as gr
import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from playwright.sync_api import expect, sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser

# Der Container bringt Chromium mit, aber nicht zwingend in der Revision, die
# das installierte Playwright erwartet. Erst den mitgelieferten Build suchen,
# sonst Playwright selbst entscheiden lassen.
_BUNDLED_CHROMIUM = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


def _launch_browser(playwright):
    kwargs = {"args": ["--no-sandbox"]}
    if _BUNDLED_CHROMIUM:
        kwargs["executable_path"] = _BUNDLED_CHROMIUM[-1]
    return playwright.chromium.launch(**kwargs)


def _slow_stream(self, model_name, messages, options=None, keep_alive=600):
    """Wie DummyLLMCore.stream_chat, nur in vielen kleinen Häppchen.

    Das Original liefert die ganze Antwort in *einem* Chunk. Damit ist ein
    Stream im Browser vorbei, bevor man ihn sehen kann — und der Tausch
    „Senden ⇄ Stop" (#35) wäre nicht prüfbar.
    """
    user_input = ""
    for message in reversed(messages or []):
        if message.get("role") == "user":
            user_input = message.get("content", "") or ""
            break
    for word in f"ECHO: {user_input}".split(" "):
        time.sleep(0.12)
        yield {"message": {"content": word + " "}}


# Kleinstes gültiges WAV: 44-Byte-Header, null Sample-Bytes. Reicht, damit
# Gradio die Datei als Audio ausliefert — geprüft wird der *Weg*, nicht der Ton.
_EMPTY_WAV = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


def _fake_piper_module():
    """Ersatz für `tts.piper_tts` — schreibt ein WAV, ohne Piper zu brauchen.

    Der Handler importiert `create_wav` erst beim Klick (lazy, weil piper auf
    Modulebene importiert). Ein Eintrag in `sys.modules` genügt deshalb.
    """
    module = ModuleType("tts.piper_tts")

    def create_wav(text, persona, *, voices_dir, out_wav, tts_cfg, language="de"):
        Path(out_wav).write_bytes(_EMPTY_WAV)
        return str(out_wav)

    module.create_wav = create_wav
    return module


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    """Startet die echte App auf einem freien Port und gibt ihre URL zurück."""
    from config.config_singleton import Config
    from core.dummy_llm_core import DummyLLMCore
    from core.factory import AppFactory

    workdir = tmp_path_factory.mktemp("webui")

    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "warm_up": False})
    cfg.override("wiki", {"mode": False})  # kein spaCy-Modell im Container
    cfg.override("ui", {"type": "web"})
    # Vorlesen an, aber mit gestubbtem Piper: geprüft wird, dass Gradio die
    # erzeugte Datei überhaupt ausliefert (unter Gradio 5 strenger bei Pfaden),
    # nicht dass sie gut klingt.
    cfg.override("tts", {"enabled": True, "features": {"web_read_aloud": True}})
    cfg.override("stt", {"enabled": False})
    cfg.override("rss", {"enabled": False})
    cfg.override("api", {"enabled": False})
    # Logverzeichnis und Ablage bewusst **auseinander**: der Vote-Log liegt
    # neben der Ablage, nicht bei den Logs. Lägen beide im selben Verzeichnis,
    # könnte der Test unten nicht zwischen altem und neuem Verhalten
    # unterscheiden — er wäre grün geblieben, egal wohin geschrieben wird.
    cfg.override("logging", {"dir": str(workdir / "logs")})
    # Ablage an, aber ohne Anmeldung: genau die Lage aus #72, in der die
    # Verlauf-Karte wegfallen muss.
    cfg.override(
        "storage", {"enabled": True, "path": str(workdir / "data" / "conv.sqlite3")}
    )

    captured: dict = {}

    # Die Verfügbarkeitsfragen beantwortet seit #56 `ui/webui_features.py` —
    # dort hängt auch die Prüfung auf installierte Pakete.
    with patch(
        "ui.webui_features.module_available", lambda name: name != "faster_whisper"
    ):
        ui = AppFactory().get_ui()
    sys.modules["tts.piper_tts"] = _fake_piper_module()

    # `_start_server` läuft **echt**. Der erste Anlauf fing es ab und rief
    # `demo.launch()` selbst — damit prüfte der Browser-Test alles außer dem
    # Startpfad, und genau dort saßen zwei Gradio-6-Brüche (`show_api` weg,
    # `js` nur noch an `launch()`). Abgefangen wird deshalb erst eine Ebene
    # tiefer: `Blocks.launch` bekommt die echten Argumente der App und nur
    # Host/Port/Blockieren von uns.
    real_launch = gr.Blocks.launch

    def _launch_nonblocking(self, **kwargs):
        captured["demo"] = self
        captured["kwargs"] = dict(kwargs)
        kwargs.update(
            server_name="127.0.0.1",
            server_port=None,
            prevent_thread_lock=True,
            quiet=True,
        )
        return real_launch(self, **kwargs)

    with (
        patch.object(gr.Blocks, "launch", _launch_nonblocking),
        patch.object(DummyLLMCore, "stream_chat", _slow_stream),
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore")
        ui.launch()

        demo = captured["demo"]
        try:
            yield type(
                "LiveApp",
                (),
                {
                    "url": demo.local_url,
                    "workdir": workdir,
                    "ui": ui,
                    "launch_kwargs": captured["kwargs"],
                },
            )
        finally:
            demo.close()
            sys.modules.pop("tts.piper_tts", None)
            Config.reset_instance()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = _launch_browser(playwright)
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def page(browser, live_app):
    # `locale` festnageln: Gradio 6 übersetzt sein *eigenes* Bedienchrom nach
    # der Browsersprache — der Daumen heißt auf einem deutschen System
    # „Gefällt mir", auf einem englischen „Like". Ohne diese Zeile hängt der
    # Selektor unten an der Spracheinstellung des Rechners, auf dem der Test
    # gerade läuft; er war genau deshalb auf einem deutschen Windows rot und
    # auf dem Linux-Runner grün. Unsere eigenen Texte bleiben davon unberührt,
    # sie kommen aus `locales/de.yaml` und folgen `language:` in der Config —
    # deshalb wird hier weiter auf „Senden" und „Verlauf" gewartet.
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    # Nicht `networkidle`: Gradio hält eine Verbindung offen, der Zustand tritt
    # nie ein. Stattdessen auf ein Element warten, das die App gebaut hat.
    page.goto(live_app.url, wait_until="domcontentloaded")
    page.wait_for_selector(".persona-card", timeout=30_000)
    try:
        yield page
    finally:
        context.close()


def _pick_persona(page, name="LEAH"):
    page.get_by_role("button", name=name, exact=False).first.click()
    expect(page.get_by_placeholder("Schreibe…")).to_be_visible(timeout=15_000)


def _ask(page, question):
    page.get_by_placeholder("Schreibe…").fill(question)
    page.get_by_role("button", name="Senden", exact=False).first.click()


# ---- Der Chat lebt --------------------------------------------------------


def test_a_persona_answers_and_the_tokens_arrive_in_the_browser(page):
    """Die Kernaussage: ein Generator-Handler liefert seine Yields ans Frontend."""
    _pick_persona(page)
    _ask(page, "Hallo Welt")
    expect(page.get_by_text("ECHO: Hallo Welt")).to_be_visible(timeout=30_000)


def test_the_send_button_turns_into_stop_while_streaming(page):
    """#35: der Tausch reist in denselben Yields mit, nicht als Folge-Event.

    Als eigenes `.then()`-Event kostete er ~3,5 s bis zum ersten Token. Wäre er
    je wieder eines, erschiene Stop erst, wenn der Stream fast durch ist.
    """
    _pick_persona(page)
    _ask(page, "Bitte etwas laenger antworten damit der Stream sichtbar bleibt")
    expect(page.get_by_role("button", name="Stop", exact=False)).to_be_visible(
        timeout=5_000
    )
    # …und danach ist wieder Senden da.
    expect(page.get_by_role("button", name="Senden", exact=False).first).to_be_visible(
        timeout=30_000
    )


def test_the_status_line_reports_context_and_speed_after_an_answer(page):
    """#36: die Statuszeile kommt erst im Schluss-Yield."""
    _pick_persona(page)
    _ask(page, "Kurz")
    # `.chat-status` sitzt sowohl am Gradio-Block als auch am Markdown darin —
    # ohne `.prose` wäre das ein strict-mode-Treffer auf zwei Elemente.
    status = page.locator(".prose.chat-status")
    expect(status).to_contain_text("Token", timeout=30_000)
    expect(status).to_contain_text("Tok/s")


# ---- Theme (#69) ----------------------------------------------------------


def test_the_theme_toggle_does_not_reload_the_page(page):
    """#69: der Umschalter waren zwei `<a href>` — ein Klick kostete die Sitzung.

    Nachgestellt wird genau der Verlust: getippter, noch nicht abgeschickter
    Text muss den Klick überleben. Zusätzlich eine Marke am `window`, die ein
    Reload zuverlässig abräumt.
    """
    _pick_persona(page)
    page.evaluate("window.__yulyen_marker = 'ueberlebt'")
    page.get_by_placeholder("Schreibe…").fill("noch nicht abgeschickt")

    before = page.evaluate("document.body.classList.contains('dark')")
    page.locator("#theme-toggle").click()

    page.wait_for_function(
        f"document.body.classList.contains('dark') !== {str(before).lower()}",
        timeout=5_000,
    )
    assert page.evaluate("window.__yulyen_marker") == "ueberlebt"
    expect(page.get_by_placeholder("Schreibe…")).to_have_value("noch nicht abgeschickt")


def test_the_theme_choice_survives_a_real_reload(page, live_app):
    """Die Wahl liegt im localStorage und wird nach Gradios Init zurückgeholt."""
    page.locator("#theme-toggle").click()
    chosen = page.evaluate("document.body.classList.contains('dark')")

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        f"document.body.classList.contains('dark') === {str(chosen).lower()}",
        timeout=5_000,
    )


# ---- Ablage ohne Anmeldung (#72) -----------------------------------------


def test_without_a_login_there_is_no_history_card(page):
    """#72: `DisabledAuth` gibt allen dieselbe Identität — also kein Verlauf.

    Eine Karte über einem NullStore verspricht etwas, das sich nie füllt.
    """
    expect(page.get_by_role("button", name="Verlauf", exact=False)).to_have_count(0)


# ---- Feedback (#40/#65) ---------------------------------------------------


def test_a_thumb_on_an_answer_is_written_to_the_vote_log(page, live_app):
    """#40: der Daumen schreibt eine Zeile, #65: mit Schlüssel in die Ablage.

    Genau diese Zuordnung hängt am Chatbot-Format — sie ist das
    Abbruchkriterium für die Gradio-5-Migration.
    """
    _pick_persona(page)
    _ask(page, "Bewerte mich")
    expect(page.get_by_text("ECHO: Bewerte mich")).to_be_visible(timeout=30_000)

    # Über die Rolle statt über Klassen: Gradio benennt den Daumen zwischen
    # 4.44 und 5.x unterschiedlich (`like-button` und „like" gegen
    # `icon-button` und „Like"). Der verankerte Regex trennt Like von Dislike
    # und ist gegen die Schreibweise unempfindlich — `exact=True` wäre
    # case-sensitiv und damit genau an dieser Stelle zerbrechlich.
    #
    # Dass hier ein *englisches* Wort steht, ist keine Nachlässigkeit: seit
    # Gradio 6 ist der Name übersetzt, und die Sprache legt das `page`-Fixture
    # fest (`locale="en-US"`). Der Anker ist dabei die halbe Miete — „Gefällt
    # mir" ist ein Präfix von „Gefällt mir nicht", ein ungeankertes Muster
    # träfe im Deutschen beide Daumen.
    page.get_by_role("button", name=re.compile(r"^like$", re.I)).last.click()

    # Neben der Ablage, nicht im Logverzeichnis: `logs/` ist wegwerfbar,
    # gesammelte Bewertungen sind es nicht (sie sind der Trainingsdaten-Kanal
    # für #7). Das Fixture legt beide Verzeichnisse deshalb getrennt an — der
    # Pfad hier ist die eigentliche Zusicherung.
    votes = live_app.workdir / "data" / "feedback_votes.jsonl"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not votes.exists():
        time.sleep(0.2)
    assert votes.exists(), "kein feedback_votes.jsonl neben der Ablage geschrieben"
    assert not (
        live_app.workdir / "logs" / "feedback_votes.jsonl"
    ).exists(), "der Vote-Log darf nicht im Logverzeichnis landen"

    entries = [json.loads(line) for line in votes.read_text().splitlines() if line]
    assert entries, "Vote-Log ist leer"
    assert entries[-1]["vote"] in ("up", "down")
    assert "ECHO: Bewerte mich" in entries[-1]["answer"]


# ---- Dateien, die die App ausliefert -------------------------------------
#
# Der Weg ist an mehreren Stellen zerbrechlich: die Dateien entstehen in einem
# Temp-Verzeichnis (`_delivery_dir`), haengen an der Sitzung
# (`SessionContext.tmp_files`) und muessen von Gradio nach draussen gereicht
# werden. Gradio kopiert sie dafuer in seinen eigenen Cache — was auf einer
# neuen Hauptversion sowohl an Pfadregeln als auch am Ausliefern haengen kann.
# In-process sieht man davon nichts: dort steht am Ende nur ein `gr.update`
# mit einem Pfad, und ob der Browser die Datei je bekommt, sagt es nicht.


def _download_via(page, trigger):
    """Klickt und gibt den Inhalt der Datei zurück, die der Browser bekommt."""
    with page.expect_download(timeout=30_000) as info:
        trigger()
    target = Path(info.value.path())
    return info.value.suggested_filename, target.read_bytes()


def test_the_conversation_can_actually_be_downloaded_as_json(page):
    """#54: der Austauschweg — verlustfrei zurückladbar, also echtes JSON."""
    _pick_persona(page)
    _ask(page, "Sichere mich")
    expect(page.get_by_text("ECHO: Sichere mich")).to_be_visible(timeout=30_000)

    page.get_by_role("button", name=re.compile("herunterladen", re.I)).first.click()
    link = page.locator("a[download], .download-link a, a[href*='/file=']").first
    expect(link).to_be_visible(timeout=30_000)

    name, raw = _download_via(page, link.click)
    assert name.endswith(".json")

    payload = json.loads(raw.decode("utf-8"))
    assert payload["meta"]["persona"]
    texts = [m.get("content", "") for m in payload["messages"]]
    assert any("Sichere mich" in t for t in texts)
    assert any("ECHO: Sichere mich" in t for t in texts)


def test_injected_context_never_leaves_through_the_download(page):
    """#60: die Datei ist das Gespräch, nicht der Prompt.

    Fremdtext (Wiki, RSS) gehört zum Prompt und darf im Austauschformat nicht
    auftauchen — hier steht kein Fremdkontext an, geprüft wird deshalb die
    Form: nur `user` und `assistant`, keine System-Nachrichten.
    """
    _pick_persona(page)
    _ask(page, "Kurz")
    expect(page.get_by_text("ECHO: Kurz")).to_be_visible(timeout=30_000)

    page.get_by_role("button", name=re.compile("herunterladen", re.I)).first.click()
    link = page.locator("a[download], .download-link a, a[href*='/file=']").first
    expect(link).to_be_visible(timeout=30_000)
    _name, raw = _download_via(page, link.click)

    roles = {m.get("role") for m in json.loads(raw.decode("utf-8"))["messages"]}
    assert roles <= {"user", "assistant"}, f"unerwartete Rollen im Export: {roles}"


def test_read_aloud_delivers_a_playable_file(page):
    """Der WAV-Weg (#25): erzeugt in einem tmp-Verzeichnis, geliefert von Gradio.

    Piper ist gestubbt — es geht um die Auslieferung, nicht um die Stimme.

    Geprüft wird der **Netzverkehr**, nicht das `src`-Attribut des Players.
    Wie eine Audio-Komponente ihre Quelle intern anhängt, ist Gradios Sache und
    hat sich zwischen Hauptversionen schon geändert; ob die Datei über die
    Leitung geht, ist die Aussage, die wir wirklich meinen — und genau die, die
    ein strengerer Pfad-Check (`allowed_paths`) brechen würde.
    """
    delivered: list[tuple[str, int]] = []
    page.on(
        "response",
        lambda r: delivered.append((r.url, r.status)) if ".wav" in r.url else None,
    )

    _pick_persona(page)
    _ask(page, "Lies mich vor")
    expect(page.get_by_text("ECHO: Lies mich vor")).to_be_visible(timeout=30_000)

    page.get_by_role("button", name=re.compile("vorlesen", re.I)).first.click()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not delivered:
        page.wait_for_timeout(250)
    assert delivered, "der Browser hat nie eine .wav-Datei angefordert"

    url, status = delivered[-1]
    # 206 ist kein Fehler: der Player fordert Audio als Range-Request an, und
    # Gradio 6 beantwortet das mit Teilinhalt. Nur 200 zu erlauben wäre eine
    # Aussage über den Transportweg, nicht über die Auslieferung.
    assert status in (200, 206), f"WAV nicht ausgeliefert: HTTP {status} für {url}"
    body = page.request.get(url).body()
    assert body.startswith(b"RIFF"), "keine WAV-Daten am Ende der Leitung"


# ---- Der Server steht überhaupt ------------------------------------------


def test_the_app_serves_without_a_backend_thread_dying(live_app):
    """Ein Sanity-Check, der ohne Browser auskommt."""
    assert live_app.url.startswith("http://127.0.0.1")
    assert any(t.is_alive() for t in threading.enumerate())


def test_the_real_start_path_hands_over_the_load_script(live_app):
    """Diese Fixture faehrt `_start_server` echt — hier steht, warum das zaehlt.

    Der erste Anlauf fing `_start_server` ab und rief `demo.launch()` selbst.
    Damit lief der Browser-Test an genau dem Pfad vorbei, auf dem zwei
    Gradio-6-Brueche sassen: `show_api` gibt es nicht mehr (TypeError beim
    Start), und `js` wirkt nur noch an `launch()`.
    """
    kwargs = live_app.launch_kwargs
    assert kwargs.get("js"), "das Lade-Skript erreicht launch() nicht"
    assert "show_api" not in kwargs, "show_api gibt es in Gradio 6 nicht mehr"
    assert "api" not in (kwargs.get("footer_links") or [])
