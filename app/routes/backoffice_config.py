"""Admin API to edit backoffice/faq.json and backoffice/scenarii/*.md."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import backoffice_store
from app.auth import require_admin

router = APIRouter(prefix="/backoffice", tags=["backoffice-config"])


def _admin_dep(request: Request) -> None:
    require_admin(request)


class FaqPutBody(BaseModel):
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Array of {question, answer}",
    )


class ScenarioPutBody(BaseModel):
    content: str = Field(..., min_length=1)


@router.get("/faq", dependencies=[Depends(_admin_dep)])
async def get_faq() -> JSONResponse:
    try:
        entries = backoffice_store.read_faq()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse({"entries": entries})


@router.put("/faq", dependencies=[Depends(_admin_dep)])
async def put_faq(body: FaqPutBody) -> JSONResponse:
    try:
        entries = backoffice_store.write_faq(body.entries)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return JSONResponse({"ok": True, "entries": entries})


@router.get("/scenarii/list", dependencies=[Depends(_admin_dep)])
async def list_scenarii() -> JSONResponse:
    return JSONResponse({"files": backoffice_store.list_scenario_files()})


@router.get("/scenarii/file", dependencies=[Depends(_admin_dep)])
async def get_scenario(file: str) -> JSONResponse:
    try:
        out = backoffice_store.read_scenario_file(file)
        return JSONResponse(out)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/scenarii/file", dependencies=[Depends(_admin_dep)])
async def put_scenario(file: str, body: ScenarioPutBody) -> JSONResponse:
    try:
        out = backoffice_store.write_scenario_file(file, body.content)
        return JSONResponse({"ok": True, **out})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
