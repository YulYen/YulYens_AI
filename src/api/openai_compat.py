"""OpenAI-compatible endpoints (#37): ``/v1/models`` and ``/v1/chat/completions``.

The point is reach, not novelty: every OpenAI client (Open WebUI, phone apps,
editor plugins) can talk to the personas — and unlike raw Ollama it goes through
the guard, the wiki injection and the conversation log, because it uses the very
same streamer the UI uses.

Mapping: ``model`` is the persona name. ``/v1/models`` therefore lists personas,
not LLMs — the underlying model stays a server-side decision (``core.model_name``,
or the session override from the WebUI).

V1 passes the client history through untouched. An OpenAI client owns its context
window, so Karl and the heuristic trimming deliberately stay out of the way; a
history that exceeds ``num_ctx`` is the client's problem, as with any OpenAI
endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from threading import Lock
from typing import Any, Literal

from core.context_utils import approx_token_count
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .provider import UnknownPersonaError

# ---- Request/response models ---------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
    # Accepted and ignored on purpose: the sampling parameters live with the
    # persona (ensembles/*/personas_base.yaml). Silently accepting them keeps
    # clients that always send them working; honouring them would let any
    # caller flatten a persona's character.
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    n: int | None = None
    stop: Any = None
    user: str | None = None


class OpenAIError(Exception):
    """Carries an OpenAI-shaped error to the handler registered on the app.

    Not an HTTPException: FastAPI serializes those as ``{"detail": ...}``, so
    the body would come out as ``{"detail": {"error": {...}}}`` — one level too
    deep for clients that read ``error.message`` (verified against the official
    openai SDK, which exposes exactly that body).
    """

    def __init__(
        self, status: int, message: str, err_type: str, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.payload = {
            "error": {
                "message": message,
                "type": err_type,
                "param": None,
                "code": code,
            }
        }


def _error(status: int, message: str, err_type: str, code: str | None = None):
    return OpenAIError(status, message, err_type, code)


def openai_error_handler(_request: Request, exc: OpenAIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.payload)


def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map FastAPI's 422 body to the OpenAI shape — but only under /v1.

    A client that sends a malformed request should get an error it can parse;
    /ask keeps FastAPI's default so existing callers are unaffected.
    """
    if not request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=422, content={"detail": jsonable_encoder(exc.errors())}
        )
    first = (exc.errors() or [{}])[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = first.get("msg", "Invalid request.")
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": f"{message} ({location})" if location else message,
                "type": "invalid_request_error",
                "param": location or None,
                "code": None,
            }
        },
    )


# ---- Config helpers ------------------------------------------------------


def _openai_cfg(cfg) -> dict:
    api_cfg = dict(getattr(cfg, "api", {}) or {})
    return dict(api_cfg.get("openai_compatible", {}) or {})


def resolve_secret(value: Any) -> str:
    """Same convention as the mail adapter: literal, ``env:NAME`` or ``${NAME}``."""
    if isinstance(value, dict) and "env" in value:
        return os.environ.get(str(value["env"]), "")
    if value is None:
        return ""
    text = str(value)
    if text.startswith("env:"):
        return os.environ.get(text[4:].strip(), "")
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text.strip())
    if match:
        return os.environ.get(match.group(1), "")
    return text


# ---- Rate limiting -------------------------------------------------------


class RateLimiter:
    """Fixed-window counter per client, in-process.

    Deliberately simple: this guards a hobby server on a LAN against a runaway
    script, not a public endpoint against abuse. One Ollama backend serializes
    requests anyway, so the useful limit is small.
    """

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = max(0, int(limit_per_minute))
        self._lock = Lock()
        self._windows: dict[str, tuple[int, int]] = {}

    def check(self, client: str, now: float | None = None) -> bool:
        if self.limit <= 0:  # 0 disables the limit
            return True
        minute = int((now if now is not None else time.time()) // 60)
        with self._lock:
            window, count = self._windows.get(client, (minute, 0))
            if window != minute:
                window, count = minute, 0
            if count >= self.limit:
                return False
            self._windows[client] = (window, count + 1)
            return True


_rate_limiter: RateLimiter | None = None


def _limiter(cfg) -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            int(_openai_cfg(cfg).get("rate_limit_per_minute", 60) or 0)
        )
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Test hook: drop the cached limiter so a new config takes effect."""
    global _rate_limiter
    _rate_limiter = None


# ---- Dependencies --------------------------------------------------------


def _get_config():
    from config.config_singleton import Config

    return Config()


def require_access(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Feature flag, optional bearer key and rate limit — all from config."""
    cfg = _get_config()
    settings = _openai_cfg(cfg)

    if not bool(settings.get("enabled", True)):
        # 404 statt 403: ein abgeschalteter Endpunkt soll aussehen, als gäbe es
        # ihn nicht — kein Hinweis darauf, dass hier etwas zu holen wäre.
        raise _error(404, "Not Found", "invalid_request_error")

    expected = resolve_secret(settings.get("api_key"))
    if expected:
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        if provided != expected:
            raise _error(
                401,
                "Incorrect API key provided.",
                "invalid_request_error",
                "invalid_api_key",
            )

    client = request.client.host if request.client else "unknown"
    if not _limiter(cfg).check(client):
        raise _error(
            429,
            "Rate limit exceeded. Slow down or raise "
            "api.openai_compatible.rate_limit_per_minute.",
            "rate_limit_error",
            "rate_limit_exceeded",
        )


# ---- Payload helpers -----------------------------------------------------


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _usage(messages: list[dict], reply: str) -> dict:
    prompt_tokens = approx_token_count(messages)
    completion_tokens = approx_token_count(
        [{"role": "assistant", "content": reply}], per_request_overhead=0
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _chunk_payload(
    completion_id: str, created: int, model: str, delta: dict, finish: str | None
) -> dict:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---- Router --------------------------------------------------------------

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


@router.get("/models", dependencies=[Depends(require_access)])
def list_models():
    from .app import get_provider

    provider = get_provider()
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": created,
                "owned_by": "yulyen",
            }
            for name in provider.known_personas()
        ],
    }


@router.post("/chat/completions", dependencies=[Depends(require_access)])
def chat_completions(req: ChatCompletionRequest):
    from .app import get_provider

    provider = get_provider()
    try:
        persona = provider.resolve_persona(req.model)
    except UnknownPersonaError as exc:
        raise _error(404, str(exc), "invalid_request_error", "model_not_found") from exc

    messages = [m.model_dump() for m in req.messages]
    completion_id = _completion_id()
    created = int(time.time())

    if not req.stream:
        reply = "".join(provider.stream_messages(messages, persona)).strip()
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": persona,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
            "usage": _usage(messages, reply),
        }

    def event_stream() -> Iterator[str]:
        # Erster Chunk trägt nur die Rolle — so erwarten es OpenAI-Clients.
        yield _sse(
            _chunk_payload(completion_id, created, persona, {"role": "assistant"}, None)
        )
        try:
            for token in provider.stream_messages(messages, persona):
                yield _sse(
                    _chunk_payload(
                        completion_id, created, persona, {"content": token}, None
                    )
                )
        except Exception:
            # Ein Fehler mitten im Stream kann keinen HTTP-Status mehr setzen;
            # der Client bekommt ein finish_reason und einen Log-Eintrag.
            logging.exception("OpenAI-compatible stream failed for %s", persona)
            yield _sse(_chunk_payload(completion_id, created, persona, {}, "error"))
            yield "data: [DONE]\n\n"
            return
        yield _sse(_chunk_payload(completion_id, created, persona, {}, "stop"))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
