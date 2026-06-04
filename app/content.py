"""Load FAQ, wiki, and perimeter-filtered scenarii."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app import config

_faq_cache: Optional[str] = None
_faq_mtime: Optional[float] = None
_scenarii_cache: Optional[str] = None
_scenarii_mtime_key: Optional[tuple] = None
_wiki_cache: Optional[str] = None


def invalidate_faq_cache() -> None:
    global _faq_cache, _faq_mtime
    _faq_cache = None
    _faq_mtime = None


def invalidate_scenarii_cache() -> None:
    global _scenarii_cache, _scenarii_mtime_key
    _scenarii_cache = None
    _scenarii_mtime_key = None


def load_faq_block() -> str:
    global _faq_cache, _faq_mtime
    path = config._resolve_read_path(
        config.BACKOFFICE_DIR / "faq.json",
        config._LEGACY_CHAT_DIR / "faq.json",
    )
    try:
        mtime = path.stat().st_mtime if path.is_file() else None
    except OSError:
        mtime = None
    if _faq_cache is not None and mtime == _faq_mtime:
        return _faq_cache
    if not path.is_file():
        _faq_cache = "(no FAQ entries)"
        _faq_mtime = mtime
        return _faq_cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _faq_cache = "(FAQ unreadable)"
        _faq_mtime = mtime
        return _faq_cache
    if not isinstance(data, list):
        _faq_cache = "(invalid FAQ)"
        _faq_mtime = mtime
        return _faq_cache
    lines: list[str] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        lines.append(f"{i}. Q: {q}\n   A: {a}")
    _faq_cache = "\n".join(lines) if lines else "(empty FAQ)"
    _faq_mtime = mtime
    return _faq_cache


def _scenarii_files_to_load() -> list[Path]:
    files: list[Path] = []
    scen_dir = config._resolve_read_path(
        config.SCENARII_DIR,
        config._LEGACY_CHAT_DIR / "scenarii",
    )
    for name in config.ALWAYS_SCENARII_FILES:
        p = scen_dir / name
        if p.is_file():
            files.append(p)
    features = config.load_perimeter().get("features") or {}
    for feature, filename in config.FEATURE_SCENARII_FILES.items():
        if features.get(feature):
            p = scen_dir / filename
            if p.is_file():
                files.append(p)
    return files


def _mtime_key(paths: list[Path]) -> tuple:
    key: list = []
    for p in paths:
        try:
            key.append((str(p), p.stat().st_mtime))
        except OSError:
            key.append((str(p), None))
    key.append(str(config.load_perimeter()))
    return tuple(key)


def load_scenarii_block() -> str:
    global _scenarii_cache, _scenarii_mtime_key
    paths = _scenarii_files_to_load()
    if not paths:
        return "(no scenarii files configured)"
    mk = _mtime_key(paths)
    if _scenarii_cache is not None and mk == _scenarii_mtime_key:
        return _scenarii_cache
    parts: list[str] = []
    for p in paths:
        try:
            parts.append(p.read_text(encoding="utf-8").rstrip())
        except OSError:
            parts.append(f"(unreadable: {p.name})")
    _scenarii_cache = "\n\n---\n\n".join(parts)
    _scenarii_mtime_key = mk
    return _scenarii_cache


def _wiki_enabled() -> bool:
    if config.INJECT_WIKI_IN_PROMPT:
        return True
    features = config.load_perimeter().get("features") or {}
    return bool(features.get("wiki_in_prompt"))


def load_wiki_excerpt() -> Optional[str]:
    global _wiki_cache
    if not _wiki_enabled():
        return None
    path = config._resolve_read_path(
        config.BACKOFFICE_DIR / "wiki.md",
        config._LEGACY_CHAT_DIR / "wiki.md",
    )
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    text = text.strip()
    if len(text) > config.WIKI_MAX_CHARS:
        text = text[: config.WIKI_MAX_CHARS] + "\n…"
    return text
