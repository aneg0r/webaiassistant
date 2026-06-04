"""Admin API for listing side-effect JSON files."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import actions, config
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    actions_dir = tmp_path / "actions"
    feedback_dir = tmp_path / "feedback"
    surveys_dir = tmp_path / "surveys"
    feedback_agent_dir = tmp_path / "feedback_agent"
    for d in (actions_dir, feedback_dir, surveys_dir, feedback_agent_dir):
        d.mkdir()
    monkeypatch.setattr(config, "CHAT_ACTIONS_DIR", actions_dir)
    monkeypatch.setattr(config, "CHAT_FEEDBACK_DIR", feedback_dir)
    monkeypatch.setattr(config, "CHAT_SURVEYS_DIR", surveys_dir)
    monkeypatch.setattr(config, "CHAT_FEEDBACK_AGENT_DIR", feedback_agent_dir)
    return {
        "actions": actions_dir,
        "feedback": feedback_dir,
        "surveys": surveys_dir,
        "feedback_agent": feedback_agent_dir,
    }


def test_records_list_actions(perimeter, isolated_storage, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"callback_request": True},
        }
    )
    actions.save_callback_action(
        {"email": "a@b.com", "phone": "+331", "question": "Demo"},
        "sess-abc",
    )
    r = client.get("/backoffice/records/list?source=actions")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "actions"
    records = data["records"]
    assert len(records) == 1
    assert records[0]["prefix"] == "callback"
    assert records[0]["session_id"] == "sess-abc"
    assert "a@b.com" in records[0]["summary"]


@pytest.fixture
def perimeter(monkeypatch):
    def _apply(data: dict):
        monkeypatch.setattr(config, "load_perimeter", lambda: data)

    yield _apply


def test_records_file_feedback(perimeter, isolated_storage, client) -> None:
    perimeter(
        {
            "product_type": "physical",
            "features": {key: False for key in config.FEATURE_SCENARII_FILES}
            | {"feedback_page": True},
        }
    )
    fname = actions.save_item_feedback(
        reference={"page": "/pricing"},
        ancien_texte="old",
        nouveau_texte="new",
        notation=4,
        remarques="Clear",
        session_id="sess-fb",
    )
    assert fname
    r = client.get(f"/backoffice/records/file?source=feedback&file={fname}")
    assert r.status_code == 200
    body = r.json()
    assert body["file"] == fname
    assert body["data"]["notation"] == 4
    assert body["data"]["reference"]["page"] == "/pricing"


def test_records_list_unknown_source(client) -> None:
    r = client.get("/backoffice/records/list?source=unknown")
    assert r.status_code == 400


def test_records_file_rejects_path_traversal(isolated_storage, client) -> None:
    r = client.get("/backoffice/records/file?source=actions&file=../session/x.json")
    assert r.status_code == 400
