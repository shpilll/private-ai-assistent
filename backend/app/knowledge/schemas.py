from datetime import date
from typing import Annotated, Literal

from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LinkId = Annotated[int, Field(gt=0, le=2147483647)]
TaskStatus = Literal["todo", "in_progress", "done"]
Priority = Literal["low", "normal", "high"]


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    title: Title


class ProjectInput(CategoryInput):
    category_id: LinkId | None = None
    description: str = ""


class GoalInput(ProjectInput):
    target_date: date | None = None


class TaskInput(ProjectInput):
    project_id: LinkId | None = None
    goal_id: LinkId | None = None
    status: TaskStatus = "todo"
    priority: Priority = "normal"
    due_date: date | None = None


class NoteInput(CategoryInput):
    body: Annotated[str, Field(min_length=1)]
    project_id: LinkId | None = None
    category_id: LinkId | None = None


class CategoryView(CategoryInput):
    id: int


class CategoryPatch(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    title: Title


class ProjectView(ProjectInput):
    id: int


class ProjectPatch(CategoryPatch, total=False):
    category_id: LinkId | None
    description: str


class GoalView(GoalInput):
    id: int


class GoalPatch(ProjectPatch, total=False):
    target_date: date | None


class TaskView(TaskInput):
    id: int


class TaskPatch(ProjectPatch, total=False):
    project_id: LinkId | None
    goal_id: LinkId | None
    status: TaskStatus
    priority: Priority
    due_date: date | None


class NoteView(NoteInput):
    id: int


class NotePatch(CategoryPatch, total=False):
    body: Annotated[str, Field(min_length=1)]
    project_id: LinkId | None
    category_id: LinkId | None
