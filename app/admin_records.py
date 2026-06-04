"""List and read JSON side-effect files for the admin UI."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import config

def _record_dir(source: str) -> Path:
    return config.records_read_dir(source)


def _safe_file_name(file_name: str) -> str:
    raw = (file_name or "").strip()
    if ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("invalid file name")
    base = os.path.basename(raw)
    if not base.lower().endswith(".json"):
        raise ValueError("only .json files allowed")
    return base


def _parse_filename_prefix(file_name: str) -> str:
    stem = file_name[:-5] if file_name.lower().endswith(".json") else file_name
    return stem.split("__")[0] if "__" in stem else stem


def _summarize_record(prefix: str, data: dict[str, Any]) -> str:
    parts: list[str] = []

    if prefix == "feedback":
        ref = data.get("reference")
        if isinstance(ref, dict):
            page = ref.get("page") or ref.get("url") or ref.get("scope")
            if page:
                parts.append(f"ref={page}")
        notation = data.get("notation")
        if notation is not None:
            parts.append(f"note={notation}")
        rem = (data.get("remarques") or "").strip()
        if rem:
            parts.append(rem[:120])
    elif prefix == "feedback_agent":
        rating = (data.get("rating") or "").strip()
        if rating:
            parts.append(f"rating={rating}")
    elif prefix == "survey":
        choice = data.get("choice")
        if choice is not None:
            parts.append(f"choice={choice}")
        sid = data.get("survey_id")
        if sid:
            parts.append(f"survey_id={sid}")
    elif prefix in ("callback", "newsletter", "issue_reporting"):
        for key in ("email", "phone", "question", "description", "category", "page"):
            val = data.get(key)
            if val is not None and str(val).strip():
                parts.append(f"{key}={str(val).strip()[:80]}")
    else:
        for key, val in list(data.items())[:6]:
            if key in ("at", "session_id"):
                continue
            if val is not None and str(val).strip():
                parts.append(f"{key}={str(val).strip()[:60]}")

    return " · ".join(parts) if parts else "—"


def list_records(source: str) -> list[dict[str, Any]]:
    dir_path = _record_dir(source)
    if not dir_path.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    for path in sorted(dir_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        file_name = path.name
        prefix = _parse_filename_prefix(file_name)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        at = mtime
        session_id: Optional[str] = None
        summary = "—"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                at_val = raw.get("at")
                if isinstance(at_val, str) and at_val.strip():
                    at = at_val.strip()
                sid = raw.get("session_id")
                if sid is not None and str(sid).strip():
                    session_id = str(sid).strip()
                summary = _summarize_record(prefix, raw)
        except (OSError, json.JSONDecodeError):
            summary = "(fichier illisible)"

        rows.append(
            {
                "file": file_name,
                "prefix": prefix,
                "at": at,
                "session_id": session_id,
                "updated_at": mtime,
                "summary": summary,
            }
        )
    return rows


def read_record(source: str, file_name: str) -> dict[str, Any]:
    dir_path = _record_dir(source)
    safe = _safe_file_name(file_name)
    path = dir_path / safe
    if not path.exists() or not path.is_file():
        raise LookupError("record file not found")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError("invalid json file") from e
    if not isinstance(raw, dict):
        raw = {"data": raw}
    return {
        "source": source,
        "file": safe,
        "prefix": _parse_filename_prefix(safe),
        "data": raw,
    }
