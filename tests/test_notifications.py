"""HTTP chat alerts: first message and human request, without a live network."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, notifications
from app.agent import AgentResult
from app.main import app
from app.notifications import (
    EVENT_CHAT_CONNECTED,
    EVENT_HUMAN_REQUESTED,
    HttpNotifier,
    events_to_notify,
)
from app.transcripts import (
    append_chat_transcript_json,
    set_human_in_charge_for_transcript,
)


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300


class _FakeClient:
    posts: list[tuple[str, dict]] = []

    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None):
        _FakeClient.posts.append((url, json))
        return _FakeResponse()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    index = tmp_path / "chat_session_index.json"
    index.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "SESSIONS_DIR", session_dir)
    monkeypatch.setattr(config, "CHAT_SESSION_INDEX_PATH", index)
    return session_dir


@pytest.fixture
def recorded(monkeypatch):
    calls: list[dict] = []

    def record(step, **kwargs):
        calls.append({"step": step, **kwargs})

    monkeypatch.setattr(notifications, "schedule_notification", record)
    return calls


@pytest.fixture
def quiet_agent(monkeypatch):
    state = {"handoff": None}

    def agent_chat_turn(*args, **kwargs):
        return AgentResult(reply="ok", handoff_signal=state["handoff"])

    monkeypatch.setattr("app.routes.agent.agent_chat_turn", agent_chat_turn)
    return state


def test_events_first_message_then_followup():
    first = events_to_notify(
        session_id="sess-1",
        prompt="hello",
        handoff_signal=None,
        existing_transcript=None,
    )
    assert first == [EVENT_CHAT_CONNECTED]

    second = events_to_notify(
        session_id="sess-1",
        prompt="again",
        handoff_signal=None,
        existing_transcript={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert second == []


def test_events_human_request_once():
    existing = {"messages": [{"role": "user", "content": "hello"}]}
    first = events_to_notify(
        session_id="sess-1",
        prompt="I want a person",
        handoff_signal="human_requires_human",
        existing_transcript=existing,
    )
    assert first == [EVENT_HUMAN_REQUESTED]

    already = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "ok", "handoff_signal": "human_requires_human"},
        ]
    }
    second = events_to_notify(
        session_id="sess-1",
        prompt="still waiting",
        handoff_signal="human_requires_human",
        existing_transcript=already,
    )
    assert second == []


def test_events_agent_offer_and_closed_session_do_not_alert():
    offer = events_to_notify(
        session_id="sess-1",
        prompt="help",
        handoff_signal="agent_demande_humain",
        existing_transcript={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert offer == []

    closed = events_to_notify(
        session_id="sess-new",
        prompt=config.CHAT_CLOSED_SESSION_PROMPT,
        handoff_signal=None,
        existing_transcript=None,
    )
    assert closed == []


def test_empty_urls_do_not_post(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_URL_CHAT_CONNECTED", "")
    monkeypatch.setattr(config, "NOTIFY_URL_HUMAN_REQUESTED", "")
    monkeypatch.setattr(notifications.threading, "Thread", _ImmediateThread)
    _FakeClient.posts = []
    monkeypatch.setattr(notifications.httpx, "Client", _FakeClient)

    notifier = HttpNotifier()
    notifier.schedule(EVENT_CHAT_CONNECTED, content="hi", session_id="s", client_ip="1.2.3.4")
    notifier.schedule(
        EVENT_HUMAN_REQUESTED,
        content="human",
        session_id="s",
        handoff_signal="human_requires_human",
    )
    assert _FakeClient.posts == []


def test_each_url_receives_only_its_event(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_URL_CHAT_CONNECTED", "http://alerts.test/connected")
    monkeypatch.setattr(config, "NOTIFY_URL_HUMAN_REQUESTED", "http://alerts.test/human")
    monkeypatch.setattr(notifications.threading, "Thread", _ImmediateThread)
    _FakeClient.posts = []
    monkeypatch.setattr(notifications.httpx, "Client", _FakeClient)

    notifier = HttpNotifier()
    long_text = "x" * 600
    notifier.schedule(
        EVENT_CHAT_CONNECTED,
        content=long_text,
        session_id="sess-1",
        client_ip="10.0.0.1",
    )
    notifier.schedule(
        EVENT_HUMAN_REQUESTED,
        content="operator please",
        session_id="sess-1",
        client_ip="10.0.0.1",
        handoff_signal="human_requires_human",
    )

    assert [url for url, _ in _FakeClient.posts] == [
        "http://alerts.test/connected",
        "http://alerts.test/human",
    ]
    connected = _FakeClient.posts[0][1]
    assert connected["event"] == EVENT_CHAT_CONNECTED
    assert connected["session_id"] == "sess-1"
    assert connected["client_ip"] == "10.0.0.1"
    assert connected["content"] == "x" * 500
    assert connected["handoff_signal"] is None
    assert connected["at"].endswith("Z")

    human = _FakeClient.posts[1][1]
    assert human["event"] == EVENT_HUMAN_REQUESTED
    assert human["handoff_signal"] == "human_requires_human"


def test_prise_en_charge_calls_both_urls(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_URL_REMOVE_CONNECTED", "http://alerts.test/remove-connected")
    monkeypatch.setattr(config, "NOTIFY_URL_REMOVE_HUMAIN", "http://alerts.test/remove-humain")
    _FakeClient.posts = []
    monkeypatch.setattr(notifications.httpx, "Client", _FakeClient)

    result = notifications.send_prise_en_charge()

    assert result["ok"] is True
    assert result["skipped"] == []
    posted = {url: body["event"] for url, body in _FakeClient.posts}
    assert posted == {
        "http://alerts.test/remove-connected": "remove_connected",
        "http://alerts.test/remove-humain": "remove_humain",
    }


def test_prise_en_charge_skips_empty_urls(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_URL_REMOVE_CONNECTED", "")
    monkeypatch.setattr(config, "NOTIFY_URL_REMOVE_HUMAIN", "")
    _FakeClient.posts = []
    monkeypatch.setattr(notifications.httpx, "Client", _FakeClient)

    result = notifications.send_prise_en_charge()

    assert result == {
        "ok": True,
        "sent": [],
        "skipped": ["remove_connected", "remove_humain"],
    }
    assert _FakeClient.posts == []


def test_route_prise_en_charge(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_USER", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(
        "app.routes.admin.send_prise_en_charge",
        lambda: {
            "ok": True,
            "sent": [
                {"event": "remove_connected", "ok": True, "status_code": 200},
                {"event": "remove_humain", "ok": True, "status_code": 200},
            ],
            "skipped": [],
        },
    )

    response = client.post("/backoffice/notify/prise-en-charge")

    assert response.status_code == 200
    body = response.json()
    assert [item["event"] for item in body["sent"]] == ["remove_connected", "remove_humain"]


def test_post_error_is_swallowed(monkeypatch):
    class Boom:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(notifications.httpx, "Client", Boom)
    notifications._post_json("http://alerts.test/connected", {"event": EVENT_CHAT_CONNECTED})


def test_route_notifies_once_per_event(sessions, client, recorded, quiet_agent):
    first = client.post("/agent/prompt", json={"prompt": "hello", "sessionId": "sess-1"})
    assert first.status_code == 200
    assert [c["step"] for c in recorded] == [EVENT_CHAT_CONNECTED]

    second = client.post("/agent/prompt", json={"prompt": "again", "sessionId": "sess-1"})
    assert second.status_code == 200
    assert [c["step"] for c in recorded] == [EVENT_CHAT_CONNECTED]

    quiet_agent["handoff"] = "human_requires_human"
    third = client.post("/agent/prompt", json={"prompt": "a human please", "sessionId": "sess-1"})
    assert third.status_code == 200
    assert [c["step"] for c in recorded] == [EVENT_CHAT_CONNECTED, EVENT_HUMAN_REQUESTED]

    fourth = client.post("/agent/prompt", json={"prompt": "still here", "sessionId": "sess-1"})
    assert fourth.status_code == 200
    assert [c["step"] for c in recorded] == [EVENT_CHAT_CONNECTED, EVENT_HUMAN_REQUESTED]


def test_route_agent_offer_connects_without_human_alert(sessions, client, recorded, quiet_agent):
    quiet_agent["handoff"] = "agent_demande_humain"
    response = client.post("/agent/prompt", json={"prompt": "help", "sessionId": "sess-offer"})
    assert response.status_code == 200
    assert [c["step"] for c in recorded] == [EVENT_CHAT_CONNECTED]


def test_route_closed_session_poll_and_human_in_charge_skip_alerts(
    sessions, client, recorded, quiet_agent
):
    closed = client.post(
        "/agent/prompt",
        json={"prompt": config.CHAT_CLOSED_SESSION_PROMPT, "sessionId": "sess-close"},
    )
    assert closed.status_code == 200
    assert closed.json().get("closed_session") is True
    assert recorded == []

    polled = client.get("/agent/prompt", params={"sessionId": "sess-close"})
    assert polled.status_code == 200
    assert recorded == []

    append_chat_transcript_json("127.0.0.1", "sess-live", "hi", "hello")
    set_human_in_charge_for_transcript("sess-live", None, active=True)
    taken = client.post("/agent/prompt", json={"prompt": "operator?", "sessionId": "sess-live"})
    assert taken.status_code == 200
    assert taken.json().get("human_in_charge") is True
    assert recorded == []
