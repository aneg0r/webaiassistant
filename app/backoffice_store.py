"""Read/write backoffice configuration files (FAQ, scenarii)."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from app import config
from app.content import invalidate_faq_cache, invalidate_scenarii_cache, invalidate_wiki_cache

_FAQ_PATH = config.BACKOFFICE_DIR / "faq.json"
_FAQ_EXAMPLE_PATH = config.PROJECT_ROOT / "backoffice" / "faq.json.example"
_WIKI_PATH = config.BACKOFFICE_DIR / "wiki.md"
_WIKI_EXAMPLE_PATH = config.PROJECT_ROOT / "backoffice" / "wiki.md.example"
_SCENARII_DIR = config.SCENARII_DIR
_SCENARII_EXAMPLE_DIR = config.PROJECT_ROOT / "backoffice" / "scenarii.example"

_SCENARIO_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+\.md$")


def _ensure_backoffice_dirs() -> None:
    config.BACKOFFICE_DIR.mkdir(parents=True, exist_ok=True)
    _SCENARII_DIR.mkdir(parents=True, exist_ok=True)


def _copy_backoffice_file_from_example(runtime: Path, example: Path) -> None:
    if runtime.is_file() or not example.is_file():
        return
    shutil.copy2(example, runtime)


def ensure_faq_from_example() -> None:
    """Copy bundled FAQ template if runtime file is missing."""
    _ensure_backoffice_dirs()
    _copy_backoffice_file_from_example(_FAQ_PATH, _FAQ_EXAMPLE_PATH)


def ensure_wiki_from_example() -> None:
    """Copy bundled wiki template if runtime file is missing."""
    _ensure_backoffice_dirs()
    _copy_backoffice_file_from_example(_WIKI_PATH, _WIKI_EXAMPLE_PATH)


def ensure_scenarii_from_example() -> None:
    """Copy all bundled scenario templates on first install only."""
    if _SCENARII_DIR.is_dir():
        return
    if not _SCENARII_EXAMPLE_DIR.is_dir():
        return
    _SCENARII_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(_SCENARII_EXAMPLE_DIR.glob("*.md")):
        shutil.copy2(src, _SCENARII_DIR / src.name)


def validate_faq_payload(data: Any) -> list[dict[str, str]]:
    if not isinstance(data, list):
        raise ValueError("FAQ must be a JSON array")
    out: list[dict[str, str]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"FAQ entry {i + 1} must be an object")
        q = item.get("question")
        a = item.get("answer")
        if not isinstance(q, str) or not isinstance(a, str):
            raise ValueError(f"FAQ entry {i + 1} needs string question and answer")
        out.append({"question": q.strip(), "answer": a.strip()})
    return out


def read_faq() -> list[dict[str, str]]:
    _ensure_backoffice_dirs()
    if not _FAQ_PATH.is_file():
        return []
    try:
        raw = json.loads(_FAQ_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError("FAQ file unreadable or invalid JSON") from e
    return validate_faq_payload(raw)


def read_wiki() -> str:
    _ensure_backoffice_dirs()
    if not _WIKI_PATH.is_file():
        return ""
    try:
        return _WIKI_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError("wiki file unreadable") from e


def write_wiki(content: str) -> str:
    if content is None:
        raise ValueError("content required")
    text = str(content)
    _ensure_backoffice_dirs()
    _WIKI_PATH.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    invalidate_wiki_cache()
    return _WIKI_PATH.read_text(encoding="utf-8")


def write_faq(data: Any) -> list[dict[str, str]]:
    entries = validate_faq_payload(data)
    _ensure_backoffice_dirs()
    _FAQ_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    invalidate_faq_cache()
    return entries


def _safe_scenario_filename(name: str) -> str:
    raw = (name or "").strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("invalid scenario file name")
    base = os.path.basename(raw)
    if not _SCENARIO_NAME_RE.match(base):
        raise ValueError("scenario file must match [a-zA-Z0-9._-]+.md")
    return base


def list_scenario_files() -> list[str]:
    _ensure_backoffice_dirs()
    if not _SCENARII_DIR.is_dir():
        return []
    names = [p.name for p in _SCENARII_DIR.glob("*.md") if p.is_file()]
    return sorted(names, key=str.lower)


def list_scenario_example_files() -> list[str]:
    if not _SCENARII_EXAMPLE_DIR.is_dir():
        return []
    names = [p.name for p in _SCENARII_EXAMPLE_DIR.glob("*.md") if p.is_file()]
    return sorted(names, key=str.lower)


def read_scenario_example_file(name: str) -> dict[str, str]:
    fname = _safe_scenario_filename(name)
    path = _SCENARII_EXAMPLE_DIR / fname
    if not path.is_file():
        raise LookupError("example scenario file not found")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError("example scenario file unreadable") from e
    return {"file": fname, "content": content}


def copy_scenario_from_example(name: str, *, overwrite: bool = False) -> dict[str, str]:
    fname = _safe_scenario_filename(name)
    src = _SCENARII_EXAMPLE_DIR / fname
    if not src.is_file():
        raise LookupError("example scenario file not found")
    _ensure_backoffice_dirs()
    dest = _SCENARII_DIR / fname
    if dest.is_file() and not overwrite:
        raise FileExistsError("scenario file already exists")
    shutil.copy2(src, dest)
    invalidate_scenarii_cache()
    return read_scenario_file(fname)


def read_scenario_file(name: str) -> dict[str, str]:
    fname = _safe_scenario_filename(name)
    path = _SCENARII_DIR / fname
    if not path.is_file():
        raise LookupError("scenario file not found")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError("scenario file unreadable") from e
    return {"file": fname, "content": content}


def write_scenario_file(name: str, content: str) -> dict[str, str]:
    fname = _safe_scenario_filename(name)
    if content is None:
        raise ValueError("content required")
    text = str(content)
    if not text.strip():
        raise ValueError("scenario content cannot be empty")
    _ensure_backoffice_dirs()
    path = _SCENARII_DIR / fname
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    invalidate_scenarii_cache()
    return {"file": fname, "content": path.read_text(encoding="utf-8")}
