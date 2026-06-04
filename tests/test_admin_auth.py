"""Tests for admin authentication (Bearer + Basic)."""

from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import config
from app.auth import admin_dual_auth_required, require_admin


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }
    return Request(scope)


def _basic_header(user: str, password: str) -> tuple[bytes, bytes]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return (b"authorization", f"Basic {token}".encode())


def _bearer_header(token: str) -> tuple[bytes, bytes]:
    return (b"authorization", f"Bearer {token}".encode())


def _x_admin_token_header(token: str) -> tuple[bytes, bytes]:
    return (b"x-admin-token", token.encode())


def test_open_when_no_credentials_configured(monkeypatch) -> None:
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_USER", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    require_admin(_request())


def test_bearer_only(monkeypatch) -> None:
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret-token")
    monkeypatch.setattr(config, "ADMIN_USER", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    require_admin(_request([_bearer_header("secret-token")]))
    with pytest.raises(HTTPException) as exc:
        require_admin(_request())
    assert exc.value.status_code == 401


def test_basic_only(monkeypatch) -> None:
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_USER", "admin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "pass")
    require_admin(_request([_basic_header("admin", "pass")]))
    with pytest.raises(HTTPException) as exc:
        require_admin(_request([_bearer_header("wrong")]))
    assert exc.value.status_code == 401


def test_dual_required_on_api(monkeypatch) -> None:
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok")
    monkeypatch.setattr(config, "ADMIN_USER", "admin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "pass")
    assert admin_dual_auth_required() is True
    with pytest.raises(HTTPException):
        require_admin(_request([_basic_header("admin", "pass")]))
    with pytest.raises(HTTPException):
        require_admin(_request([_bearer_header("tok")]))
    require_admin(
        _request([_basic_header("admin", "pass"), _x_admin_token_header("tok")])
    )


def test_html_accepts_basic_only_when_dual_configured(monkeypatch) -> None:
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok")
    monkeypatch.setattr(config, "ADMIN_USER", "admin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "pass")
    require_admin(_request([_basic_header("admin", "pass")]), for_html=True)
    require_admin(_request([_bearer_header("tok")]), for_html=True)
