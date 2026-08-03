"""Reine Formatierer der WebUI — Text rein, Markdown raus.

Sie hingen als Methoden an `WebUI` (2200 Zeilen, 71 Methoden), obwohl keine
davon den Zustand der Klasse braucht: sie nehmen Daten und den Text-Formatter
der Config. Hier sind sie einzeln testbar, und die God-Class wird kleiner,
ohne dass die Handler-Logik verschoben wird.

``t`` ist überall ``Config.t`` — der i18n-Formatter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.context_utils import approx_token_count
from core.context_utils import threshold as CONTEXT_FILL_WARN_RATIO
from wiki.lookup import WikiSnippet, format_snippet_meta

if TYPE_CHECKING:
    from core.streaming_provider import StreamStats
    from storage import ConversationRef

# Ein Chatbot-Eintrag im `messages`-Format: {"role": …, "content": …}.
#
# Bis #61a waren das Paare `(User-Text, Bot-Text)`. Gradio 6 hat den Parameter
# `type` ersatzlos entfernt — das Paarformat existiert dort nicht mehr. Der
# Wechsel ist deshalb erzwungen, aber er ist auch der ehrlichere Entwurf: eine
# Anzeige-Zeile ist *eine* Nachricht, und das Paar konnte Zustände tragen, die
# es nie gab (beide Seiten gefüllt in einer Zeile, die live nie so entsteht).
ChatMessage = dict[str, str]
Message = dict[str, str]

# Übergangsname. Wer ihn noch importiert, bekommt jetzt das neue Format —
# das ist Absicht: eine stille Weiterverwendung der Paare wäre schlimmer.
ChatPair = ChatMessage


def bot_bubble(text: str) -> ChatMessage:
    """Eine Bot-Bubble. Auch für Hinweise, die nie ins Kontextfenster gehen."""
    return {"role": "assistant", "content": text}


def user_bubble(text: str) -> ChatMessage:
    return {"role": "user", "content": text}


def messages_to_chat_history(messages: list[Message] | None) -> list[ChatMessage]:
    """LLM-Verlauf in die Anzeigeform bringen.

    Seit #61a ist das fast eine Identität — Anzeige und Verlauf haben dieselbe
    Form. Der Unterschied bleibt inhaltlich: die Anzeige trägt zusätzlich
    Hinweis-Bubbles, die nie in den LLM-Verlauf gehen, und der Verlauf kann
    injizierten Fremdkontext tragen, der nie angezeigt wird. Deshalb wird hier
    weiterhin gefiltert statt durchgereicht.
    """
    return [
        {"role": str(item.get("role")), "content": str(item.get("content") or "")}
        for item in messages or []
        if item.get("role") in ("user", "assistant")
    ]


def context_bar(ratio: float, width: int = 12) -> str:
    filled = max(0, min(width, round(ratio * width)))
    return "█" * filled + "░" * (width - filled)


def format_status_line(
    t: Any,
    persona_options: dict | None,
    history: list[Message] | None,
    stats: StreamStats | None,
) -> str:
    """Kontext-Füllstand und Tempo der letzten Antwort (#36).

    Beides misst das Projekt längst — der Füllstand steckt in
    ``context_near_limit``, die Zeiten schrieb ``stream()`` bisher nur ins
    Logfile. Sichtbar erklärt der Balken die Kompressions-Meldung, *bevor*
    sie kommt.
    """
    parts: list[str] = []
    limit = int((persona_options or {}).get("num_ctx") or 0)
    if limit > 0:
        used = approx_token_count(history or [])
        ratio = used / limit
        text = t(
            "web_status_context",
            used=f"{used:,}".replace(",", "."),
            limit=f"{limit:,}".replace(",", "."),
            percent=f"{ratio * 100:.0f}",
            bar=context_bar(ratio),
        )
        # Ab dieser Schwelle greift die Kompression — dann fett statt still.
        parts.append(f"**{text}**" if ratio >= CONTEXT_FILL_WARN_RATIO else text)

    if stats is not None and stats.tokens:
        parts.append(
            t("web_status_speed", tokens_per_second=f"{stats.tokens_per_second:.1f}")
        )
        if stats.t_first_ms is not None:
            parts.append(
                t("web_status_first_token", seconds=f"{stats.t_first_ms / 1000:.1f}")
            )
    return " · ".join(parts)


def format_wiki_sources(snippets: list[WikiSnippet] | None, t: Any) -> str:
    """Markdown für das Quellen-Accordion (#32).

    Zeigt bewusst den *injizierten* Text und dessen Länge, nicht nur Titel
    und Link: nur so ist erkennbar, worauf eine Antwort beruht — und ob der
    Artikel an ``wiki.snippet_limit`` abgeschnitten wurde, das Modell den
    Rest also nie gesehen hat.
    """
    sections = []
    for idx, snip in enumerate(snippets or [], start=1):
        title = snip.topic or "?"
        heading = f"[{title}]({snip.link})" if snip.link else title
        meta = format_snippet_meta(snip, t)
        # Blockquote: hebt den fremden Text vom Rahmen ab und bleibt auch
        # bei 1200 Zeichen am Stück lesbar.
        quoted = "\n".join(
            f"> {line}" if line.strip() else ">" for line in snip.snippet.splitlines()
        )
        sections.append(f"### {idx}. {heading}\n*{meta}*\n\n{quoted}")
    return "\n\n---\n\n".join(sections)


def format_ask_all_results(replies: dict[str, str]) -> str:
    """One markdown section per persona, separated by horizontal rules."""
    return "\n\n---\n\n".join(
        f"### {persona}\n\n{reply}" for persona, reply in replies.items()
    )


def history_label(ref: ConversationRef) -> str:
    """`2026-07-31 05:10 · PETER · Wie ist der Status …`"""
    stamp = ref.updated_at[:16].replace("T", " ")
    return f"{stamp} · {ref.persona} · {ref.title or '—'}"


def conversation_markdown(ref: ConversationRef, messages: list[Message], t: Any) -> str:
    """Ein Gespräch als Markdown — dieselbe Form für Vorschau und Export."""
    head = t(
        "history_export_head",
        persona=ref.persona,
        model=ref.model,
        created_at=ref.created_at[:16].replace("T", " "),
        user=ref.user,
    )
    lines = [f"# {ref.title or ref.persona}", "", f"*{head}*", ""]
    for message in messages:
        who = (
            ref.persona
            if message.get("role") == "assistant"
            else t("history_role_user")
        )
        lines.append(f"**{who}:** {message.get('content', '')}")
        lines.append("")
    return "\n".join(lines)


def find_question_for_row(chat_history: list[ChatMessage] | None, row: int) -> str:
    """Die Frage, zu der die bewertete Antwort gehört (#40).

    Rückwärts ab der bewerteten Zeile zur nächsten Nutzer-Nachricht: zwischen
    Frage und Antwort können Hinweis-Bubbles stehen (Wiki, RSS, Kompression),
    und ein geladenes Gespräch fängt nicht zwingend mit einer Frage an.
    """
    if not chat_history:
        return ""
    row = min(row, len(chat_history) - 1)
    for index in range(row, -1, -1):
        message = chat_history[index]
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""
