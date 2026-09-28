from sqlmodel import SQLModel, Session, create_engine
from .config import get_settings


def make_engine():
    url = get_settings().app_database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = make_engine()


def init_db():
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

