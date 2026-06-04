"""FastAPI application — embeddable prospects/clients chat."""

from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.auth import require_admin
from app.routes import admin, agent, backoffice_config
from app.schemas import (
    ArchiveSessionBody,
    FeedbackPageBody,
    GeminiPromptBody,
    HumanInChargeBody,
    HumanReplyBody,
)

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

backoffice_dir = config.BACKOFFICE_DIR
if backoffice_dir.is_dir():
    app.mount(
        "/backoffice",
        StaticFiles(directory=str(backoffice_dir)),
        name="backoffice",
    )


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


@app.get("/agent_admin/")
async def agent_admin_page(request: Request):
    require_admin(request, for_html=True)
    return _admin_page("agent_admin.htm")


@app.get("/agent_admin.htm")
async def agent_admin_redirect():
    return RedirectResponse(url="/agent_admin/", status_code=307)


@app.get("/admin/configuration.htm")
async def admin_configuration_page(request: Request):
    require_admin(request, for_html=True)
    return _admin_page("configuration.htm")


@app.get("/backoffice/configuration.htm")
async def backoffice_configuration_redirect():
    return RedirectResponse(url="/admin/configuration.htm", status_code=307)


@app.get("/api/agent/prompt")
async def compat_get_api_agent_prompt(
    sessionId: Optional[str] = Query(None),
    file: Optional[str] = Query(None),
):
    return await agent.get_agent_prompt(sessionId=sessionId, file=file)


@app.post("/api/agent/prompt")
async def compat_post_api_agent_prompt(request: Request, body: GeminiPromptBody):
    return await agent.post_agent_prompt(request, body)


@app.get("/apitm/agent/prompt")
async def compat_get_apitm_agent_prompt(
    sessionId: Optional[str] = Query(None),
    file: Optional[str] = Query(None),
):
    return await agent.get_agent_prompt(sessionId=sessionId, file=file)


@app.post("/apitm/agent/prompt")
async def compat_post_apitm_agent_prompt(request: Request, body: GeminiPromptBody):
    return await agent.post_agent_prompt(request, body)


@app.post("/api/agent/feedback-page")
async def compat_post_api_feedback_page(body: FeedbackPageBody):
    return await agent.post_feedback_page(body)


@app.get("/apitm/chat/sessions/list")
async def compat_sessions_list(request: Request):
    admin.require_admin(request)
    return await admin.sessions_list()


@app.post("/apitm/chat/sessions/archive")
async def compat_sessions_archive(request: Request, body: ArchiveSessionBody):
    admin.require_admin(request)
    return await admin.sessions_archive(body)


@app.post("/api/human")
async def compat_api_human(request: Request, body: HumanReplyBody):
    admin.require_admin(request)
    return await admin.human_reply(body)


@app.post("/api/human-in-charge")
async def compat_api_human_in_charge(request: Request, body: HumanInChargeBody):
    admin.require_admin(request)
    return await admin.human_in_charge(body)


@app.on_event("startup")
async def ensure_dirs():
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
