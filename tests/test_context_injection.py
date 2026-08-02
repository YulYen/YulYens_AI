"""Injizierter Fremdkontext in der ``user``-Rolle (#60).

Der Umbau hat zwei Hälften, und die zweite ist die, die stillschweigend bricht.

*Sichtbar:* Wiki-Snippets und RSS-Meldungen stehen nicht mehr als ``system`` im
Prompt. Fällt sofort auf, sobald man hinsieht.

*Unsichtbar:* ``system`` war zugleich das Merkmal, an dem Ablage und
JSON-Export den Fremdtext vom Gespräch getrennt haben. Ohne Ersatz landet jeder
abgerufene Artikel in ``data/conversations.sqlite3``, im Verlauf, im
Markdown-Export und im heruntergeladenen JSON — und *nichts* daran sieht kaputt
aus. Ein Gespräch mit einem Wikipedia-Absatz mittendrin ist eine plausible
Datei. Deshalb steht die Hälfte hier als eigener Test und nicht als Zeile in
einem Bestandstest.
"""

from __future__ import annotations

import json

import pytest
from config.config_singleton import Config
from core.context_injection import (
    INJECTED_KEY,
    conversation_only,
    injected_message,
    is_injected,
)
from rss.feeds import inject_rss_context
from storage import SqliteStore
from ui.conversation_io_terminal import load_conversation, save_conversation
from wiki.lookup import WikiSnippet, inject_wiki_context


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(tmp_path / "conversations.sqlite3")


def _snippet(
    topic: str = "Kiwix", text: str = "Kiwix liest ZIM-Dateien."
) -> WikiSnippet:
    return WikiSnippet(
        topic=topic,
        snippet=text,
        link=f"http://127.0.0.1:8080/{topic}",
        source="offline",
        full_length=len(text),
    )


# --- die sichtbare Hälfte -------------------------------------------------


def test_the_wiki_snippet_is_quoted_user_text_the_instruction_stays_system():
    history: list = []
    inject_wiki_context(history, [_snippet()])

    guardrail, quoted = history
    # Unser eigener Satz darf Systemautorität haben …
    assert guardrail["role"] == "system" and not is_injected(guardrail)
    # … der Text aus der ZIM-Datei nicht.
    assert quoted["role"] == "user" and is_injected(quoted)
    assert quoted[INJECTED_KEY] == "wiki"
    assert "Kiwix liest ZIM-Dateien." in quoted["content"]


def test_the_quoted_block_is_delimited_on_both_sides():
    """Ohne Ende-Marke ist die Klammer wertlos.

    Eine offene Klammer kann der Fremdtext selbst schließen und danach wie die
    Anwendung weiterreden — genau der Angriff, gegen den delimitiert wird.
    """
    history: list = []
    inject_wiki_context(history, [_snippet()])
    content = history[-1]["content"]

    opener = Config().t("context_quote_wrapper", body="X").split("X")[0].strip()
    closer = Config().t("context_quote_wrapper", body="X").split("X")[-1].strip()
    assert opener and closer, "die Klammer braucht beide Seiten"
    assert content.startswith(opener) and content.endswith(closer)


def test_the_rss_block_is_quoted_user_text_too():
    history: list = []
    inject_rss_context(history, "Meldung: Bahnstreik")

    assert history[0]["role"] == "system"
    assert history[1]["role"] == "user" and history[1][INJECTED_KEY] == "rss"
    assert "Bahnstreik" in history[1]["content"]


# --- die stille Hälfte ----------------------------------------------------


def test_the_store_does_not_record_injected_context(store):
    """Die Ablage ist das Gespräch, nicht der Prompt.

    Vor #60 erledigte das der Rollenfilter nebenbei. Jetzt trägt der Marker
    diese Zusage allein.
    """
    cid = store.start(user="yulyen", persona="PETER", model="m", app="web")
    history: list = []
    inject_wiki_context(history, [_snippet(text="Geheimer Artikeltext.")])
    history.append({"role": "user", "content": "Was ist Kiwix?"})
    history.append({"role": "assistant", "content": "Ein Offline-Reader."})

    store.sync(cid, history)
    _ref, messages = store.load(cid)

    assert messages == [
        {"role": "user", "content": "Was ist Kiwix?"},
        {"role": "assistant", "content": "Ein Offline-Reader."},
    ]
    assert "Geheimer Artikeltext." not in json.dumps(messages, ensure_ascii=False)


def test_the_title_is_the_question_not_the_injected_article(store):
    """Der Titel entsteht aus der ersten ``user``-Nachricht.

    Ohne Marker-Filter wäre das ab #60 der Wikipedia-Absatz — der Verlauf
    zeigte lauter Gespräche mit Artikeltext als Überschrift.
    """
    cid = store.start(user="yulyen", persona="PETER", model="m", app="web")
    history: list = []
    inject_wiki_context(history, [_snippet(text="Ein langer Artikelanfang.")])
    history.append({"role": "user", "content": "Was ist Kiwix?"})

    store.sync(cid, history)

    assert store.list_conversations()[0].title == "Was ist Kiwix?"


def test_the_json_export_carries_the_conversation_not_the_prompt(tmp_path):
    """Die Datei geht aus dem Haus — Artikeltext hat darin nichts verloren.

    Vor #60 rutschte er als ``system``-Nachricht mit hinaus; danach wäre er von
    einer echten Frage des Nutzers nicht mehr zu unterscheiden.
    """
    meta = {
        "created_at": "2026-08-02T10:00:00",
        "model": "dummy",
        "persona": "PETER",
        "app": "terminal",
    }
    history: list = []
    inject_wiki_context(history, [_snippet(text="Artikeltext aus der ZIM-Datei.")])
    history.append({"role": "user", "content": "Was ist Kiwix?"})
    history.append({"role": "assistant", "content": "Ein Offline-Reader."})

    target = tmp_path / "conv.json"
    save_conversation(str(target), meta, history)
    _meta, messages = load_conversation(str(target))

    assert "ZIM-Datei" not in target.read_text(encoding="utf-8")
    assert [m for m in messages if m["role"] != "system"] == [
        {"role": "user", "content": "Was ist Kiwix?"},
        {"role": "assistant", "content": "Ein Offline-Reader."},
    ]
    # Das Guardrail ist unser eigener Satz und wandert weiterhin mit — es war
    # schon vor #60 in der Datei und enthält weder Fremdtext noch Nutzerdaten.
    # Bewusst nicht mitgefiltert: das wäre eine zweite, unabhängige Entscheidung
    # über den Export (dann müsste auch geklärt werden, dass ein
    # wieder-geladenes Gespräch die Guardrails nicht doppelt).
    assert sum(1 for m in messages if m["role"] == "system") == 1


def test_filtering_leaves_the_prompt_history_untouched():
    """Der Filter kopiert. Sonst räumte ein Export die laufende History leer."""
    history = [injected_message("Fremdtext", "wiki"), {"role": "user", "content": "Hi"}]

    kept = conversation_only(history)
    kept[0]["content"] = "verändert"

    assert len(history) == 2
    assert history[1] == {"role": "user", "content": "Hi"}
