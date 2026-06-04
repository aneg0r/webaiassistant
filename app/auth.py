"""Admin authentication — Bearer token and/or HTTP Basic from .env."""

from __future__ import annotations

import base64
import secrets

from fastapi import HTTPException, Request

from app import config


def admin_auth_enabled() -> bool:
    return bool(config.ADMIN_TOKEN or (config.ADMIN_USER and config.ADMIN_PASSWORD))


def admin_dual_auth_required() -> bool:
    """When both token and basic are configured, API calls must provide both."""
    return bool(config.ADMIN_TOKEN and config.ADMIN_USER and config.ADMIN_PASSWORD)


def _check_basic_username_password(username: str, password: str) -> bool:
    user = config.ADMIN_USER
    expected = config.ADMIN_PASSWORD
    if not user or not expected:
        return False
    user_ok = secrets.compare_digest(username.encode(), user.encode())
    pass_ok = secrets.compare_digest(password.encode(), expected.encode())
    return user_ok and pass_ok


def _basic_from_request(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
        username, _, password = decoded.partition(":")
        return _check_basic_username_password(username, password)
    except (ValueError, UnicodeDecodeError):
        return False


def _check_admin_token(request: Request) -> bool:
    """Accept Bearer or X-Admin-Token (latter avoids clobbering nginx Basic on fetch)."""
    expected = config.ADMIN_TOKEN
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
        return secrets.compare_digest(provided.encode(), expected.encode())
    header = (request.headers.get("X-Admin-Token") or "").strip()
    if header:
        return secrets.compare_digest(header.encode(), expected.encode())
    return False


def _unauthorized(request: Request, *, need_basic: bool) -> None:
    if need_basic or (config.ADMIN_USER and config.ADMIN_PASSWORD):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_admin(request: Request, *, for_html: bool = False) -> None:
    """
    Protect admin API and HTML.

    - Nothing configured in .env → open (dev only).
    - Only ADMIN_TOKEN → valid Bearer required.
    - Only ADMIN_USER + ADMIN_PASSWORD → valid Basic required.
    - Both configured → API requires Basic **and** Bearer; HTML accepts either
      (so nginx Basic can load the page; JS adds Bearer for API calls).
    """
    has_token = bool(config.ADMIN_TOKEN)
    has_basic = bool(config.ADMIN_USER and config.ADMIN_PASSWORD)
    if not has_token and not has_basic:
        return

    bearer_ok = _check_admin_token(request) if has_token else True
    basic_ok = _basic_from_request(request) if has_basic else True

    if for_html:
        if (has_token and bearer_ok) or (has_basic and basic_ok):
            return
        _unauthorized(request, need_basic=has_basic)
        return

    if admin_dual_auth_required():
        if bearer_ok and basic_ok:
            return
        detail = "Unauthorized: ADMIN_TOKEN (Bearer) and ADMIN_USER/PASSWORD (Basic) required"
        if has_basic:
            raise HTTPException(
                status_code=401,
                detail=detail,
                headers={"WWW-Authenticate": "Basic"},
            )
        raise HTTPException(status_code=401, detail=detail)

    if (has_token and bearer_ok) or (has_basic and basic_ok):
        return
    _unauthorized(request, need_basic=has_basic)
