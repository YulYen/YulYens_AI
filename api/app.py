from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from .provider import AnswerProvider, EchoProvider

# Globale, austauschbare Abhängigkeit:
_provider: Optional[AnswerProvider] = None

def set_provider(p: AnswerProvider) -> None:
    global _provider
    _provider = p

def get_provider() -> AnswerProvider:
    global _provider
    if _provider is None:
        _provider = EchoProvider()  # bis wir in Schritt 2 „RealLeah“ setzen
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
        raise HTTPException(status_code=500, detail=str(e))
