from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Runtime configuration, read from environment variables or a local ``.env`` file (see ``.env.example``)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_dir: Path = Path("./db/ft")
    """Directory containing ``urns.db``, ``metadata.db`` and the ``alto_*.db`` shards."""

    max_workers: int = Field(default=8, ge=1)
    """Maximum number of shards queried concurrently."""

    root_path: str = ""
    """URL prefix the API is served under when behind a reverse proxy, e.g. ``/dhlab``."""
