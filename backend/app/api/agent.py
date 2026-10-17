"""Agent endpoint: a coordinator's question about one case, answered through the IRIS tools."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.chat import ChatModel, ChatResult, GatewayChatModel, run_chat
from app.api.errors import NotFoundError
from app.app_db.models import Case
from app.app_db.session import get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=1000)


@lru_cache
def _model() -> ChatModel:
    return GatewayChatModel()


def get_chat_model() -> ChatModel:
    return _model()


@router.post("/chat", response_model=ChatResult)
def chat(body: ChatRequest, db: Session = Depends(get_db), model: ChatModel = Depends(get_chat_model)) -> ChatResult:
    case = db.get(Case, body.case_id)
    if case is None:
        raise NotFoundError("Případ nebyl nalezen")
    return run_chat(case.id, case.patient_id, body.question, model)
