from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from .provider import AiApiProvider
import logging
import traceback

# Globale, austauschbare Abhängigkeit:
_provider: Optional[AiApiProvider] = None

def set_provider(p: AiApiProvider) -> None:
    global _provider
    _provider = p

def get_provider() -> AiApiProvider:
    global _provider
    if _provider is None:
        _provider = AiApiProvider()  
    return _provider

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)

class AskResponse(BaseModel):
    answer: str

app = FastAPI(title="Leah One‑Shot API", version="1.0.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        provider = get_provider()
        ans = provider.answer(req.question)
        return AskResponse(answer=ans.strip())
    except Exception as e:
        logging.error(e)
        logging.error(f"Fehler in der API:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
