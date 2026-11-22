from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.db.models import Document
from app.db.records import Records
from app.db.search import IndexStore, SourceKind
from app.knowledge.routes import session_for_request
from app.knowledge.schemas import LinkId
from app.rag.chunks import index_profile
from app.rag.service import answer, retrieve

router = APIRouter(prefix="/api")


class DocumentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category_id: int | None


class DocumentCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: LinkId | None


def documents(db: Session = Depends(session_for_request)):
    return Records(db, Document)


def read_file(file: UploadFile):
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not name.lower().endswith(".txt") or len(name) > 200 or "\x00" in name:
        raise HTTPException(422, "Expected a .txt filename up to 200 characters")
    raw = file.file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Maximum file size is 1 MiB")
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Expected UTF-8 text") from exc
    if not body.lstrip("\ufeff").strip() or "\x00" in body:
        raise HTTPException(422, "Expected non-empty text without NUL bytes")
    return {"title": name, "body": body}


@router.post("/documents", tags=["documents"], response_model=DocumentInfo, status_code=201)
def upload(file: Annotated[UploadFile, File()], category_id: LinkId | None = None,
           repo: Records = Depends(documents)):
    return repo.create({**read_file(file), "category_id": category_id})


@router.get("/documents", tags=["documents"], response_model=list[DocumentInfo])
def list_documents(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                   repo: Records = Depends(documents)):
    return repo.list(offset, limit)


@router.get("/documents/{source_id}/content", tags=["documents"])
def content(source_id: LinkId, repo: Records = Depends(documents)):
    return Response(repo.get(source_id).body, media_type="text/plain; charset=utf-8")


@router.put("/documents/{source_id}", tags=["documents"], response_model=DocumentInfo)
def replace(source_id: LinkId, file: Annotated[UploadFile, File()], repo: Records = Depends(documents)):
    return repo.update(source_id, read_file(file))


@router.delete("/documents/{source_id}", tags=["documents"], status_code=204)
def delete_document(source_id: LinkId, repo: Records = Depends(documents)):
    repo.delete(source_id)
    return Response(status_code=204)


@router.patch("/documents/{source_id}", tags=["documents"], response_model=DocumentInfo)
def change_category(source_id: LinkId, data: DocumentCategory, repo: Records = Depends(documents)):
    return repo.update(source_id, data.model_dump())


class SearchQuery(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1800)]
    limit: int = Field(5, ge=1, le=8)
    category_id: LinkId | None = None
    kind: SourceKind | None = None


class Hit(BaseModel):
    kind: SourceKind
    source_id: int
    title: str
    start: int
    text: str
    distance: float
    url: str


class Answer(BaseModel):
    answer: str
    sources: list[Hit]


def store(request: Request):
    return IndexStore(request.app.state.engine)


@router.get("/index/{kind}/{source_id}", tags=["index"])
def status(kind: SourceKind, source_id: LinkId, request: Request, db: IndexStore = Depends(store)):
    embeddings = request.app.state.ai.embeddings
    return {**db.status(kind, source_id, index_profile(embeddings)), "provider_configured": embeddings.configured}


@router.post("/index/{kind}/{source_id}", tags=["index"], status_code=202)
def reindex(kind: SourceKind, source_id: LinkId, db: IndexStore = Depends(store)):
    db.requeue(kind, source_id)
    return {"state": "pending"}


@router.post("/rag/search", tags=["rag"], response_model=list[Hit])
def search(query: SearchQuery, request: Request, db: IndexStore = Depends(store)):
    return retrieve(db, request.app.state.ai.embeddings, query)


@router.post("/rag/ask", tags=["rag"], response_model=Answer)
def ask(query: SearchQuery, request: Request, db: IndexStore = Depends(store)):
    ai = request.app.state.ai
    return answer(db, ai.embeddings, ai.generator, query)
