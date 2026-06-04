"""Unit tests for agent parsing and transcripts (no live LLM)."""

from __future__ import annotations

import json

import pytest

from app.agent import AgentResult, _enrich_ticket, _parse_agent_json
from app.content import load_scenarii_block
from app.transcripts import (
    append_chat_transcript_json,
    read_transcript_for_session,
    set_human_in_charge_for_transcript,
)


def test_parse_agent_json_minimal():
    raw = '{"reply": "Hello", "scenario": null, "scenario_state": null}'
    result = _parse_agent_json(raw)
    assert isinstance(result, AgentResult)
    assert result.reply == "Hello"
    assert result.scenario is None
    assert result.scenario_state is None


def test_parse_agent_json_with_buttons():
    raw = json.dumps(
        {
            "reply": "How was this conversation?",
            "buttons": [
                {"label": "Bad", "value": "bad"},
                {"label": "Good", "value": "good"},
            ],
        }
    )
    result = _parse_agent_json(raw)
    assert result.buttons == [
        {"label": "Bad", "value": "bad"},
        {"label": "Good", "value": "good"},
    ]


def test_transcript_stores_buttons(tmp_path, monkeypatch):
    import app.config as cfg
    import app.transcripts as tr

    session_dir = tmp_path / "session"
    data_dir = tmp_path / "data"
    session_dir.mkdir()
    data_dir.mkdir()
    index_path = data_dir / "chat_session_index.json"
    index_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cfg, "CHAT_SESSION_DIR", session_dir)
    monkeypatch.setattr(cfg, "CHAT_SESSION_INDEX_PATH", index_path)
    monkeypatch.setattr(tr, "config", cfg)

    sid = "test-session-buttons"
    buttons = [{"label": "Neutre", "value": "neutral"}]
    append_chat_transcript_json(
        "127.0.0.1",
        sid,
        "bye",
        "How was it?",
        buttons=buttons,
    )
    data = read_transcript_for_session(sid)
    assert data is not None
    asst = data["messages"][-1]
    assert asst["role"] == "assistant"
    assert asst["buttons"] == buttons


def test_enrich_ticket_overwrites_llm_timestamp():
    fake = "2024-07-30T12:00:00Z"
    out = _enrich_ticket({"summary": "Need human", "timestamp": fake}, "sess-abc")
    assert out is not None
    assert out["session_id"] == "sess-abc"
    assert out["timestamp"] != fake
    assert out["timestamp"].endswith("Z")


def test_parse_agent_json_with_fence():
    raw = '```json\n{"reply": "Hi", "handoff_signal": "agent_demande_humain"}\n```'
    result = _parse_agent_json(raw)
    assert result.reply == "Hi"
    assert result.handoff_signal == "agent_demande_humain"


def test_parse_agent_json_fallback_text():
    result = _parse_agent_json("plain text without json")
    assert result.reply == "plain text without json"


def test_scenarii_block_includes_intent_rules():
    block = load_scenarii_block()
    assert "Intent management" in block or "intent" in block.lower()
    assert "technical_support" in block.lower()


def test_transcript_human_in_charge(tmp_path, monkeypatch):
    import app.config as cfg
    import app.transcripts as tr

    session_dir = tmp_path / "session"
    data_dir = tmp_path / "data"
    session_dir.mkdir()
    data_dir.mkdir()
    index_path = data_dir / "chat_session_index.json"
    index_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cfg, "CHAT_SESSION_DIR", session_dir)
    monkeypatch.setattr(cfg, "CHAT_SESSION_INDEX_PATH", index_path)
    monkeypatch.setattr(tr, "config", cfg)

    sid = "test-session-001"
    append_chat_transcript_json("127.0.0.1", sid, "Hi", "Hello there")
    set_human_in_charge_for_transcript(sid, None, active=True)
    data = read_transcript_for_session(sid)
    assert data is not None
    assert data.get("human_in_charge") is True
    msgs = data.get("messages") or []
    assert len(msgs) >= 2
