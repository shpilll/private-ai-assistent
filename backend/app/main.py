from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.chat.routes import router as chat_router
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import make_engine, vector_installed
from app.agent.routes import router as agent_router
from app.db.records import InvalidReference, RecordMissing
from app.knowledge.routes import router
from app.rag.providers import ProviderError
from app.rag.wiring import open_providers
from app.rag.routes import router as rag_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    app.state.engine = engine
    try:
        with open_providers() as providers:
            app.state.ai = providers
            yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Personal AI Assistant",
    description=(
        "Manage a personal knowledge base, search notes and documents by meaning, "
        "and stream conversations with a tool-calling assistant. "
        "Knowledge base CRUD and document uploads work without an AI provider."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(rag_router)
app.include_router(agent_router)
app.include_router(chat_router)


@app.exception_handler(ProviderError)
async def provider_error(request: Request, exc: ProviderError):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(RecordMissing)
async def missing_record(request: Request, exc: RecordMissing):
    return JSONResponse({"detail": "Record not found"}, status_code=404)


@app.exception_handler(InvalidReference)
async def invalid_reference(request: Request, exc: InvalidReference):
    return JSONResponse({"detail": "Linked record does not exist"}, status_code=422)


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"], responses={503: {"description": "Database or vector extension unavailable"}})
def ready(request: Request) -> dict[str, str]:
    try:
        with request.app.state.engine.connect() as connection:
            installed = vector_installed(connection)
    except SQLAlchemyError as exc:
        logger.exception("Database readiness check failed")
        raise HTTPException(503, "Database unavailable") from exc
    if not installed:
        raise HTTPException(503, "Vector extension missing")
    return {"status": "ready"}


if Path("static/index.html").is_file():
    app.mount("/", StaticFiles(directory="static", html=True), name="chat-ui")
