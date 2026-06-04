"""Chat session JSON transcripts and index."""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import config

_chat_transcript_lock = threading.Lock()


def _sanitize_chat_filename_part(s: str, max_len: int = 64) -> str:
    s = (s or "").strip() or "x"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:max_len]


def _session_file_path(rel_name: str) -> Path:
    name = os.path.basename((rel_name or "").strip())
    primary = config.SESSIONS_DIR / name
    if primary.is_file():
        return primary
    legacy = config._LEGACY_SESSIONS_DIR / name
    if legacy.is_file():
        return legacy
    return primary


def _load_chat_session_index() -> dict:
    path = config.session_index_read_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_chat_session_index(index: dict) -> None:
    config.CHAT_SESSION_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CHAT_SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=0)


def append_chat_transcript_json(
    client_ip: str,
    session_id: Optional[str],
    user_text: str,
    assistant_reply: str,
    *,
    scenario: Optional[str] = None,
    handoff_signal: Optional[str] = None,
    ticket: Optional[dict] = None,
    feedback: Optional[dict] = None,
    buttons: Optional[list] = None,
) -> None:
    ip = (client_ip or "").strip() or "unknown"
    sid = (session_id or "").strip()
    sid_key = sid if sid else f"no-session__{_sanitize_chat_filename_part(ip)}"
    now = datetime.now(timezone.utc)
    iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    with _chat_transcript_lock:
        config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        index = _load_chat_session_index()
        rel_name = index.get(sid_key)
        path = _session_file_path(rel_name) if rel_name else None

        if path is None or not path.is_file():
            token = "xxxxx" if not sid else secrets.token_hex(4)
            session_part = _sanitize_chat_filename_part(sid if sid else "no-session")
            ip_part = _sanitize_chat_filename_part(ip.replace(":", "-"))
            dt_part = now.strftime("%Y%m%d_%H%M%S")
            fname = f"{token}__{session_part}__{ip_part}__{dt_part}.json"
            path = config.SESSIONS_DIR / fname
            asst0: dict = {
                "role": "assistant",
                "content": assistant_reply,
                "at": iso,
            }
            if scenario is not None:
                asst0["scenario"] = scenario
            if handoff_signal is not None:
                asst0["handoff_signal"] = handoff_signal
            if ticket is not None:
                asst0["ticket"] = ticket
            if feedback is not None:
                asst0["feedback"] = feedback
            if buttons:
                asst0["buttons"] = buttons
            data = {
                "sessionId": sid or None,
                "client_ip": ip,
                "started_at": iso,
                "updated_at": iso,
                "messages": [
                    {"role": "user", "content": user_text, "at": iso},
                    asst0,
                ],
            }
            index[sid_key] = fname
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _save_chat_session_index(index)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {
                "sessionId": sid or None,
                "client_ip": ip,
                "started_at": iso,
                "messages": [],
            }

        data["updated_at"] = iso
        if "messages" not in data or not isinstance(data["messages"], list):
            data["messages"] = []
        data["messages"].append({"role": "user", "content": user_text, "at": iso})
        asst: dict = {"role": "assistant", "content": assistant_reply, "at": iso}
        if scenario is not None:
            asst["scenario"] = scenario
        if handoff_signal is not None:
            asst["handoff_signal"] = handoff_signal
        if ticket is not None:
            asst["ticket"] = ticket
        if feedback is not None:
            asst["feedback"] = feedback
        if buttons:
            asst["buttons"] = buttons
        data["messages"].append(asst)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def append_user_message_to_transcript(
    client_ip: str,
    session_id: Optional[str],
    user_text: str,
) -> None:
    text = (user_text or "").strip()
    if not text:
        raise ValueError("user_text empty")
    ip = (client_ip or "").strip() or "unknown"
    sid = (session_id or "").strip()
    sid_key = sid if sid else f"no-session__{_sanitize_chat_filename_part(ip)}"
    iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    with _chat_transcript_lock:
        index = _load_chat_session_index()
        rel_name = index.get(sid_key)
        if not rel_name:
            raise LookupError("No transcript for this session")
        path = _session_file_path(rel_name)
        if not path.is_file():
            raise LookupError("Transcript file not found")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        if "messages" not in data or not isinstance(data["messages"], list):
            data["messages"] = []
        data["updated_at"] = iso
        data["messages"].append({"role": "user", "content": text, "at": iso})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def update_scenario_state_in_transcript(
    session_id: str, scenario_state: Optional[dict]
) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        rel_name = index.get(sid)
        if not rel_name:
            return
        path = _session_file_path(rel_name)
        if not path.is_file():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        if scenario_state is None:
            data.pop("scenario_state", None)
        else:
            data["scenario_state"] = scenario_state
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def list_chat_transcripts_summary() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sessions_dir = config.sessions_read_dir()
    if not sessions_dir.is_dir():
        return rows
    for path in sessions_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        messages = data.get("messages")
        if not isinstance(messages, list):
            messages = []
        last_message_role: Optional[str] = None
        last_message_author: Optional[str] = None
        last_message_content: Optional[str] = None
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                role = last_msg.get("role")
                if isinstance(role, str):
                    last_message_role = role.strip().lower() or None
                    if last_message_role == "user":
                        last_message_author = "user"
                    elif last_message_role == "assistant":
                        last_message_author = (
                            "human" if bool(last_msg.get("from_human", False)) else "assistant"
                        )
                content = last_msg.get("content")
                if content is not None:
                    last_message_content = str(content)
        human_req = False
        agent_dem = False
        for m in messages:
            if not isinstance(m, dict):
                continue
            hs = m.get("handoff_signal")
            if hs == "human_requires_human":
                human_req = True
            elif hs == "agent_demande_humain":
                agent_dem = True
        rows.append(
            {
                "file": path.name,
                "sessionId": data.get("sessionId"),
                "started_at": data.get("started_at"),
                "updated_at": data.get("updated_at"),
                "client_ip": data.get("client_ip"),
                "human_requires_human": human_req,
                "agent_demande_humain": agent_dem,
                "human_in_charge": bool(data.get("human_in_charge", False)),
                "last_message_role": last_message_role,
                "last_message_author": last_message_author,
                "last_message_content": last_message_content,
            }
        )
    rows.sort(key=lambda r: (r.get("updated_at") or ""), reverse=True)
    return rows


def append_human_reply_to_transcript(
    session_id: Optional[str],
    file: Optional[str],
    content: str,
    prenom: Optional[str] = None,
) -> Dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("content empty")
    iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        sid_key: Optional[str] = None
        fn = (file or "").strip()
        if fn:
            base = os.path.basename(fn)
            if not base.endswith(".json"):
                raise ValueError(".json file expected")
            for k, v in index.items():
                if v == base:
                    sid_key = k
                    break
        else:
            sid = (session_id or "").strip()
            if sid and sid in index:
                sid_key = sid
        if not sid_key:
            raise LookupError("No transcript for session or file")
        rel_name = index.get(sid_key)
        if not rel_name:
            raise LookupError("No transcript for session or file")
        path = _session_file_path(rel_name)
        if not path.is_file():
            raise LookupError("Transcript file not found")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        if "messages" not in data or not isinstance(data["messages"], list):
            data["messages"] = []
        data["updated_at"] = iso
        data["human_in_charge"] = True
        msg: Dict[str, Any] = {
            "role": "assistant",
            "content": text,
            "at": iso,
            "from_human": True,
        }
        pn = (prenom or "").strip()
        if pn:
            msg["prenom"] = pn
        data["messages"].append(msg)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {
            "ok": True,
            "updated_at": iso,
            "message_count": len(data["messages"]),
            "human_in_charge": True,
        }


def set_human_in_charge_for_transcript(
    session_id: Optional[str],
    file: Optional[str],
    *,
    active: bool,
) -> Dict[str, Any]:
    iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        sid_key: Optional[str] = None
        fn = (file or "").strip()
        if fn:
            base = os.path.basename(fn)
            if not base.endswith(".json"):
                raise ValueError(".json file expected")
            for k, v in index.items():
                if v == base:
                    sid_key = k
                    break
        else:
            sid = (session_id or "").strip()
            if sid and sid in index:
                sid_key = sid
        if not sid_key:
            raise LookupError("No transcript for session or file")
        rel_name = index.get(sid_key)
        if not rel_name:
            raise LookupError("No transcript for session or file")
        path = _session_file_path(rel_name)
        if not path.is_file():
            raise LookupError("Transcript file not found")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        data["updated_at"] = iso
        data["human_in_charge"] = bool(active)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "updated_at": iso, "human_in_charge": bool(active)}


def read_transcript_for_session(session_id: str) -> Optional[Dict[str, Any]]:
    sid = (session_id or "").strip()
    if not sid:
        return None
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        rel_name = index.get(sid)
        if not rel_name:
            return None
        path = _session_file_path(rel_name)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return data if isinstance(data, dict) else None


def read_transcript_by_filename(basename: str) -> Optional[Dict[str, Any]]:
    base = os.path.basename((basename or "").strip())
    if not base.endswith(".json"):
        return None
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        rel_name = None
        for _k, v in index.items():
            if v == base:
                rel_name = v
                break
        if not rel_name:
            return None
        path = _session_file_path(rel_name)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return data if isinstance(data, dict) else None


def read_transcript_file(file_name: str) -> Dict[str, Any]:
    raw = (file_name or "").strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("invalid file name")
    base = os.path.basename(raw)
    if not base.lower().endswith(".json"):
        raise ValueError("only .json files allowed")
    path = _session_file_path(base)
    if not path.is_file():
        raise LookupError("session file not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError("invalid json file") from e
    if not isinstance(data, dict):
        raise ValueError("invalid transcript")
    return data


def filename_for_session_id(session_id: str) -> Optional[str]:
    sid = (session_id or "").strip()
    if not sid:
        return None
    with _chat_transcript_lock:
        index = _load_chat_session_index()
        return index.get(sid)
