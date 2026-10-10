import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine


@pytest.fixture(autouse=True)
def isolate_api_test_database(request):
    """Keep API test writes out of the developer's ignored local SQLite database."""
    if request.module.__name__.endswith("test_api"):
        from app.database import get_session
        from app.main import app

        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(test_engine)

        def get_test_session():
            with Session(test_engine) as session:
                yield session

        app.dependency_overrides[get_session] = get_test_session
        yield
        app.dependency_overrides.clear()
        test_engine.dispose()
        return
    yield
