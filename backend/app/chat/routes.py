import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.routes import AgentRequest
from app.agent.service import agent_events
from app.agent.tools import registry
from app.db.chat import ChatStore
from app.db.records import RecordMissing
from app.db.search import IndexStore
from app.knowledge.routes import session_for_request
from app.rag.providers import ProviderError

router = APIRouter(prefix="/api/chats", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(AgentRequest):
    request_id: UUID


@router.post("", status_code=201)
def create(db: Session = Depends(session_for_request)):
    return ChatStore(db).create()


@router.get("")
def conversations(db: Session = Depends(session_for_request)):
    return ChatStore(db).conversations()


@router.get("/{chat_id}")
def history(chat_id: UUID, db: Session = Depends(session_for_request)):
    return ChatStore(db).history(chat_id)


def line(kind, data):
    return json.dumps({"type": kind, "data": data}, ensure_ascii=False) + "\n"


def stream_turn(engine, ai, chat_id, data):
    try:
        with engine.begin() as conn, Session(conn, join_transaction_mode="create_savepoint",
                                             expire_on_commit=False) as db:
            store = ChatStore(db)
            chat = store.get(chat_id, lock=True)
            previous = store.replay(chat_id, data.request_id)
            if previous:
                if previous.prompt != data.message:
                    raise ValueError("Этот запрос уже использован для другого сообщения.")
                turn = store.view(previous)
            else:
                tools = registry(db, IndexStore(engine), ai.embeddings)
                for kind, value in agent_events(data.message, ai.tool_caller, tools, store.context(chat_id), stream=True):
                    if kind == "result":
                        turn = store.save(chat, data.request_id, data.message, value)
                    else:
                        yield line(kind, value)
                db.commit()
        yield line("done", turn)
    except RecordMissing:
        yield line("error", "Диалог не найден.")
    except (ProviderError, ValueError) as exc:
        yield line("error", str(exc))
    except Exception:
        logger.exception("Chat turn failed")
        yield line("error", "Не удалось завершить сообщение.")


@router.post(
    "/{chat_id}/messages",
    response_class=StreamingResponse,
    responses={200: {
        "description": "One JSON event per line. The stream ends with done or error.",
        "content": {"application/x-ndjson": {"schema": {"type": "string"}}},
    }},
)
def message(chat_id: UUID, data: ChatRequest, request: Request):
    """Stream text deltas and tool names. Retry with the same message and request ID
    to recover a committed turn without running its tools twice."""
    events = stream_turn(request.app.state.engine, request.app.state.ai, chat_id, data)
    return StreamingResponse(events, media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
