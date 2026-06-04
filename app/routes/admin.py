"""Admin routes under /backoffice/."""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import config
from app.admin_records import read_record, list_records
from app.auth import require_admin
from app.presence import snapshot as presence_snapshot
from app.schemas import ArchiveSessionBody, HumanInChargeBody, HumanReplyBody
from app.transcripts import (
    append_human_reply_to_transcript,
    list_chat_transcripts_summary,
    read_transcript_file,
    set_human_in_charge_for_transcript,
)

router = APIRouter(prefix="/backoffice", tags=["admin"])


def _admin_dep(request: Request) -> None:
    require_admin(request)


@router.get("/sessions/list", dependencies=[Depends(_admin_dep)])
async def sessions_list() -> JSONResponse:
    now_ts = time.time()
    presence = presence_snapshot()
    sessions = list_chat_transcripts_summary()
    for s in sessions:
        sid = (s.get("sessionId") or "").strip() if isinstance(s, dict) else ""
        last_poll_ts = presence.get(sid) if sid else None
        if last_poll_ts is None:
            s["client_last_poll_at"] = None
            s["client_online"] = False
        else:
            s["client_last_poll_at"] = datetime.fromtimestamp(last_poll_ts).isoformat(
                timespec="seconds"
            )
            s["client_online"] = (
                now_ts - last_poll_ts
            ) < config.CHAT_PRESENCE_ONLINE_WINDOW_SECONDS
    return JSONResponse({"sessions": sessions})


@router.post("/sessions/archive", dependencies=[Depends(_admin_dep)])
async def sessions_archive(body: ArchiveSessionBody) -> JSONResponse:
    file_name = (body.file or "").strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="file required")
    base_name = os.path.basename(file_name)
    if not base_name.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="only .json files allowed")
    src_path = config.SESSIONS_DIR / base_name
    if not src_path.exists() or not src_path.is_file():
        legacy = config._LEGACY_SESSIONS_DIR / base_name
        if legacy.is_file():
            src_path = legacy
        else:
            raise HTTPException(status_code=404, detail="session file not found")
    archived_dir = config.SESSIONS_DIR / "archived"
    archived_dir.mkdir(parents=True, exist_ok=True)
    dest_path = archived_dir / base_name
    if dest_path.exists():
        raise HTTPException(status_code=409, detail="archived file already exists")
    shutil.move(str(src_path), str(dest_path))
    return JSONResponse(
        {
            "ok": True,
            "file": base_name,
            "archived_path": f"var/sessions/archived/{base_name}",
        }
    )


@router.post("/human", dependencies=[Depends(_admin_dep)])
async def human_reply(body: HumanReplyBody) -> JSONResponse:
    try:
        out = append_human_reply_to_transcript(
            body.session_id,
            body.file,
            body.content,
            prenom=body.prenom,
        )
        return JSONResponse(out)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/sessions/file", dependencies=[Depends(_admin_dep)])
async def sessions_file(
    file: str = Query(..., description="Transcript basename"),
) -> JSONResponse:
    try:
        return JSONResponse(read_transcript_file(file))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/records/list", dependencies=[Depends(_admin_dep)])
async def records_list(source: str = Query(..., description="actions|feedback|surveys|feedback_agent")) -> JSONResponse:
    try:
        records = list_records(source.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return JSONResponse({"source": source.strip().lower(), "records": records})


@router.get("/records/file", dependencies=[Depends(_admin_dep)])
async def records_file(
    source: str = Query(...),
    file: str = Query(..., alias="file"),
) -> JSONResponse:
    try:
        out = read_record(source.strip().lower(), file)
        return JSONResponse(out)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/human-in-charge", dependencies=[Depends(_admin_dep)])
async def human_in_charge(body: HumanInChargeBody) -> JSONResponse:
    try:
        out = set_human_in_charge_for_transcript(
            body.session_id,
            body.file,
            active=body.active,
        )
        return JSONResponse(out)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
