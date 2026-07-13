"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import os

# Silence ChromaDB telemetry BEFORE any chromadb import anywhere in the
# import graph (chroma's __init__ spawns a posthog client at first use and
# recent posthog releases break chroma's call signature, which floods the
# log with `capture() takes 1 positional argument but 3 were given`).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "True")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import get_settings
from backend.errors import ValidationError
from backend.memory import Memory
from backend.observability.logging_config import configure_logging, get_logger
from backend.observability.request_context import RequestIDMiddleware
from backend.routes.chat import install_memory, make_exception_handler, router, _attach_request_id_json
from starlette.middleware.base import BaseHTTPMiddleware
from backend.security.rate_limit import limiter


configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    mem = Memory()
    install_memory(mem)
    log.info("startup", settings_keys=list(get_settings().model_dump().keys()))

    async def _prewarm_chroma() -> None:
        """Build the ChromaStore + HF embedding model at startup.

        Without this, the very first /chat or /admin/kb/sources request
        pays the 60-180s sentence-transformers download cost *during* the
        request — which the UI interprets as "no response". Loading up front
        keeps the first real turn snappy.
        """
        try:
            from backend.vector_store.chroma_store import ChromaStore

            def _build() -> None:
                # Triggers the HF model download + Chroma client init in a
                # thread so the asyncio event loop stays free.
                ChromaStore.instance()

            await asyncio.to_thread(_build)
            log.info("startup_prewarm_done", component="chroma")
        except Exception as e:  # noqa: BLE001
            log.warning("startup_prewarm_failed", error=str(e))

    # Best-effort: don't block startup if the model download is slow.
    asyncio.create_task(_prewarm_chroma())

    try:
        yield
    finally:
        await mem.close()


def _cors_origins() -> list[str]:
    raw = get_settings().cors_origins.strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="Mini AI Assistant", version="0.2.2", lifespan=lifespan)

    # Rate limiter state — slowapi requires this on the app.
    app.state.limiter = limiter

    # Middleware (order matters: outermost first).
    app.add_middleware(RequestIDMiddleware)
    # Cache parsed JSON body on request.state so the slowapi key_func can read session_id.
    app.add_middleware(BaseHTTPMiddleware, dispatch=_attach_request_id_json)
    # Outermost — must handle OPTIONS preflight before other middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes — registered before any catch-all so /chat, /healthz, /metrics
    # always take precedence over the SPA's index.html handler.
    app.include_router(router)

    # Serve the built SPA when present (Docker image, or after `npm run
    # build` in a checkout). Anything that isn't an API route falls through
    # to index.html so React Router can take over.
    _web_dist = os.path.join(os.path.dirname(__file__), "web", "dist")
    _index_html = os.path.join(_web_dist, "index.html")
    if os.path.isfile(_index_html):
        from fastapi.responses import FileResponse

        # Mount the SPA at /app/ first so users have an explicit UI entry
        # point that doesn't collide with the API catalog at "/".
        app.mount(
            "/app/assets",
            StaticFiles(directory=os.path.join(_web_dist, "assets")),
            name="spa-app-assets",
        )

        @app.get("/app/{full_path:path}", include_in_schema=False)
        async def _spa_app_route(full_path: str):  # type: ignore[no-untyped-def]
            """SPA under /app/ — real files win, everything else → index.html."""
            candidate = os.path.join(_web_dist, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            return FileResponse(_index_html)

        @app.get("/app", include_in_schema=False)
        async def _spa_app_root():  # type: ignore[no-untyped-def]
            return FileResponse(_index_html)

        # Any other unknown path also returns index.html so deep links
        # (e.g. /random/spa) still render the SPA — the real file lookup
        # below also handles /favicon.png, /robots.txt, etc.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa_catch_all(full_path: str):  # type: ignore[no-untyped-def]
            candidate = os.path.join(_web_dist, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            return FileResponse(_index_html)

        app.mount(
            "/assets",
            StaticFiles(directory=os.path.join(_web_dist, "assets")),
            name="spa-assets",
        )

    # Rate-limit handler.
    handler = make_exception_handler()

    @app.exception_handler(RateLimitExceeded)
    async def _ratelimit_handler(request, exc):  # type: ignore[no-untyped-def]
        return await handler(request, exc)

    @app.exception_handler(ValidationError)
    async def _val_handler(request, exc):  # type: ignore[no-untyped-def]
        return await handler(request, exc)

    @app.exception_handler(Exception)
    async def _default_handler(request, exc):  # type: ignore[no-untyped-def]
        return await handler(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_handler(request, exc: StarletteHTTPException):  # type: ignore[no-untyped-def]
        """Starlette HTTP errors (404 etc.) — return JSON, never HTML, never 500."""
        return JSONResponse(
            {
                "error": "not_found" if exc.status_code == 404 else "http_error",
                "code": "not_found" if exc.status_code == 404 else "http_error",
                "status": exc.status_code,
                "friendly": "That endpoint doesn't exist. Try GET / for the route catalog.",
            },
            status_code=exc.status_code,
        )

    return app


app = create_app()
