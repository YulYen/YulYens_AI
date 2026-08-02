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
import threading
import time
import warnings
from unittest.mock import patch

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


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    """Startet die echte App auf einem freien Port und gibt ihre URL zurück."""
    from config.config_singleton import Config
    from core.dummy_llm_core import DummyLLMCore
    from core.factory import AppFactory
    from ui.web_ui import WebUI

    workdir = tmp_path_factory.mktemp("webui")

    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "warm_up": False})
    cfg.override("wiki", {"mode": False})  # kein spaCy-Modell im Container
    cfg.override("ui", {"type": "web"})
    cfg.override("tts", {"enabled": False})
    cfg.override("stt", {"enabled": False})
    cfg.override("rss", {"enabled": False})
    cfg.override("api", {"enabled": False})
    cfg.override("logging", {"dir": str(workdir)})  # Feedback-Log landet hier
    # Ablage an, aber ohne Anmeldung: genau die Lage aus #72, in der die
    # Verlauf-Karte wegfallen muss.
    cfg.override("storage", {"enabled": True, "path": str(workdir / "conv.sqlite3")})

    captured: dict = {}

    def _capture(self, demo):
        captured["demo"] = demo

    ui = AppFactory().get_ui()
    with (
        patch.object(WebUI, "_start_server", _capture),
        patch.object(DummyLLMCore, "stream_chat", _slow_stream),
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore")
        ui.launch()

        demo = captured["demo"]
        # prevent_thread_lock: launch() würde sonst blockieren.
        demo.launch(
            server_name="127.0.0.1",
            prevent_thread_lock=True,
            show_api=False,
            quiet=True,
        )
        try:
            yield type(
                "LiveApp",
                (),
                {
                    "url": demo.local_url,
                    "workdir": workdir,
                    "ui": ui,
                },
            )
        finally:
            demo.close()
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
    context = browser.new_context()
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

    # Gradio beschriftet den Daumen klein und vergibt eine eigene Klasse.
    page.locator("button.like-button:visible").last.click()

    votes = live_app.workdir / "feedback_votes.jsonl"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not votes.exists():
        time.sleep(0.2)
    assert votes.exists(), "kein feedback_votes.jsonl geschrieben"

    entries = [json.loads(line) for line in votes.read_text().splitlines() if line]
    assert entries, "Vote-Log ist leer"
    assert entries[-1]["vote"] in ("up", "down")
    assert "ECHO: Bewerte mich" in entries[-1]["answer"]


# ---- Der Server steht überhaupt ------------------------------------------


def test_the_app_serves_without_a_backend_thread_dying(live_app):
    """Ein Sanity-Check, der ohne Browser auskommt."""
    assert live_app.url.startswith("http://127.0.0.1")
    assert any(t.is_alive() for t in threading.enumerate())
