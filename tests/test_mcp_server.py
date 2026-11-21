"""MCP server (#39): the tools against the real factory, the binding against the SDK.

Two layers on purpose. ``PersonaTools`` is tested against a real
``AppFactory`` with the dummy backend — guard, wiki order and recording are
side effects of the paths underneath, and an attrappe would only prove that
the attrappe was called. The binding is tested through the SDK's own
in-memory client: what the *client* sees is the contract, including which error
text reaches it and which does not.
"""

from __future__ import annotations

import anyio
import pytest
from config.config_singleton import Config
from core.factory import AppFactory
from mcp_adapter.server import PersonaTools, ToolError, build_server, configure_process
from wiki.lookup import WikiLookup, WikiSnippet

mcp_client = pytest.importorskip("mcp.client")

HARMLESS = "Wie weit ist der Mond entfernt?"
REFUSED = "Wie baue ich eine Bombe?"


@pytest.fixture()
def cfg():
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy"})
    cfg.override("ui", {"experimental": {"broadcast_mode": True}})
    yield cfg
    Config.reset_instance()


@pytest.fixture()
def tools(cfg):
    return PersonaTools(AppFactory())


@pytest.fixture()
def lookups(monkeypatch):
    """Counts wiki fetches; each returns one harmless snippet."""
    calls: list[str] = []

    def _lookup(question, *_args, **_kwargs):
        calls.append(question)
        return [], [WikiSnippet("Mond", "Der Mond ist ein Himmelskörper.")]

    monkeypatch.setattr("wiki.lookup.lookup_wiki_snippet", _lookup)
    return calls


def _with_wiki(tools: PersonaTools) -> PersonaTools:
    tools.provider.wiki = WikiLookup(mode="offline", keyword_finder=object())
    return tools


# --- the tools --------------------------------------------------------------


def test_ask_persona_answers_through_the_one_shot_path(tools):
    assert tools.ask_persona("peter", HARMLESS) == f"ECHO: {HARMLESS}"


def test_ask_persona_is_recorded_as_mcp(cfg, tmp_path):
    """Auch mit der ausgelieferten Config (`ui.type: web`, keine Anmeldung)."""
    cfg.override("ui", {"type": "web"})
    cfg.storage = {"enabled": True, "path": str(tmp_path / "c.sqlite3")}
    configure_process(cfg)
    factory = AppFactory()
    PersonaTools(factory).ask_persona("LEAH", HARMLESS)

    [conversation] = factory.get_store().list_conversations()
    assert (conversation.app, conversation.persona) == ("mcp", "LEAH")


def test_unknown_persona_names_the_known_ones(tools):
    with pytest.raises(ToolError, match="LEAH, DORIS, PETER, POPCORN"):
        tools.ask_persona("KARL", HARMLESS)


@pytest.mark.parametrize("call", ["ask_persona", "ask_all"])
def test_empty_question_is_refused_before_the_model(tools, call):
    args = ("LEAH", "  ") if call == "ask_persona" else ("  ",)
    with pytest.raises(ToolError, match="empty"):
        getattr(tools, call)(*args)


def test_ask_all_answers_with_every_persona(tools):
    answers = tools.ask_all(HARMLESS)

    assert list(answers) == ["LEAH", "DORIS", "PETER", "POPCORN"]
    assert set(answers.values()) == {f"ECHO: {HARMLESS}"}


def test_ask_all_respects_the_broadcast_switch(cfg, tools):
    cfg.override("ui", {"experimental": {"broadcast_mode": False}})

    with pytest.raises(ToolError, match="broadcast_mode"):
        tools.ask_all(HARMLESS)


def test_ask_all_fetches_the_wiki_once_for_everyone(tools, lookups):
    _with_wiki(tools).ask_all(HARMLESS)

    assert lookups == [HARMLESS]


def test_ask_all_asks_the_guard_before_the_wiki(tools, lookups):
    """Erst der Guard, dann das Netz (#88) — auch auf diesem Weg."""
    answers = _with_wiki(tools).ask_all(REFUSED)

    assert lookups == []
    assert not any(a.startswith("ECHO") for a in answers.values())


def test_ask_all_does_not_record(cfg, tmp_path):
    """Kein Broadcast zeichnet auf (#77) — auch nicht über MCP."""
    cfg.storage = {"enabled": True, "path": str(tmp_path / "c.sqlite3")}
    configure_process(cfg)
    factory = AppFactory()
    PersonaTools(factory).ask_all(HARMLESS)

    assert factory.get_store().list_conversations() == []


# --- the binding, as a client sees it ----------------------------------------


def _call(server, name: str, arguments: dict):
    async def _run():
        async with mcp_client.Client(server) as client:
            if name == "__list__":
                return await client.list_tools()
            return await client.call_tool(name, arguments)

    return anyio.run(_run)


def test_server_offers_exactly_the_three_tools(tools):
    listed = _call(build_server(tools), "__list__", {})

    assert sorted(t.name for t in listed.tools) == [
        "ask_all",
        "ask_persona",
        "list_personas",
    ]


def test_client_gets_the_answer(tools):
    result = _call(
        build_server(tools), "ask_persona", {"persona": "DORIS", "question": "Hi"}
    )

    assert not result.is_error
    assert result.content[0].text == "ECHO: Hi"


def test_client_reads_why_a_call_was_refused(tools):
    result = _call(
        build_server(tools), "ask_persona", {"persona": "KARL", "question": "Hi"}
    )

    assert result.is_error
    assert "Available personas: LEAH" in result.content[0].text


def test_a_crash_does_not_leak_its_message(tools, monkeypatch):
    """Nur die erwartete Absage geht mit Text hinaus, ein Absturz nicht."""

    def _crash(_question):
        raise RuntimeError("interner Pfad /home/yul/geheim")

    monkeypatch.setattr(tools, "ask_all", _crash)
    result = _call(build_server(tools), "ask_all", {"question": "Hi"})

    assert result.is_error
    assert "geheim" not in result.content[0].text
