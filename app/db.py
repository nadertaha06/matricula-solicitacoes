from functools import lru_cache
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from app.config import get_settings


class Base(DeclarativeBase):
    pass


def new_id():
    return str(uuid4())


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5)


def session_scope():
    with Session(get_engine()) as session:
        yield session


def init_db():
    # Initial schema only. Subsequent schema changes require explicit migrations.
    Base.metadata.create_all(get_engine())
