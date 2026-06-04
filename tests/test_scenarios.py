"""One test group per chat scenario (markdown, prompt gating, parsing, side-effects)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

from app import config
from app.agent import AgentResult, _parse_agent_json
from app.content import load_scenarii_block
from app.side_effects import persist_turn_side_effects

SCENARII_DIR = config.CHAT_SCENARII_DIR


@dataclass(frozen=True)
class ScenarioSpec:
    """Defines a scenario playbook and how to validate it in tests."""

    name: str
    filename: str
    feature: Optional[str]  # perimeter feature key; None if always loaded
    always_on: bool = False
    required_sections: tuple[str, ...] = ("Triggers",)
    sample_response: Optional[dict[str, Any]] = None
    side_effect_check: Optional[str] = None  # action | feedback | handoff | ticket | none


def _sample(
    name: str,
    *,
    state: Optional[dict] = None,
    handoff: Optional[str] = None,
    ticket: Optional[dict] = None,
    feedback: Optional[dict] = None,
    action: Optional[dict] = None,
) -> dict[str, Any]:
    return {
        "reply": f"Reply for {name}.",
        "scenario": name if state else None,
        "scenario_state": state,
        "handoff_signal": handoff,
        "ticket": ticket,
        "feedback": feedback,
        "action": action,
    }


SCENARIOS: list[ScenarioSpec] = [
    ScenarioSpec(
        name="off_topic",
        filename="off_topic.md",
        feature=None,
        always_on=True,
        required_sections=("Triggers", "Action"),
        sample_response=_sample("off_topic", state=None),
        side_effect_check="none",
    ),
    ScenarioSpec(
        name="knowledge_search",
        filename="knowledge_search.md",
        feature="knowledge_search",
        sample_response=_sample("knowledge_search", state=None),
        side_effect_check="none",
    ),
    ScenarioSpec(
        name="technical_support",
        filename="technical_support.md",
        feature="troubleshooting",
        sample_response=_sample(
            "technical_support",
            state={"active": "technical_support", "step": 1, "collected": {}},
        ),
        side_effect_check="none",
    ),
    ScenarioSpec(
        name="customer_service_returns",
        filename="customer_service_returns.md",
        feature="customer_service_returns",
        sample_response=_sample(
            "customer_service_returns",
            state=None,
            ticket={
                "summary": "Return request",
                "scenario": "customer_service_returns",
                "session_id": "sess-1",
            },
        ),
        side_effect_check="ticket",
    ),
    ScenarioSpec(
        name="customer_service_order_handling",
        filename="customer_service_order_handling.md",
        feature="customer_service_order_handling",
        sample_response=_sample(
            "customer_service_order_handling",
            state=None,
            ticket={
                "summary": "Checkout failed after payment",
                "scenario": "customer_service_order_handling",
                "session_id": "sess-1",
            },
        ),
        side_effect_check="ticket",
    ),
    ScenarioSpec(
        name="callback_request",
        filename="callback_request.md",
        feature="callback_request",
        sample_response=_sample(
            "callback_request",
            state=None,
            action={
                "type": "callback_request",
                "payload": {
                    "email": "user@example.com",
                    "phone": "+33123456789",
                    "question": "Pricing",
                },
            },
        ),
        side_effect_check="action",
    ),
    ScenarioSpec(
        name="issue_reporting",
        filename="issue_reporting.md",
        feature="issue_reporting",
        sample_response=_sample(
            "issue_reporting",
            state=None,
            action={
                "type": "issue_reporting",
                "payload": {
                    "description": "Broken link on pricing page",
                    "category": "content",
                    "page": "/pricing",
                },
            },
        ),
        side_effect_check="issue_reporting",
    ),
    ScenarioSpec(
        name="newsletter",
        filename="newsletter.md",
        feature="newsletter",
        sample_response=_sample(
            "newsletter",
            state=None,
            action={
                "type": "newsletter",
                "payload": {"email": "sub@example.com", "consent": True},
            },
        ),
        side_effect_check="action",
    ),
    ScenarioSpec(
        name="survey",
        filename="survey.md",
        feature="survey",
        sample_response=_sample(
            "survey",
            state=None,
            action={"type": "survey", "payload": {"choice": "satisfied", "survey_id": "default"}},
        ),
        side_effect_check="survey",
    ),
    ScenarioSpec(
        name="feedback_page",
        filename="feedback_page.md",
        feature="feedback_page",
        sample_response=_sample(
            "feedback_page",
            state=None,
            feedback={
                "reference": {"page": "/pricing"},
                "ancien_texte": "old",
                "nouveau_texte": "new",
                "notation": 4,
                "remarques": "Clearer layout",
            },
        ),
        side_effect_check="feedback",
    ),
    ScenarioSpec(
        name="feedback_agent",
        filename="feedback_agent.md",
        feature="feedback_agent",
        sample_response=_sample(
            "feedback_agent",
            state=None,
            action={
                "type": "feedback_agent",
                "payload": {"rating": "good"},
            },
        ),
        side_effect_check="feedback_agent",
    ),
    ScenarioSpec(
        name="human_escalation",
        filename="human_escalation.md",
        feature="human_escalation",
        sample_response=_sample(
            "human_escalation",
            state=None,
            handoff="human_requires_human",
            ticket={"summary": "User wants a human", "scenario": "human_escalation"},
        ),
        side_effect_check="handoff",
    ),
]

SCENARIO_IDS = [s.name for s in SCENARIOS]


def _reset_scenarii_cache() -> None:
    import app.content as content

    content._scenarii_cache = None
    content._scenarii_mtime_key = None


def _all_features_off() -> dict[str, Any]:
    return {
        "product_type": "physical",
        "features": {key: False for key in config.FEATURE_SCENARII_FILES},
    }


def _all_features_on() -> dict[str, Any]:
    return {
        "product_type": "physical",
        "features": {key: True for key in config.FEATURE_SCENARII_FILES},
    }


@pytest.fixture
def perimeter(monkeypatch):
    """Patch load_perimeter and clear scenarii cache after each change."""

    def _apply(data: dict[str, Any]) -> None:
        monkeypatch.setattr(config, "load_perimeter", lambda: data)
        _reset_scenarii_cache()

    yield _apply
    _reset_scenarii_cache()


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Redirect action/feedback/survey dirs to a temp folder."""
    actions = tmp_path / "actions"
    feedback = tmp_path / "feedback"
    surveys = tmp_path / "surveys"
    issue_reports = tmp_path / "issue_reports"
    feedback_agent = tmp_path / "feedback_agent"
    for d in (actions, feedback, surveys, issue_reports, feedback_agent):
        d.mkdir()
    monkeypatch.setattr(config, "CHAT_ACTIONS_DIR", actions)
    monkeypatch.setattr(config, "CHAT_FEEDBACK_DIR", feedback)
    monkeypatch.setattr(config, "CHAT_SURVEYS_DIR", surveys)
    monkeypatch.setattr(config, "CHAT_ISSUE_REPORTS_DIR", issue_reports)
    monkeypatch.setattr(config, "CHAT_FEEDBACK_AGENT_DIR", feedback_agent)
    return {
        "actions": actions,
        "feedback": feedback,
        "surveys": surveys,
        "issue_reports": issue_reports,
        "feedback_agent": feedback_agent,
    }


# --- Markdown structure (one test per scenario) ---


@pytest.mark.parametrize("spec", SCENARIOS, ids=SCENARIO_IDS)
def test_scenario_markdown_file_exists_and_structure(spec: ScenarioSpec) -> None:
    path = SCENARII_DIR / spec.filename
    assert path.is_file(), f"missing {spec.filename}"
    text = path.read_text(encoding="utf-8")
    assert f"## {spec.name}" in text, f"{spec.filename} must declare ## {spec.name}"
    for section in spec.required_sections:
        assert f"**{section}" in text or f"**{section}:" in text, (
            f"{spec.filename} missing **{section}** section"
        )


def test_intent_rules_always_loaded() -> None:
    path = SCENARII_DIR / "00_intent_rules.md"
    assert path.is_file()
    block = load_scenarii_block()
    assert "Intent management" in block or "intent" in block.lower()


# --- Prompt inclusion (gated scenarios) ---


@pytest.mark.parametrize("spec", SCENARIOS, ids=SCENARIO_IDS)
def test_scenario_in_prompt_when_enabled(spec: ScenarioSpec, perimeter) -> None:
    if spec.always_on:
        block = load_scenarii_block()
        assert f"## {spec.name}" in block
        return
    assert spec.feature is not None
    features = {key: False for key in config.FEATURE_SCENARII_FILES}
    features[spec.feature] = True
    perimeter(_all_features_off() | {"features": features})
    block = load_scenarii_block()
    assert f"## {spec.name}" in block


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if not s.always_on and s.feature],
    ids=[s.name for s in SCENARIOS if not s.always_on and s.feature],
)
def test_scenario_absent_from_prompt_when_feature_disabled(
    spec: ScenarioSpec, perimeter
) -> None:
    features = {key: False for key in config.FEATURE_SCENARII_FILES}
    perimeter({"product_type": "physical", "features": features})
    block = load_scenarii_block()
    assert f"## {spec.name}" not in block


# --- LLM JSON parsing (one test per scenario) ---


@pytest.mark.parametrize("spec", SCENARIOS, ids=SCENARIO_IDS)
def test_scenario_parse_llm_json_response(spec: ScenarioSpec) -> None:
    assert spec.sample_response is not None
    raw = json.dumps(spec.sample_response, ensure_ascii=False)
    result = _parse_agent_json(raw)
    assert isinstance(result, AgentResult)
    assert result.reply == spec.sample_response["reply"]
    expected_state = spec.sample_response.get("scenario_state")
    if expected_state is None:
        assert result.scenario_state is None
    else:
        assert result.scenario_state == expected_state
        assert result.scenario_state.get("active") == spec.name


@pytest.mark.parametrize("spec", SCENARIOS, ids=SCENARIO_IDS)
def test_scenario_parse_via_agent_response_model(spec: ScenarioSpec) -> None:
    """Structured path: JSON matches AgentResponse schema for this scenario."""
    from app.agent import AgentResponse

    assert spec.sample_response is not None
    model = AgentResponse.model_validate(spec.sample_response)
    assert model.reply is not None
    if spec.sample_response.get("scenario_state"):
        assert model.scenario_state is not None
        assert model.scenario_state.active == spec.name


# --- Side-effects (scenarios that persist data) ---


def _persist(
    spec: ScenarioSpec,
    perimeter,
    isolated_storage: dict[str, Path],
    *,
    enable_feature: bool = True,
) -> AgentResult:
    features = {key: True for key in config.FEATURE_SCENARII_FILES}
    if spec.feature and not enable_feature:
        features[spec.feature] = False
    perimeter(_all_features_on() | {"features": features})
    assert spec.sample_response is not None
    result = _parse_agent_json(json.dumps(spec.sample_response))
    persist_turn_side_effects(result, "test-session-scenario")
    return result


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.side_effect_check == "action" and s.name == "callback_request"],
    ids=["callback_request"],
)
def test_scenario_callback_action_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["actions"].glob("callback__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["email"] == "user@example.com"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "newsletter"],
    ids=["newsletter"],
)
def test_scenario_newsletter_action_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["actions"].glob("newsletter__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["email"] == "sub@example.com"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "newsletter"],
    ids=["newsletter_disabled"],
)
def test_scenario_newsletter_skipped_when_feature_off(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage, enable_feature=False)
    assert list(isolated_storage["actions"].glob("newsletter__*.json")) == []


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "issue_reporting"],
    ids=["issue_reporting"],
)
def test_scenario_issue_reporting_action_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["issue_reports"].glob("issue_reporting__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["description"] == "Broken link on pricing page"
    assert data["category"] == "content"
    assert data["page"] == "/pricing"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "survey"],
    ids=["survey"],
)
def test_scenario_survey_action_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["surveys"].glob("survey__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["choice"] == "satisfied"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "feedback_agent"],
    ids=["feedback_agent"],
)
def test_scenario_feedback_agent_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["feedback_agent"].glob("feedback_agent__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["rating"] == "good"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.name == "feedback_page"],
    ids=["feedback_page"],
)
def test_scenario_feedback_page_persisted(
    spec: ScenarioSpec, perimeter, isolated_storage
) -> None:
    _persist(spec, perimeter, isolated_storage)
    files = list(isolated_storage["feedback"].glob("feedback__*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["notation"] == 4
    assert data["reference"]["page"] == "/pricing"


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.side_effect_check == "handoff"],
    ids=["human_escalation"],
)
def test_scenario_human_escalation_handoff_parsed(spec: ScenarioSpec) -> None:
    assert spec.sample_response is not None
    result = _parse_agent_json(json.dumps(spec.sample_response))
    assert result.handoff_signal == "human_requires_human"
    assert result.ticket is not None
    assert "human" in result.ticket.get("summary", "").lower()


@pytest.mark.parametrize(
    "spec",
    [s for s in SCENARIOS if s.side_effect_check == "ticket"],
    ids=[s.name for s in SCENARIOS if s.side_effect_check == "ticket"],
)
def test_scenario_ticket_parsed(spec: ScenarioSpec) -> None:
    assert spec.sample_response is not None
    result = _parse_agent_json(json.dumps(spec.sample_response))
    assert result.ticket is not None
    assert result.ticket.get("scenario") == spec.name


@pytest.mark.parametrize(
    "spec",
    [
        s
        for s in SCENARIOS
        if s.side_effect_check == "none" and s.name not in ("off_topic", "knowledge_search")
    ],
    ids=[s.name for s in SCENARIOS if s.side_effect_check == "none" and s.name not in ("off_topic", "knowledge_search")],
)
def test_scenario_multi_turn_state_active(spec: ScenarioSpec) -> None:
    """technical_support keeps scenario_state until exit."""
    assert spec.sample_response is not None
    result = _parse_agent_json(json.dumps(spec.sample_response))
    assert result.scenario_state is not None
    assert result.scenario_state["active"] == spec.name
    assert result.scenario_state.get("step", 0) >= 1


def test_off_topic_clears_scenario_state() -> None:
    spec = next(s for s in SCENARIOS if s.name == "off_topic")
    result = _parse_agent_json(json.dumps(spec.sample_response))
    assert result.scenario_state is None
