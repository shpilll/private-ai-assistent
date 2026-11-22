from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import models
from app.db.confirmations import propose_deletion
from app.db.records import Records
from app.db.search import IndexStore
from app.knowledge import schemas
from app.rag.providers import Embeddings
from app.rag.routes import SearchQuery
from app.rag.service import retrieve


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Target(Arguments):
    id: schemas.LinkId


class TaskUpdate(Target):
    changes: schemas.TaskPatch = Field(min_length=1)


class GoalUpdate(Target):
    changes: schemas.GoalPatch = Field(min_length=1)


class Page(Arguments):
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=50)


class Search(SearchQuery):
    model_config = ConfigDict(extra="forbid")


@dataclass
class Tool:
    description: str
    arguments: type[BaseModel]
    execute: Callable

    def schema(self, name):
        return {"type": "function", "function": {"name": name, "description": self.description,
                "parameters": self.arguments.model_json_schema()}}


def registry(db: Session, index: IndexStore, embeddings: Embeddings):
    def create(model, view):
        def execute(args):
            row = Records(db, model).create(args.model_dump())
            return view.model_validate(row).model_dump(mode="json")
        return execute

    def update(model, view):
        def execute(args):
            row = Records(db, model).update(args.id, args.changes)
            return view.model_validate(row).model_dump(mode="json")
        return execute

    def listing(model, view):
        def execute(args):
            rows = Records(db, model).list(args.offset, args.limit)
            return [view.model_validate(row).model_dump(mode="json") for row in rows]
        return execute

    return {
        "search_knowledge": Tool("Search indexed notes and documents for relevant passages and URLs.",
                                 Search, lambda a: retrieve(index, embeddings, a)),
        "create_task": Tool("Create one task.", schemas.TaskInput, create(models.Task, schemas.TaskView)),
        "update_task": Tool("Update selected fields of an existing task.", TaskUpdate,
                            update(models.Task, schemas.TaskView)),
        "delete_task": Tool("Request user confirmation to delete one task by ID.", Target,
                            lambda a: propose_deletion(db, a.id)),
        "get_tasks": Tool("List tasks with IDs, status and due dates.", Page, listing(models.Task, schemas.TaskView)),
        "create_goal": Tool("Create one goal.", schemas.GoalInput, create(models.Goal, schemas.GoalView)),
        "update_goal": Tool("Update selected fields of an existing goal.", GoalUpdate,
                            update(models.Goal, schemas.GoalView)),
        "get_projects": Tool("List projects with IDs.", Page, listing(models.Project, schemas.ProjectView)),
        "save_note": Tool("Save a note for later retrieval.", schemas.NoteInput, create(models.Note, schemas.NoteView)),
    }
