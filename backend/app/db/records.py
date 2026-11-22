from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Indexable, Record


class RecordMissing(Exception):
    pass


class InvalidReference(Exception):
    pass


class Records:
    def __init__(self, session: Session, model: type[Record]):
        self.session = session
        self.model = model

    def list(self, offset: int, limit: int):
        query = select(self.model).order_by(self.model.id).offset(offset).limit(limit)
        return self.session.scalars(query).all()

    def get(self, record_id: int, *, lock: bool = False):
        row = self.session.get(self.model, record_id, with_for_update=lock, populate_existing=lock)
        if row is None:
            raise RecordMissing()
        return row

    def create(self, values: dict):
        row = self.model(**values)
        self.session.add(row)
        self._commit()
        return row

    def update(self, record_id: int, values: dict):
        row = self.get(record_id, lock=True)
        if isinstance(row, Indexable) and "body" in values and values["body"] != row.body:
            row.invalidate()
        for key, value in values.items():
            setattr(row, key, value)
        self._commit()
        return row

    def delete(self, record_id: int):
        self.session.delete(self.get(record_id, lock=True))
        self._commit()

    def _commit(self):
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23503":
                raise InvalidReference() from error
            raise
