"""Persist scenario side-effects (callback, newsletter, survey)."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import config

_lock = threading.Lock()


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _session_slug(session_id: Optional[str]) -> str:
    sid = (session_id or "").strip()
    if not sid:
        return "nosession"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", sid[:32])


def _write_json(dir_path: Path, prefix: str, payload: dict[str, Any], session_id: Optional[str]) -> str:
    iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {**payload, "at": iso, "session_id": (session_id or "").strip() or None}
    fname = f"{prefix}__{_timestamp_slug()}__{_session_slug(session_id)}.json"
    with _lock:
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / fname
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fname


def save_callback_action(payload: dict[str, Any], session_id: Optional[str] = None) -> str:
    if not config.feature_enabled("callback_request"):
        return ""
    return _write_json(config.CHAT_ACTIONS_DIR, "callback", payload, session_id)


def save_newsletter_action(payload: dict[str, Any], session_id: Optional[str] = None) -> str:
    if not config.feature_enabled("newsletter"):
        return ""
    return _write_json(config.CHAT_ACTIONS_DIR, "newsletter", payload, session_id)


def save_issue_reporting_action(payload: dict[str, Any], session_id: Optional[str] = None) -> str:
    if not config.feature_enabled("issue_reporting"):
        return ""
    description = (payload.get("description") or "").strip()
    if not description:
        return ""
    category = (payload.get("category") or "").strip().lower() or None
    if category not in ("bug", "content", "accessibility", "other"):
        category = "other" if category else None
    page = (payload.get("page") or "").strip() or None
    return _write_json(
        config.CHAT_ISSUE_REPORTS_DIR,
        "issue_reporting",
        {"description": description, "category": category, "page": page},
        session_id,
    )


def save_survey_action(payload: dict[str, Any], session_id: Optional[str] = None) -> str:
    if not config.feature_enabled("survey"):
        return ""
    return _write_json(config.CHAT_SURVEYS_DIR, "survey", payload, session_id)


def save_feedback_agent_action(payload: dict[str, Any], session_id: Optional[str] = None) -> str:
    if not config.feature_enabled("feedback_agent"):
        return ""
    rating = (payload.get("rating") or "").strip().lower()
    if rating not in ("bad", "neutral", "good", "no_answer"):
        rating = "no_answer"
    return _write_json(
        config.CHAT_FEEDBACK_AGENT_DIR,
        "feedback_agent",
        {"rating": rating},
        session_id,
    )


def save_item_feedback(
    reference: dict[str, Any],
    ancien_texte: str,
    nouveau_texte: str,
    notation: int,
    remarques: str,
    session_id: Optional[str] = None,
) -> str:
    """Save page or item feedback under var/records/feedback/."""
    if not config.feature_enabled("feedback_page"):
        return ""
    notation = max(1, min(5, int(notation)))
    payload: dict[str, Any] = {
        "reference": reference,
        "ancien_texte": (ancien_texte or "").strip(),
        "nouveau_texte": (nouveau_texte or "").strip(),
        "notation": notation,
        "remarques": (remarques or "").strip(),
        "session_id": (session_id or "").strip() or None,
    }
    return _write_json(config.CHAT_FEEDBACK_DIR, "feedback", payload, session_id)
