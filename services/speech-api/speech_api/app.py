"""Speech API gateway: auth, limits, fair scheduling, usage logging in front of the GPU engines."""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from . import errors
from .auth import RateLimiter
from .routes import router
from .scheduler import EngineScheduler

ENGINE_TIMEOUT = httpx.Timeout(connect=2.0, read=300.0, write=60.0, pool=5.0)


def _engine_urls_from_env() -> dict[str, str]:
    return {
        "omnivoice": os.environ.get("ENGINE_OMNIVOICE_URL", "http://tts-omnivoice:8000"),
        "kokoro": os.environ.get("ENGINE_KOKORO_URL", "http://tts-kokoro:8000"),
        "asr": os.environ.get("ENGINE_ASR_URL", "http://asr-whisperx:8000"),
        # optional engines: registered only when their URL is set
        **({"indicf5": os.environ["ENGINE_INDICF5_URL"]} if os.environ.get("ENGINE_INDICF5_URL") else {}),
    }


def create_app(
    engine_urls: dict[str, str] | None = None,
    transports: dict[str, httpx.AsyncBaseTransport] | None = None,
    database_url: str | None = None,
    concurrency: int | None = None,
    max_waiting: int = 32,
) -> FastAPI:
    engine_urls = engine_urls or _engine_urls_from_env()
    transports = transports or {}
    database_url = database_url or os.environ["DATABASE_URL"]
    concurrency = concurrency or int(os.environ.get("ENGINE_CONCURRENCY", "1"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = AsyncConnectionPool(database_url, min_size=1, max_size=10, open=False,
                                           kwargs={"autocommit": True})
        await app.state.db.open()
        app.state.engines = {
            name: httpx.AsyncClient(base_url=url, timeout=ENGINE_TIMEOUT, transport=transports.get(name))
            for name, url in engine_urls.items()
        }
        app.state.schedulers = {name: EngineScheduler(name, concurrency, max_waiting) for name in engine_urls}
        app.state.limiter = RateLimiter()
        try:
            yield
        finally:
            for c in app.state.engines.values():
                await c.aclose()
            await app.state.db.close()

    # Interactive docs only on request (SPEECH_API_DOCS=1): the API is public, its docs page need not be.
    docs = os.environ.get("SPEECH_API_DOCS", "0") == "1"
    app = FastAPI(title="EduVid Speech API", version="1.0", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url=None, openapi_url="/openapi.json" if docs else None)
    errors.install(app)
    app.include_router(router)
    return app


def __getattr__(name: str):
    # `uvicorn speech_api.app:app` builds the app lazily so importing this module in tests needs no env
    if name == "app":
        return create_app()
    raise AttributeError(name)
