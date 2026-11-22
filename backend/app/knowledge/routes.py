from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db import models
from app.db.records import Records
from app.knowledge import schemas


def session_for_request(request: Request):
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


def crud_router(path, model, input_schema, output_schema, patch_schema):
    routes = APIRouter(prefix=f"/{path}", tags=[path])

    def repository(session: Session = Depends(session_for_request)):
        return Records(session, model)

    @routes.get("", response_model=list[output_schema])
    def list_records(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                     records: Records = Depends(repository)):
        return records.list(offset, limit)

    @routes.post("", response_model=output_schema, status_code=201)
    def create_record(data: input_schema, records: Records = Depends(repository)):
        return records.create(data.model_dump())

    @routes.get("/{record_id}", response_model=output_schema)
    def get_record(record_id: schemas.LinkId, records: Records = Depends(repository)):
        return records.get(record_id)

    @routes.patch("/{record_id}", response_model=output_schema)
    def update_record(record_id: schemas.LinkId, data: patch_schema, records: Records = Depends(repository)):
        return records.update(record_id, data)

    @routes.delete("/{record_id}", status_code=204)
    def delete_record(record_id: schemas.LinkId, records: Records = Depends(repository)) -> Response:
        records.delete(record_id)
        return Response(status_code=204)

    return routes


router = APIRouter(prefix="/api")
router.include_router(crud_router("categories", models.Category, schemas.CategoryInput,
                                schemas.CategoryView, schemas.CategoryPatch))
router.include_router(crud_router("projects", models.Project, schemas.ProjectInput,
                                schemas.ProjectView, schemas.ProjectPatch))
router.include_router(crud_router("goals", models.Goal, schemas.GoalInput,
                                schemas.GoalView, schemas.GoalPatch))
router.include_router(crud_router("tasks", models.Task, schemas.TaskInput,
                                schemas.TaskView, schemas.TaskPatch))
router.include_router(crud_router("notes", models.Note, schemas.NoteInput,
                                schemas.NoteView, schemas.NotePatch))
