"""FastAPI application — embeddable prospects/clients chat."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.auth import require_admin
from app import backoffice_store
from app.routes import admin, agent, backoffice_config

PROJECT_ROOT = config.PROJECT_ROOT

app = FastAPI(title="Embeddable Chat", version="1.0.0")

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(agent.router)
app.include_router(admin.router)
app.include_router(backoffice_config.router)

static_dir = config.STATIC_DIR
admin_static_dir = static_dir / "admin"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    index = static_dir / "index.htm"
    if index.is_file():
        return FileResponse(index)
    return RedirectResponse(url="/chat.htm")


@app.get("/chat.htm")
async def chat_page():
    path = static_dir / "chat.htm"
    if path.is_file():
        return FileResponse(path)
    raise FileNotFoundError("static/chat.htm missing")


@app.get("/example.htm")
async def example_page():
    path = static_dir / "example.htm"
    if path.is_file():
        return FileResponse(path)
    raise FileNotFoundError("static/example.htm missing")


def _admin_page(name: str) -> FileResponse:
    path = admin_static_dir / name
    if path.is_file():
        return FileResponse(path)
    raise FileNotFoundError(f"static/admin/{name} missing")


@app.get("/backoffice/")
async def backoffice_admin_page(request: Request):
    require_admin(request, for_html=True)
    return _admin_page("agent_admin.htm")


@app.get("/backoffice/configuration.htm")
async def backoffice_configuration_page(request: Request):
    require_admin(request, for_html=True)
    return _admin_page("configuration.htm")


@app.get("/admin/configuration.htm")
async def admin_configuration_legacy_redirect():
    return RedirectResponse(url="/backoffice/configuration.htm", status_code=307)


@app.get("/agent_admin/")
async def agent_admin_legacy_redirect():
    return RedirectResponse(url="/backoffice/", status_code=307)


@app.get("/agent_admin.htm")
async def agent_admin_htm_redirect():
    return RedirectResponse(url="/backoffice/", status_code=307)


backoffice_dir = config.BACKOFFICE_DIR
if backoffice_dir.is_dir():
    app.mount(
        "/backoffice",
        StaticFiles(directory=str(backoffice_dir)),
        name="backoffice",
    )


@app.on_event("startup")
async def ensure_dirs():
    backoffice_store.ensure_scenarii_from_example()
    for d in (
        config.SESSIONS_DIR,
        config.SESSIONS_DIR / "archived",
        config.CHAT_FEEDBACK_DIR,
        config.CHAT_ACTIONS_DIR,
        config.CHAT_SURVEYS_DIR,
        config.CHAT_ISSUE_REPORTS_DIR,
        config.CHAT_FEEDBACK_AGENT_DIR,
        config.CHAT_SESSION_INDEX_PATH.parent,
        config.SCENARII_DIR,
        config.BACKOFFICE_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
    if not config.CHAT_SESSION_INDEX_PATH.is_file():
        config.CHAT_SESSION_INDEX_PATH.write_text("{}", encoding="utf-8")
    backoffice_store.ensure_faq_from_example()
    backoffice_store.ensure_wiki_from_example()
