"""Die reinen Formatierer der WebUI — ohne WebUI.

Sie hingen als Methoden an der 2200-Zeilen-Klasse, obwohl keine davon deren
Zustand braucht. Diese Tests brauchen deshalb keinen Mock-Factory-Aufbau mehr,
nur den Text-Katalog.
"""

from types import SimpleNamespace

from config.texts import Texts
from core.streaming_provider import StreamStats
from storage import ConversationRef
from ui.webui_format import (
    context_bar,
    conversation_markdown,
    find_question_for_row,
    format_ask_all_results,
    format_status_line,
    format_wiki_sources,
    history_label,
    messages_to_chat_history,
)
from wiki.lookup import WikiSnippet

T = Texts("de").format


# ---- Wiki-Quellen (#32) ------------------------------------------------------
# Der Punkt der Anzeige ist nicht "es gab eine Quelle", sondern *welcher Text*
# im Prompt gelandet ist und ob er an wiki.snippet_limit abgeschnitten wurde.


def test_format_wiki_sources_shows_link_length_and_the_injected_text():
    markdown = format_wiki_sources(
        [
            WikiSnippet(
                topic="Deutschland",
                snippet="Deutschland ist ein Bundesstaat.",
                link="http://127.0.0.1:8080/wiki/Deutschland",
                source="local",
                full_length=8432,
            )
        ],
        T,
    )

    assert "[Deutschland](http://127.0.0.1:8080/wiki/Deutschland)" in markdown
    assert "Offline-Archiv" in markdown
    # Gekürzt: beide Zahlen müssen dastehen, sonst ist nicht erkennbar, wie viel
    # des Artikels das Modell nie gesehen hat.
    assert "32 von 8432 Zeichen" in markdown
    assert "gekürzt" in markdown
    assert "> Deutschland ist ein Bundesstaat." in markdown


def test_format_wiki_sources_marks_complete_snippets_as_complete():
    markdown = format_wiki_sources(
        [WikiSnippet(topic="Kiwix", snippet="Kurz.", source="online", full_length=5)], T
    )

    assert "vollständig" in markdown
    assert "gekürzt" not in markdown
    assert "Wikipedia (online)" in markdown


def test_format_wiki_sources_numbers_every_snippet():
    markdown = format_wiki_sources(
        [
            WikiSnippet(topic="Eins", snippet="A", full_length=1),
            WikiSnippet(topic="Zwei", snippet="B", full_length=1),
        ],
        T,
    )

    assert "### 1. Eins" in markdown
    assert "### 2. Zwei" in markdown
    assert markdown.count("---") == 1


def test_format_wiki_sources_is_empty_without_snippets():
    assert format_wiki_sources([], T) == ""
    assert format_wiki_sources(None, T) == ""


# ---- Statuszeile (#36) -------------------------------------------------------


def test_status_line_shows_context_fill():
    line = format_status_line(
        T, {"num_ctx": 8192}, [{"role": "user", "content": "x" * 400}], None
    )

    assert "8.192" in line
    assert "%" in line
    assert "█" in line or "░" in line


def test_status_line_highlights_once_compression_kicks_in():
    """Fett genau ab der Schwelle, ab der shrink_history_for_context greift."""
    small = [{"role": "user", "content": "kurz"}]
    huge = [{"role": "user", "content": "x" * 4000}]

    assert not format_status_line(T, {"num_ctx": 1000}, small, None).startswith("**")
    assert format_status_line(T, {"num_ctx": 1000}, huge, None).startswith("**")


def test_status_line_reports_speed_and_first_token():
    stats = StreamStats(tokens=120, t_first_ms=1900, t_total_ms=5000)

    line = format_status_line(T, {"num_ctx": 8192}, [], stats)

    assert "24.0" in line  # 120 Token in 5 s
    assert "1.9" in line


def test_status_line_stays_empty_without_context_limit_and_stats():
    assert format_status_line(T, {}, [], None) == ""
    assert format_status_line(T, None, [], None) == ""


def test_context_bar_fills_proportionally():
    assert context_bar(0.0, width=4) == "░░░░"
    assert context_bar(1.0, width=4) == "████"
    assert context_bar(0.5, width=4) == "██░░"
    # Werte außerhalb von 0..1 dürfen den Balken nicht sprengen
    assert len(context_bar(5.0, width=4)) == 4
    assert len(context_bar(-1.0, width=4)) == 4


# ---- Chatverlauf und Gesprächs-Markdown -------------------------------------


def test_messages_to_chat_history_keeps_question_and_answer_as_two_rows():
    """Seit #61a ist eine Anzeige-Zeile *eine* Nachricht (messages-Format)."""
    rows = messages_to_chat_history(
        [
            {"role": "user", "content": "Frage"},
            {"role": "assistant", "content": "Antwort"},
        ]
    )

    assert rows == [
        {"role": "user", "content": "Frage"},
        {"role": "assistant", "content": "Antwort"},
    ]


def test_messages_to_chat_history_drops_injected_system_context():
    """Fremdtext gehoert zum Prompt, nicht ins Gespraech (#60)."""
    rows = messages_to_chat_history(
        [
            {"role": "system", "content": "[FREMDTEXT] …"},
            {"role": "user", "content": "Frage"},
        ]
    )

    assert rows == [{"role": "user", "content": "Frage"}]


def test_messages_to_chat_history_keeps_an_unanswered_question():
    pairs = messages_to_chat_history(
        [
            {"role": "user", "content": "Erste"},
            {"role": "user", "content": "Zweite"},
        ]
    )

    assert pairs == [
        {"role": "user", "content": "Erste"},
        {"role": "user", "content": "Zweite"},
    ]


def test_messages_to_chat_history_keeps_a_lone_answer():
    """Wiki-Hinweise sind Bot-Zeilen ohne Frage — sie dürfen nicht verschwinden."""
    assert messages_to_chat_history([{"role": "assistant", "content": "Hinweis"}]) == [
        {"role": "assistant", "content": "Hinweis"}
    ]


def test_messages_to_chat_history_ignores_system_messages():
    assert messages_to_chat_history([{"role": "system", "content": "Prompt"}]) == []
    assert messages_to_chat_history(None) == []


def _ref(**kwargs) -> ConversationRef:
    defaults = dict(
        id="abc",
        user="yulyen",
        persona="PETER",
        model="ministral",
        app="web",
        created_at="2026-07-31T10:05:00",
        updated_at="2026-07-31T10:07:00",
        title="Wie ist der Status?",
        message_count=2,
    )
    defaults.update(kwargs)
    return ConversationRef(**defaults)


def test_history_label_shows_date_persona_and_title():
    assert history_label(_ref()) == "2026-07-31 10:07 · PETER · Wie ist der Status?"


def test_history_label_survives_a_conversation_without_a_title():
    assert history_label(_ref(title="")).endswith("· —")


def test_conversation_markdown_carries_persona_date_and_both_roles():
    text = conversation_markdown(
        _ref(),
        [
            {"role": "user", "content": "Frage?"},
            {"role": "assistant", "content": "Antwort."},
        ],
        T,
    )

    assert text.startswith("# Wie ist der Status?")
    assert "PETER" in text and "ministral" in text and "yulyen" in text
    assert "2026-07-31 10:05" in text
    assert "Frage?" in text and "Antwort." in text


# ---- Ask-All und Feedback ----------------------------------------------------


def test_format_ask_all_results_makes_one_section_per_persona():
    markdown = format_ask_all_results({"LEAH": "A", "DORIS": "B"})

    assert "### LEAH" in markdown and "### DORIS" in markdown
    assert markdown.count("---") == 1


def test_find_question_walks_back_to_the_nearest_user_row():
    history = [
        {"role": "user", "content": "Frage?"},
        {"role": "assistant", "content": "🕵️ Hinweis"},
        {"role": "assistant", "content": "Antwort"},
    ]

    assert find_question_for_row(history, 2) == "Frage?"


def test_find_question_walks_back_over_an_answer_row():
    """Ein geladenes Gespraech steht als Folge einzelner Nachrichten da."""
    history = [
        {"role": "user", "content": "Frage?"},
        {"role": "assistant", "content": "Antwort"},
    ]
    assert find_question_for_row(history, 1) == "Frage?"


def test_find_question_returns_empty_on_garbage():
    assert find_question_for_row([], 0) == ""
    assert find_question_for_row(None, 3) == ""
    assert find_question_for_row([{"role": "assistant", "content": "nur Bot"}], 5) == ""


def test_status_line_ignores_a_streamer_without_real_stats():
    """Testdoubles setzen last_stream_stats nicht — das darf nichts rendern."""
    from ui.session import SessionContext
    from ui.webui_chat import ChatController

    session = SessionContext(streamer=SimpleNamespace(last_stream_stats="kaputt"))

    assert ChatController.last_stream_stats(session) is None


# ---- Die Form, in der das Frontend zurueckliefert (#61a) -------------------


def test_bubble_text_reads_the_shape_gradio_sends_back():
    """Was wir hineingeben, ist nicht, was zurueckkommt.

    Gradio 6 reicht eine Anzeige-Zeile aufbereitet zurueck: `content` ist dort
    eine **Liste von Teilen**, keine Zeichenkette. Mit `str()` daraus wurde
    `"[{'text': …}]"` — und der Vote-Abgleich (#65) fand den Text nie im
    LLM-Verlauf wieder. Jede Bewertung fiel lautlos unter den Tisch.
    """
    from ui.webui_format import bubble_text

    from_frontend = {
        "role": "assistant",
        "metadata": None,
        "content": [{"type": "text", "text": "ECHO: Bewerte mich"}],
    }
    assert bubble_text(from_frontend) == "ECHO: Bewerte mich"


def test_bubble_text_still_reads_a_plain_string():
    """Beide Formen stehen im selben Verlauf nebeneinander.

    Zeilen, die wir gerade selbst angehaengt haben, sind noch Strings; erst
    die Runde ueber das Frontend macht Listen daraus.
    """
    from ui.webui_format import bot_bubble, bubble_text

    assert bubble_text(bot_bubble("Antwort")) == "Antwort"


def test_bubble_text_survives_junk_instead_of_guessing():
    from ui.webui_format import bubble_text

    assert bubble_text(None) == ""
    assert bubble_text({"role": "assistant"}) == ""
    assert bubble_text({"role": "assistant", "content": []}) == ""
    # Teile ohne Text (z. B. ein Bild) tragen nichts zum Wortlaut bei.
    assert bubble_text({"content": [{"type": "image", "path": "/x.png"}]}) == ""


def test_find_question_reads_the_frontend_shape_too():
    """Sonst stuende in der Vote-Zeile eine Frage wie `[{'text': …}]`."""
    history = [
        {"role": "user", "content": [{"type": "text", "text": "Frage?"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Antwort"}]},
    ]
    assert find_question_for_row(history, 1) == "Frage?"
