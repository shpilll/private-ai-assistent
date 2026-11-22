from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, literal_column, select
from sqlalchemy.orm import Session

from app.db.models import PendingDeletion, Task
from app.db.records import RecordMissing


class ConfirmationConflict(Exception):
    pass


def task_version(db: Session, task_id: int):
    # PostgreSQL changes xmin on every UPDATE, including foreign-key actions.
    row = db.execute(select(Task, literal_column("xmin::text"))
                     .where(Task.id == task_id).with_for_update()).one_or_none()
    if row is None:
        raise RecordMissing()
    return row


def propose_deletion(db: Session, task_id: int):
    task, version = task_version(db, task_id)
    now = datetime.now(timezone.utc)
    db.execute(delete(PendingDeletion).where(PendingDeletion.expires_at <= now))
    action = PendingDeletion(id=uuid4(), task_id=task.id, version=version,
                             expires_at=now + timedelta(minutes=10))
    db.add(action)
    db.commit()
    return {"id": str(action.id), "task_id": task.id, "title": task.title,
            "expires_at": action.expires_at.isoformat()}


def decide_deletion(db: Session, action_id: UUID, confirm: bool):
    action = db.get(PendingDeletion, action_id, with_for_update=True)
    if action is None:
        raise RecordMissing()
    if action.expires_at <= datetime.now(timezone.utc):
        raise ConfirmationConflict("Confirmation expired")
    if confirm:
        task, version = task_version(db, action.task_id)
        if version != action.version:
            raise ConfirmationConflict("Task has changed since the deletion request")
        db.delete(task)
    db.delete(action)
    db.commit()
    return {"status": "deleted" if confirm else "cancelled", "task_id": action.task_id}
