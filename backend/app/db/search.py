from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, insert, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Note
from app.db.records import RecordMissing

SourceKind = Literal["notes", "documents"]
SOURCES = {"notes": (Note, Chunk.note_id), "documents": (Document, Chunk.document_id)}


@dataclass(frozen=True)
class Snapshot:
    kind: SourceKind
    id: int
    revision: int
    body: str


class IndexStore:
    def __init__(self, engine):
        self.engine = engine

    def candidate(self, kind, profile):
        model, _ = SOURCES[kind]
        with Session(self.engine) as db:
            row = db.execute(select(model.id, model.revision, model.body).where(or_(
                model.index_state == "pending", model.profile.is_distinct_from(profile)
            )).order_by(model.id).limit(1)).first()
            return Snapshot(kind, *row) if row else None

    def publish(self, source, profile, chunks, error=None):
        model, link = SOURCES[source.kind]
        with Session(self.engine) as db, db.begin():
            row = db.get(model, source.id, with_for_update=True)
            if row is None or row.revision != source.revision:
                return False
            # Two workers can pick the same revision before either one finishes.
            if row.index_state == "ready" and row.profile == profile:
                return False
            db.execute(delete(Chunk).where(link == source.id))
            if chunks:
                db.execute(insert(Chunk), [{link.key: source.id, **part} for part in chunks])
            row.profile = profile
            row.index_state = "failed" if error else "ready"
            row.index_error = error
            return True

    def requeue(self, kind, source_id):
        model, _ = SOURCES[kind]
        with Session(self.engine) as db, db.begin():
            row = db.get(model, source_id, with_for_update=True)
            if row is None:
                raise RecordMissing()
            row.invalidate()

    def status(self, kind, source_id, profile):
        model, _ = SOURCES[kind]
        with Session(self.engine) as db:
            row = db.execute(select(model.revision, model.index_state, model.index_error, model.profile)
                             .where(model.id == source_id)).one_or_none()
            if row is None:
                raise RecordMissing()
            current = row.profile == profile
            return {"revision": row.revision, "state": row.index_state if current else "pending",
                    "error": row.index_error if current else None}

    def search(self, vector, profile, limit, category_id=None, kind=None):
        distance = Chunk.embedding.cosine_distance(vector).label("distance")
        queries = []
        for source_kind, (model, link) in SOURCES.items():
            if kind and kind != source_kind:
                continue
            query = select(literal(source_kind).label("kind"), model.id.label("source_id"),
                           model.title, Chunk.start, Chunk.text, distance).join_from(Chunk, model, link == model.id)
            query = query.where(model.index_state == "ready", model.profile == profile)
            if category_id is not None:
                query = query.where(model.category_id == category_id)
            queries.append(query)
        matches = union_all(*queries).subquery()
        statement = select(matches).order_by(matches.c.distance, matches.c.kind, matches.c.source_id,
                                             matches.c.start).limit(limit)
        with Session(self.engine) as db:
            return [dict(row) for row in db.execute(statement).mappings()]
