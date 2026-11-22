import os

from sqlalchemy import URL, Connection, create_engine, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def database_url() -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )


def make_engine():
    return create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 3})


def vector_installed(connection: Connection) -> bool:
    return connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
