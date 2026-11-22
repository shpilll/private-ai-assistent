from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, StrictBool, StringConstraints
from sqlalchemy.orm import Session

from app.agent.service import run_agent
from app.agent.tools import registry
from app.db.confirmations import ConfirmationConflict, decide_deletion
from app.db.search import IndexStore
from app.knowledge.routes import session_for_request

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class Decision(BaseModel):
    confirm: StrictBool


@router.post("/run")
def run(data: AgentRequest, request: Request):
    providers = request.app.state.ai
    engine = request.app.state.engine
    # CRUD commits release savepoints. Publish the complete turn only after the final answer.
    with engine.begin() as conn, Session(conn, join_transaction_mode="create_savepoint",
                                         expire_on_commit=False) as db:
        tools = registry(db, IndexStore(engine), providers.embeddings)
        result = run_agent(data.message, providers.tool_caller, tools)
        db.commit()
        return result


@router.post("/confirmations/{action_id}")
def decide(action_id: UUID, data: Decision, db: Session = Depends(session_for_request)):
    try:
        return decide_deletion(db, action_id, data.confirm)
    except ConfirmationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
