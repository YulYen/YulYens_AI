import logging
import traceback

import core.system_checks as system_checks
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

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


app = FastAPI(title="Leah One‑Shot API", version="1.0.0")


@app.get("/health")
def health():
    # Cheap liveness probe: the process answers.
    return {"status": "ok"}


@app.get("/healthz")
def healthz(response: Response):
    # Deep readiness probe: Ollama/model/spaCy/Kiwix/VRAM. 503 on a critical fail.
    from config.config_singleton import Config

    results = system_checks.run_checks(Config())
    status = system_checks.overall_status(results)
    if status == "error":
        response.status_code = 503
    return {"status": status, "checks": [r.as_dict() for r in results]}


@app.post("/ask", response_model=AskResponse)
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
