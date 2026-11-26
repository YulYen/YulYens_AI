"""MCP server (#39): the personas as tools for an MCP client.

A thin layer, on purpose. ``PersonaTools`` holds the three tools as plain
methods on top of what already exists — the one-shot provider for a single
persona, the broadcast for all of them — and knows nothing about MCP, so it is
testable without the SDK. ``build_server`` only binds them to an ``MCPServer``.

What comes along because it lives in the paths underneath, not here:

- **Guard on input and output** — in the streamer, as for ``/ask``.
- **Wiki context** — ``ask_persona`` through ``respond_one_shot``; ``ask_all``
  fetches once for all personas, guard first (#88), like Terminal and WebUI.
- **Recording** — ``ask_persona`` is a solo conversation and lands in the store
  as app ``mcp``. ``ask_all`` does not record, like every broadcast (#77).

Not here, deliberately: a wiki tool. ``WikiLookup.snippets`` finds keywords in
a *question* (spaCy); a client would pass a *title*, which is a second fetch
path with its own guard check — a follow-up, not part of the wrapper.

**stdout belongs to the protocol** over stdio. The SDK diverts file descriptor
1 to stderr while it serves, so a stray ``print`` in the app cannot corrupt a
message; logging goes to stderr anyway (``logging.StreamHandler``).
"""

from __future__ import annotations

from typing import Any

from yulyen_ai.config import personas
from yulyen_ai.config.config_singleton import Config
from yulyen_ai.core.orchestrator import broadcast_to_ensemble
from yulyen_ai.core.utils import is_broadcast_enabled
from yulyen_ai.security.tinyguard import input_refused
from yulyen_ai.wiki.lookup import inject_wiki_context

SERVER_NAME = "yulyen-orchestra"
RECORDED_AS = "mcp"


class ToolError(ValueError):
    """A request the tools refuse; the client sees the message."""


class PersonaTools:
    """The MCP tools as plain methods — no SDK, no event loop."""

    def __init__(self, factory: Any) -> None:
        self.factory = factory
        self.provider = factory.get_one_shot_provider()

    def persona_names(self) -> tuple[str, ...]:
        return tuple(self.provider.known_personas())

    def list_personas(self) -> list[dict[str, str]]:
        return [
            {"name": name, "description": personas.get_description(name)}
            for name in self.persona_names()
        ]

    def ask_persona(self, persona: str, question: str) -> str:
        from yulyen_ai.api.provider import UnknownPersonaError

        if not (question or "").strip():
            raise ToolError("question is empty")
        try:
            return str(self.provider.answer(question, persona, app=RECORDED_AS))
        except UnknownPersonaError as exc:
            raise ToolError(str(exc)) from exc

    def ask_all(self, question: str) -> dict[str, str]:
        question = (question or "").strip()
        if not question:
            raise ToolError("question is empty")
        if not is_broadcast_enabled(Config()):
            raise ToolError("ask_all is switched off (ui.experimental.broadcast_mode)")

        # Wie Terminal und WebUI: einmal für alle, und erst der Guard, dann das
        # Netz (#88). Die Absage selbst kommt aus jedem Streamer.
        context_messages: list[dict[str, str]] = []
        guard = self.factory.build_guard()
        if not input_refused(guard, question):
            _hints, contexts = self.provider.wiki.snippets(question, "ask_all", guard)
            if contexts:
                inject_wiki_context(context_messages, contexts, guard)

        results = broadcast_to_ensemble(
            self.factory, question, context_messages=context_messages
        )
        return {r["persona"]: r["reply"].strip() for r in results}


def build_server(tools: PersonaTools) -> Any:
    """Bind the tools to an ``MCPServer``. Needs ``pip install mcp``."""
    from collections.abc import Callable

    import anyio.to_thread
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as SdkToolError

    async def _off_loop(fn: Callable[..., Any], *args: str) -> Any:
        # Die Antwort braucht Sekunden bis Minuten und blockiert (Ollama,
        # Wiki): in einen Thread, damit der Server derweil Pings beantwortet.
        # Nur die *erwartete* Absage geht mit Text an den Client — alles andere
        # zeigt das SDK als „Error executing tool“, ohne Interna preiszugeben.
        try:
            return await anyio.to_thread.run_sync(fn, *args)
        except ToolError as exc:
            raise SdkToolError(str(exc)) from exc

    names = ", ".join(tools.persona_names())
    server = MCPServer(
        name=SERVER_NAME,
        instructions=(
            "Yul Yen's AI Orchestra: local personas on a local model. "
            f"Personas: {names}. Each has its own voice; use list_personas to "
            "see who is who, ask_persona for one, ask_all for every one."
        ),
    )

    @server.tool(description="List the personas with a one-line description each.")
    async def list_personas() -> list[dict[str, str]]:
        return tools.list_personas()

    @server.tool(
        description=(
            f"Ask one persona ({names}) a question and get its answer. "
            "Each call is a fresh conversation without memory of earlier calls."
        )
    )
    async def ask_persona(persona: str, question: str) -> str:
        return await _off_loop(tools.ask_persona, persona, question)

    @server.tool(
        description=(
            "Ask every persona the same question; returns persona name → answer. "
            "Takes about as long as the slowest persona or longer."
        )
    )
    async def ask_all(question: str) -> dict[str, str]:
        return await _off_loop(tools.ask_all, question)

    return server


def configure_process(cfg: Config) -> None:
    """Settings that hold for this process only; ``config.yaml`` stays untouched.

    **No UI runs here.** ``ui.type`` in the shared config usually says ``web``,
    and with it the factory applies the web UI's rule "no login, no recording"
    (#72). That rule exists because every web visitor would be the same user;
    an MCP client over stdio is one local user, like the terminal and the API,
    which record as ``local``. Without this line the MCP server would record
    nothing on a default installation, silently.
    """
    cfg.override("ui", {"type": None})


def main(argv: list[str] | None = None) -> int:
    """``python scripts/mcp_server.py -e classic`` — serves over stdio."""
    import argparse
    import logging
    import os
    from datetime import datetime

    from yulyen_ai.config.logging_setup import init_logging
    from yulyen_ai.core.utils import ensure_dir_exists, wiki_mode_enabled

    parser = argparse.ArgumentParser(
        prog="mcp_server.py", description="The personas as MCP tools (#39)."
    )
    parser.add_argument("-e", "--ensemble", default=None)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    try:
        import mcp  # noqa: F401
    except ImportError:
        parser.exit(2, "The MCP server needs the SDK: pip install 'mcp>=2.3,<3'\n")

    cfg = Config(path=os.path.abspath(args.config))
    cfg.ensemble = args.ensemble or getattr(cfg, "ensemble", None)
    if not cfg.ensemble:
        parser.error("Missing required parameter: --ensemble / -e (e.g. -e classic)")
    configure_process(cfg)

    # Nur in die Datei: was ein MCP-Client von stderr mitliest, landet je
    # nach Client im Log seines Nutzers, und dort hat ein Boot-Protokoll
    # nichts verloren.
    ensure_dir_exists(cfg.logging["dir"])
    init_logging(
        loglevel=str(cfg.logging["level"]),
        logfile=os.path.join(
            cfg.logging["dir"], f"yulyen_mcp_{datetime.now():%Y-%m-%d_%H-%M}.log"
        ),
        to_console=False,
    )
    if wiki_mode_enabled((getattr(cfg, "wiki", {}) or {}).get("mode")):
        try:
            from yulyen_ai.launch import start_wiki_proxy_thread

            start_wiki_proxy_thread()
        except Exception as exc:  # ohne Wiki antworten ist besser als gar nicht
            logging.warning(f"[MCP] Wiki proxy could not be started: {exc}")

    from yulyen_ai.core.factory import AppFactory

    build_server(PersonaTools(AppFactory())).run("stdio")
    return 0
