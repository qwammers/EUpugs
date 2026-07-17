from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import admin, auth, public, queue
from app.core.config import get_settings
from app.db.session import init_db

settings = get_settings()

app = FastAPI(title="HostedPugs API", version="0.1.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    # GitHub Pages and the API are different sites in production, so authenticated
    # fetch requests require a Secure, SameSite=None session cookie.
    same_site="none" if settings.frontend_origin.startswith("https://") else "lax",
    https_only=settings.frontend_origin.startswith("https://"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    if settings.enable_auto_migrate:
        init_db()


app.include_router(auth.router)
app.include_router(auth.api_router)
app.include_router(public.router)
app.include_router(queue.router)
app.include_router(admin.router)
