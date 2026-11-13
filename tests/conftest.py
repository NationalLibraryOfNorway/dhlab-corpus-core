from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dhlab_core_api.app import make_app
from dhlab_core_api.config import Config

PEER_GYNT = 100000004
PEER_GYNT_URN = "URN:NBN:no-nb_digibok_2017020148047"
ALL_BOOKS = list(range(100000000, 100000009))


@pytest.fixture
def database_dir() -> Path:
    return Path(__file__).parent / "data/db"


@pytest.fixture
def config(database_dir: Path) -> Config:
    return Config(database_dir=database_dir, max_workers=4)


@pytest.fixture
def test_client(config: Config) -> TestClient:
    """A HTTPX client that "talks" with the API without starting up a web server."""
    return TestClient(make_app(config))
