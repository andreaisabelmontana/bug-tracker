import pytest
from fastapi.testclient import TestClient

from app.api import create_app


@pytest.fixture
def client():
    """A TestClient over a fresh in-memory, seeded app per test."""
    app = create_app(db_path=":memory:", seed=True)
    with TestClient(app) as c:
        yield c
