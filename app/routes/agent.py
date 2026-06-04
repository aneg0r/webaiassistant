"""Client chat routes: POST/GET /agent/prompt."""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import actions, config
from app.agent import agent_chat_turn
from app.presence import touch
from app.schemas import FeedbackPageBody, GeminiPromptBody
from app.side_effects import persist_turn_side_effects
from app.transcripts import (
    append_chat_transcript_json,
    append_user_message_to_transcript,
    filename_for_session_id,
    read_transcript_by_filename,
    read_transcript_for_session,
)

router = APIRouter(tags=["agent"])


@router.post("/agent/feedback-page")
async def post_feedback_page(body: FeedbackPageBody) -> JSONResponse:
    """Persist feedback from the embeddable feedback_page widget."""
    if not config.feature_enabled("feedback_page"):
        raise HTTPException(status_code=403, detail="feedback_page feature disabled")

    scope = (body.scope or "").strip().lower()
    if scope == "global":
        scope = "site"
    if scope not in ("product", "site", "page"):
        raise HTTPException(
            status_code=400,
            detail="scope must be product, site, or page",
        )

    page_ref = (body.page or "").strip()
    if scope == "page" and not page_ref:
        raise HTTPException(status_code=400, detail="page required when scope is page")

    reference: dict[str, str] = {
        "scope": scope,
        "page": page_ref if scope == "page" else "/",
    }

    sid = (body.session_id or "").strip() or None
    fname = actions.save_item_feedback(
        reference=reference,
        ancien_texte="",
        nouveau_texte="",
        notation=body.notation,
        remarques=(body.remarques or "").strip(),
        session_id=sid,
    )
    if not fname:
        raise HTTPException(status_code=500, detail="could not save feedback")

    return JSONResponse(
        {
            "ok": True,
            "scenario": "feedback_page",
            "file": fname,
            "feedback": {
                "reference": reference,
                "notation": body.notation,
                "remarques": (body.remarques or "").strip(),
            },
        }
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


@router.post("/agent/prompt")
async def post_agent_prompt(request: Request, body: GeminiPromptBody) -> JSONResponse:
    sid = (body.session_id or "").strip()
    prompt_stripped = (body.prompt or "").strip()
    if not prompt_stripped:
        raise HTTPException(status_code=400, detail="empty prompt")

    if sid:
        transcript = read_transcript_for_session(sid)
        if isinstance(transcript, dict) and bool(transcript.get("human_in_charge", False)):
            try:
                append_user_message_to_transcript(_client_ip(request), body.session_id, body.prompt)
            except Exception:
                traceback.print_exc()
            return JSONResponse({"reply": "", "human_in_charge": True})

    if prompt_stripped == config.CHAT_CLOSED_SESSION_PROMPT:
        if sid:
            try:
                append_user_message_to_transcript(
                    _client_ip(request), body.session_id, prompt_stripped
                )
            except LookupError:
                pass
            except Exception:
                traceback.print_exc()
        return JSONResponse(
            {"reply": "", "human_in_charge": False, "closed_session": True}
        )

    history = None
    if body.messages:
        history = []
        for m in body.messages:
            turn: dict[str, Any] = {
                "role": m.role.strip().lower(),
                "content": m.content or "",
            }
            if m.from_human:
                turn["from_human"] = True
            if m.prenom:
                turn["prenom"] = m.prenom.strip()
            history.append(turn)

    try:
        result = agent_chat_turn(
            body.prompt,
            history=history,
            session_id=body.session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        detail = str(e)
        if "API_KEY" in detail or "not set" in detail.lower():
            raise HTTPException(status_code=503, detail=detail) from e
        if "empty" in detail.lower():
            raise HTTPException(status_code=502, detail=detail) from e
        raise HTTPException(status_code=500, detail=detail) from e

    reply = result.reply
    try:
        append_chat_transcript_json(
            _client_ip(request),
            body.session_id,
            body.prompt,
            reply,
            scenario=result.scenario,
            handoff_signal=result.handoff_signal,
            ticket=result.ticket,
            feedback=result.feedback,
            buttons=result.buttons,
        )
        persist_turn_side_effects(result, sid or None)
    except Exception:
        traceback.print_exc()

    out: dict[str, Any] = {"reply": reply, "human_in_charge": False}
    if result.scenario is not None:
        out["scenario"] = result.scenario
    if result.handoff_signal is not None:
        out["handoff_signal"] = result.handoff_signal
    if result.ticket is not None:
        out["ticket"] = result.ticket
    if result.buttons:
        out["buttons"] = result.buttons
    return JSONResponse(out)


@router.get("/agent/prompt")
async def get_agent_prompt(
    sessionId: Optional[str] = Query(None),
    file: Optional[str] = Query(None),
) -> JSONResponse:
    fn = (file or "").strip()
    sid = (sessionId or "").strip()

    if fn:
        base = os.path.basename(fn)
        data = read_transcript_by_filename(base)
        if not data:
            return JSONResponse(
                {
                    "sessionId": None,
                    "file": base,
                    "updated_at": None,
                    "human_in_charge": False,
                    "messages": [],
                }
            )
        messages = data.get("messages")
        if not isinstance(messages, list):
            messages = []
        return JSONResponse(
            {
                "sessionId": data.get("sessionId"),
                "file": base,
                "updated_at": data.get("updated_at"),
                "human_in_charge": bool(data.get("human_in_charge", False)),
                "messages": messages,
            }
        )

    if not sid:
        return JSONResponse(
            {"sessionId": None, "file": None, "updated_at": None, "messages": []}
        )

    touch(sid)
    data = read_transcript_for_session(sid)
    if not data:
        return JSONResponse(
            {
                "sessionId": sid,
                "file": filename_for_session_id(sid),
                "updated_at": None,
                "human_in_charge": False,
                "messages": [],
            }
        )
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    return JSONResponse(
        {
            "sessionId": sid,
            "file": filename_for_session_id(sid),
            "updated_at": data.get("updated_at"),
            "human_in_charge": bool(data.get("human_in_charge", False)),
            "messages": messages,
        }
    )
