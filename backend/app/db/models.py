from datetime import date, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Record(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))


class Category(Record):
    __tablename__ = "categories"


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    request_id: Mapped[UUID]
    prompt: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB)


class PendingDeletion(Base):
    __tablename__ = "pending_deletions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[int]
    version: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClassifiedRecord(Record):
    __abstract__ = True

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))


class Project(ClassifiedRecord):
    __tablename__ = "projects"

    description: Mapped[str] = mapped_column(Text, server_default="")


class Goal(ClassifiedRecord):
    __tablename__ = "goals"

    description: Mapped[str] = mapped_column(Text, server_default="")
    target_date: Mapped[date | None]


class Task(ClassifiedRecord):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="task_status"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="task_priority"),
    )

    description: Mapped[str] = mapped_column(Text, server_default="")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), server_default="todo")
    priority: Mapped[str] = mapped_column(String(16), server_default="normal")
    due_date: Mapped[date | None]


class Indexable:
    revision: Mapped[int] = mapped_column(server_default="1")
    index_state: Mapped[str] = mapped_column(server_default="pending")
    profile: Mapped[str | None]
    index_error: Mapped[str | None]

    def invalidate(self):
        self.revision += 1
        self.index_state = "pending"
        self.index_error = None


class Note(Indexable, ClassifiedRecord):
    __tablename__ = "notes"

    body: Mapped[str] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))


class Document(Indexable, ClassifiedRecord):
    __tablename__ = "documents"

    body: Mapped[str] = mapped_column(Text, deferred=True)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("num_nonnulls(note_id, document_id) = 1", name="chunk_source"),
        UniqueConstraint("note_id", "start"), UniqueConstraint("document_id", "start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int | None] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    start: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
