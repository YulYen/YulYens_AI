import logging
import traceback

import core.system_checks as system_checks
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from version import __version__

from .openai_compat import (
    OpenAIError,
    openai_error_handler,
    require_ask_access,
    validation_error_handler,
)
from .openai_compat import router as openai_router
from .provider import AiApiProvider, UnknownPersonaError

# Global, swappable dependency:
_provider: AiApiProvider | None = None


def set_provider(p: AiApiProvider) -> None:
    global _provider
    _provider = p


def get_provider() -> AiApiProvider:
    global _provider
    if _provider is None:
        raise RuntimeError("AiApiProvider not set; call set_provider() first")
    return _provider


class AskRequest(BaseModel):
    question: str = Field(..., min_length=0)
    persona: str = Field(..., min_length=0)


class AskResponse(BaseModel):
    answer: str


# Die OpenAPI-Version ist bewusst dieselbe wie die des Projekts (#74). Sie
# meint streng genommen die API-Fläche, nicht die App — aber ein fest
# eingetragener Literal daneben wäre eine Zahl, die nie mitwandert und trotzdem
# wie eine Aussage aussieht.
app = FastAPI(title="Leah One‑Shot API", version=__version__)

# Der /v1-Router wird immer gemountet; ob er antwortet, entscheidet
# api.openai_compatible.enabled pro Request (#37). Eine Weiche an dieser Stelle
# wäre nur scheinbar wirksam — zum Import-Zeitpunkt dieses Moduls gibt es die
# Config-Singleton noch nicht.
app.include_router(openai_router)
# Eigene Handler, damit die Fehler-Bodies unter /v1 die OpenAI-Form haben:
# {"error": {...}} statt FastAPIs {"detail": ...}.
app.add_exception_handler(OpenAIError, openai_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.get("/health")
def health():
    # Cheap liveness probe: the process answers. Carries the version because
    # this endpoint needs no API key — without an artifact and without a tag,
    # "which build is running?" is otherwise unanswerable from the outside.
    return {"status": "ok", "version": __version__}


@app.get("/healthz")
def healthz(response: Response):
    # Deep readiness probe: Ollama/model/spaCy/Kiwix/VRAM. 503 on a critical fail.
    from config.config_singleton import Config

    results = system_checks.run_checks(Config())
    status = system_checks.overall_status(results)
    if status == "error":
        response.status_code = 503
    return {
        "status": status,
        "version": __version__,
        "checks": [r.as_dict() for r in results],
    }


# Derselbe Schlüssel und dasselbe Rate-Limit wie unter /v1: /ask bietet
# dieselbe Fähigkeit auf demselben Port an, war aber ungeschützt — wer
# api.openai_compatible.api_key setzte, hielt die API für abgesichert.
@app.post(
    "/ask", response_model=AskResponse, dependencies=[Depends(require_ask_access)]
)
def ask(req: AskRequest):
    try:
        provider = get_provider()
        ans = provider.answer(req.question, req.persona)
        return AskResponse(answer=ans.strip())
    except UnknownPersonaError as e:
        logging.warning("Invalid persona requested: %s", req.persona)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.error("API error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
