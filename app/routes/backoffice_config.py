"""Admin API to edit backoffice/faq.json, wiki.md, and backoffice/scenarii/*.md."""

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


class WikiPutBody(BaseModel):
    content: str = ""


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


@router.get("/wiki", dependencies=[Depends(_admin_dep)])
async def get_wiki() -> JSONResponse:
    try:
        content = backoffice_store.read_wiki()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse({"content": content})


@router.put("/wiki", dependencies=[Depends(_admin_dep)])
async def put_wiki(body: WikiPutBody) -> JSONResponse:
    try:
        content = backoffice_store.write_wiki(body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return JSONResponse({"ok": True, "content": content})


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


@router.get("/scenarii/examples/list", dependencies=[Depends(_admin_dep)])
async def list_scenario_examples() -> JSONResponse:
    return JSONResponse({"files": backoffice_store.list_scenario_example_files()})


@router.get("/scenarii/examples/file", dependencies=[Depends(_admin_dep)])
async def get_scenario_example(file: str) -> JSONResponse:
    try:
        out = backoffice_store.read_scenario_example_file(file)
        return JSONResponse(out)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/scenarii/examples/copy", dependencies=[Depends(_admin_dep)])
async def copy_scenario_example(file: str, overwrite: bool = False) -> JSONResponse:
    try:
        out = backoffice_store.copy_scenario_from_example(file, overwrite=overwrite)
        return JSONResponse({"ok": True, **out})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
