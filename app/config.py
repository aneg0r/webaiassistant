"""Application settings and paths."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BACKOFFICE_DIR = Path(
    os.environ.get("BACKOFFICE_DIR", str(PROJECT_ROOT / "backoffice"))
).resolve()
VAR_DIR = Path(os.environ.get("VAR_DIR", str(PROJECT_ROOT / "var"))).resolve()

SCENARII_DIR = BACKOFFICE_DIR / "scenarii"
SESSIONS_DIR = VAR_DIR / "sessions"
RECORDS_DIR = VAR_DIR / "records"
CHAT_ACTIONS_DIR = RECORDS_DIR / "actions"
CHAT_FEEDBACK_DIR = RECORDS_DIR / "feedback"
CHAT_SURVEYS_DIR = RECORDS_DIR / "surveys"
CHAT_FEEDBACK_AGENT_DIR = RECORDS_DIR / "feedback_agent"
CHAT_ISSUE_REPORTS_DIR = RECORDS_DIR / "issue_reports"
CHAT_SESSION_INDEX_PATH = VAR_DIR / "index" / "chat_session_index.json"
STATIC_DIR = PROJECT_ROOT / "static"

DEFAULT_PERIMETER_PATH = BACKOFFICE_DIR / "perimeter.json"

# Legacy paths (pre backoffice/var split); one-release read fallback only.
_LEGACY_CHAT_DIR = PROJECT_ROOT / "chat"
_LEGACY_DATA_DIR = PROJECT_ROOT / "data"
_LEGACY_SESSION_INDEX = _LEGACY_DATA_DIR / "chat_session_index.json"
_LEGACY_SESSIONS_DIR = _LEGACY_CHAT_DIR / "session"
_LEGACY_RECORDS = {
    "actions": _LEGACY_CHAT_DIR / "actions",
    "feedback": _LEGACY_CHAT_DIR / "feedback",
    "surveys": _LEGACY_CHAT_DIR / "surveys",
    "feedback_agent": _LEGACY_CHAT_DIR / "feedback_agent",
    "issue_reports": _LEGACY_CHAT_DIR / "issue_reports",
}

# Backward-compatible aliases for tests.
CHAT_DIR = BACKOFFICE_DIR
CHAT_SCENARII_DIR = SCENARII_DIR
CHAT_SESSION_DIR = SESSIONS_DIR
DATA_DIR = VAR_DIR / "index"

# Maps perimeter feature flag -> scenarii filename (without always-on files).
FEATURE_SCENARII_FILES: dict[str, str] = {
    "knowledge_search": "knowledge_search.md",
    "troubleshooting": "technical_support.md",
    "customer_service_returns": "customer_service_returns.md",
    "customer_service_order_handling": "customer_service_order_handling.md",
    "callback_request": "callback_request.md",
    "issue_reporting": "issue_reporting.md",
    "newsletter": "newsletter.md",
    "survey": "survey.md",
    "feedback_page": "feedback_page.md",
    "feedback_agent": "feedback_agent.md",
    "human_escalation": "human_escalation.md",
}

ALWAYS_SCENARII_FILES = ("00_intent_rules.md", "off_topic.md")

PRODUCT_NAME = os.environ.get("PRODUCT_NAME", "Our product")
OFF_TOPIC_REPLY = os.environ.get(
    "OFF_TOPIC_REPLY",
    "I can only answer questions about our product.",
)
WELCOME_MESSAGE = os.environ.get(
    "WELCOME_MESSAGE",
    "Hello. How can I help you?",
)

LLM_MODEL = os.environ.get("LLM_MODEL", os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash"))
LLM_MODEL_BACKUP = os.environ.get("LLM_MODEL_BACKUP", "")

INJECT_WIKI_IN_PROMPT = os.environ.get("INJECT_WIKI_IN_PROMPT", "false").lower() in (
    "1",
    "true",
    "yes",
)
WIKI_MAX_CHARS = int(os.environ.get("WIKI_MAX_CHARS", "4000"))

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "").split(",")
    if o.strip()
]

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()

CHAT_CLOSED_SESSION_PROMPT = "Closed session"
CHAT_PRESENCE_ONLINE_WINDOW_SECONDS = 20.0
CHAT_PRESENCE_TTL_SECONDS = 600.0
MAX_HISTORY_MESSAGES = 20


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in ("1", "true", "yes")


def _resolve_read_path(primary: Path, legacy: Path) -> Path:
    if primary.is_file() or primary.is_dir():
        return primary
    if legacy.is_file() or legacy.is_dir():
        return legacy
    return primary


@lru_cache(maxsize=1)
def load_perimeter() -> dict[str, Any]:
    """Load backoffice/perimeter.json with optional FEATURE_* env overrides."""
    path = Path(os.environ.get("PERIMETER_FILE", str(DEFAULT_PERIMETER_PATH)))
    if not path.is_file():
        path = _resolve_read_path(path, _LEGACY_CHAT_DIR / "perimeter.json")
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    features = data.get("features")
    if not isinstance(features, dict):
        features = {}
        data["features"] = features
    for key in FEATURE_SCENARII_FILES:
        env_val = _env_bool(f"FEATURE_{key.upper()}")
        if env_val is not None:
            features[key] = env_val
    if not data.get("product_type"):
        data["product_type"] = "physical"
    return data


def feature_enabled(name: str) -> bool:
    features = load_perimeter().get("features") or {}
    return bool(features.get(name, False))


def session_index_read_path() -> Path:
    if CHAT_SESSION_INDEX_PATH.is_file():
        return CHAT_SESSION_INDEX_PATH
    if _LEGACY_SESSION_INDEX.is_file():
        return _LEGACY_SESSION_INDEX
    return CHAT_SESSION_INDEX_PATH


def sessions_read_dir() -> Path:
    if SESSIONS_DIR.is_dir() and any(SESSIONS_DIR.glob("*.json")):
        return SESSIONS_DIR
    if _LEGACY_SESSIONS_DIR.is_dir():
        return _LEGACY_SESSIONS_DIR
    return SESSIONS_DIR


def records_read_dir(source: str) -> Path:
    primary = {
        "actions": CHAT_ACTIONS_DIR,
        "feedback": CHAT_FEEDBACK_DIR,
        "surveys": CHAT_SURVEYS_DIR,
        "feedback_agent": CHAT_FEEDBACK_AGENT_DIR,
    }.get(source)
    if primary is None:
        raise ValueError(f"unknown source: {source}")
    legacy = _LEGACY_RECORDS.get(source)
    if primary.is_dir() and any(primary.glob("*.json")):
        return primary
    if legacy and legacy.is_dir():
        return legacy
    return primary
