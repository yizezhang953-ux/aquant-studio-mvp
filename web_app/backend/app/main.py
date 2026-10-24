from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.database_service import create_database, initialize_database, is_seeded

MAX_REQUEST_BYTES_SLACK = 1024 * 1024


class BodySizeLimitMiddleware:
    """Reject request bodies above MAX_UPLOAD_BYTES (+1 MB for JSON/multipart overhead), including
    chunked uploads without Content-Length, before they are parsed or spooled to disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = settings.max_upload_bytes + MAX_REQUEST_BYTES_SLACK
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length", b"").decode() or ""
        if length.isdigit() and int(length) > limit:
            await JSONResponse(status_code=413, content={"detail": "request body too large"})(scope, receive, send)
            return
        received = 0
        rejected = False

        async def reject() -> None:
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"request body too large"}'})

        async def limited_receive():
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    await reject()
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not rejected:  # the 413 has already been sent; drop the app's own response
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not rejected:
                raise




@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup:
        create_database()
    if settings.seed_on_startup:
        with SessionLocal() as db:
            if not is_seeded(db):
                initialize_database(db, seed=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Online backend API for AQuant Studio.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BodySizeLimitMiddleware)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "status": "online",
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
