"""API for embeddable feedback_page widget."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def feedback_dir(tmp_path, monkeypatch):
    d = tmp_path / "feedback"
    d.mkdir()
    monkeypatch.setattr(config, "CHAT_FEEDBACK_DIR", d)
    return d


@pytest.fixture
def perimeter(monkeypatch):
    def _apply(data: dict):
        monkeypatch.setattr(config, "load_perimeter", lambda: data)

    yield _apply


def test_feedback_page_api_saves_product(perimeter, feedback_dir, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={
            "scope": "product",
            "notation": 5,
            "remarques": "Great product",
            "sessionId": "fb-test-1",
        },
    )
    assert r.status_code == 200
    saved = json.loads(list(feedback_dir.glob("feedback__*.json"))[0].read_text(encoding="utf-8"))
    assert saved["reference"]["scope"] == "product"
    assert saved["reference"]["page"] == "/"


def test_feedback_page_api_saves_site(perimeter, feedback_dir, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={"scope": "site", "notation": 4, "remarques": "Clear navigation"},
    )
    assert r.status_code == 200
    saved = json.loads(list(feedback_dir.glob("feedback__*.json"))[0].read_text(encoding="utf-8"))
    assert saved["reference"]["scope"] == "site"
    assert saved["reference"]["page"] == "/"


def test_feedback_page_api_accepts_global_alias_as_site(
    perimeter, feedback_dir, client
) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={"scope": "global", "notation": 3},
    )
    assert r.status_code == 200
    saved = json.loads(list(feedback_dir.glob("feedback__*.json"))[0].read_text(encoding="utf-8"))
    assert saved["reference"]["scope"] == "site"


def test_feedback_page_api_saves_page_scope(perimeter, feedback_dir, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={
            "scope": "page",
            "page": "/pricing",
            "notation": 3,
            "remarques": "",
        },
    )
    assert r.status_code == 200
    saved = json.loads(list(feedback_dir.glob("feedback__*.json"))[0].read_text(encoding="utf-8"))
    assert saved["reference"]["scope"] == "page"
    assert saved["reference"]["page"] == "/pricing"


def test_feedback_page_api_disabled(perimeter, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={"scope": "site", "notation": 4},
    )
    assert r.status_code == 403


def test_feedback_page_api_requires_page_for_page_scope(perimeter, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    r = client.post(
        "/agent/feedback-page",
        json={"scope": "page", "notation": 4},
    )
    assert r.status_code == 400
