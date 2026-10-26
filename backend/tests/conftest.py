"""API fixtures use isolated SQLite files and run the application lifespan."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from once_wrong.main import create_app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "api-test.sqlite3"


@pytest.fixture
def client(database_path: Path):
    with TestClient(create_app(database_path, seed_demo=True)) as test_client:
        yield test_client


@pytest.fixture
def csv_fixtures() -> dict[str, bytes]:
    directory = Path(__file__).parent / "fixtures"
    return {
        name: (directory / name).read_bytes() for name in ("sample-errors.csv", "sample-fixed.csv")
    }
