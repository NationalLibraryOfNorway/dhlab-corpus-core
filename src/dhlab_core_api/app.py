from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dhlab_core_api.config import Config
from dhlab_core_api.errors import InvalidQueryError
from dhlab_core_api.repository import CorpusRepository
from dhlab_core_api.service import CorpusService
from dhlab_core_api.v1.routes import get_v1_router
from dhlab_core_api.v2.routes import get_v2_router


def make_app(config: Config | None = None) -> FastAPI:
    if config is None:
        config = Config()

    repository = CorpusRepository(config.database_dir, max_workers=config.max_workers)
    service = CorpusService(repository=repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        repository.close()

    app = FastAPI(
        title="DH-lab API",
        description="Corpus building, concordances, collocations, word totals and n-grams for the DH-lab collection.",
        root_path=config.root_path,
        lifespan=lifespan,
    )
    app.include_router(get_v1_router(service=service))
    app.include_router(get_v2_router(service=service))

    @app.exception_handler(InvalidQueryError)
    def invalid_query(request: Request, error: InvalidQueryError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.get("/")
    def read_root() -> dict[str, str]:
        """Landing page: points to the documentation and to where each API version is mounted."""
        return {"name": "DH-lab API", "docs": "/docs", "v1": "/", "v2": "/v2"}

    return app
