"""Chat agent — structured LLM, scenarios, no tools/MCP."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app import config
from app.content import load_faq_block, load_scenarii_block, load_wiki_excerpt
from app.llm import generate, generate_structured
from app.transcripts import read_transcript_for_session, update_scenario_state_in_transcript

MAX_HISTORY_MESSAGES = config.MAX_HISTORY_MESSAGES


class _ScenarioState(BaseModel):
    active: str
    step: int = 1
    collected: dict[str, Any] = Field(default_factory=dict)


class _TicketSchema(BaseModel):
    summary: str
    scenario: Optional[str] = None
    session_id: Optional[str] = None


class _FeedbackReference(BaseModel):
    file: Optional[str] = None
    language: Optional[str] = None
    id: Optional[int] = None
    page: Optional[str] = None


class _FeedbackSchema(BaseModel):
    reference: _FeedbackReference = Field(default_factory=_FeedbackReference)
    ancien_texte: str = ""
    nouveau_texte: str = ""
    notation: int = Field(ge=1, le=5, default=3)
    remarques: str = ""


class _ActionSchema(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class _ChoiceButtonSchema(BaseModel):
    label: str
    value: str = ""


class AgentResponse(BaseModel):
    """Expected JSON shape from the LLM."""

    reply: Optional[str] = None
    scenario: Optional[str] = None
    scenario_state: Optional[_ScenarioState] = None
    handoff_signal: Optional[Literal["agent_demande_humain", "human_requires_human"]] = None
    ticket: Optional[_TicketSchema] = None
    feedback: Optional[_FeedbackSchema] = None
    action: Optional[_ActionSchema] = None
    buttons: Optional[list[_ChoiceButtonSchema]] = None


@dataclass
class AgentResult:
    reply: str
    scenario: Optional[str] = None
    handoff_signal: Optional[str] = None
    ticket: Optional[dict[str, Any]] = None
    scenario_state: Optional[dict[str, Any]] = None
    feedback: Optional[dict[str, Any]] = None
    action: Optional[dict[str, Any]] = None
    buttons: Optional[list[dict[str, str]]] = None


def _history_lines(history: Optional[list[dict[str, Any]]]) -> str:
    if not history:
        return "(no prior messages)"
    lines: list[str] = []
    for m in history[-MAX_HISTORY_MESSAGES:]:
        role = (m.get("role") or "").strip().lower()
        content = (m.get("content") or "").strip()
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            if m.get("from_human") is True:
                pn = (m.get("prenom") or "").strip()
                prefix = f"Human support ({pn})" if pn else "Human support"
                lines.append(f"{prefix}: {content}")
            else:
                lines.append(f"Assistant: {content}")
        else:
            lines.append(f"{role or '?'}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


def _parse_buttons(raw: Any) -> Optional[list[dict[str, str]]]:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        value = str(item.get("value") or label).strip() or label
        out.append({"label": label, "value": value})
    return out if out else None


def _buttons_from_models(
    buttons: Optional[list[_ChoiceButtonSchema]],
) -> Optional[list[dict[str, str]]]:
    if not buttons:
        return None
    return _parse_buttons([b.model_dump() for b in buttons])


def _product_type_label() -> str:
    pt = (config.load_perimeter().get("product_type") or "physical").strip().lower()
    return "physical product" if pt == "physical" else "service / software offering"


def _build_concatenated_prompt(
    user_message: str,
    history: Optional[list[dict[str, str]]],
    session_id: Optional[str],
    *,
    scenario_state: Optional[dict] = None,
) -> str:
    faq = load_faq_block()
    scen = load_scenarii_block()
    hist = _history_lines(history)
    sid = (session_id or "").strip() or "(not provided)"
    product = config.PRODUCT_NAME
    off_topic = config.OFF_TOPIC_REPLY

    if scenario_state:
        state_block = json.dumps(scenario_state, ensure_ascii=False, indent=2)
    else:
        state_block = "null (no active scenario)"

    rules = f"""You are the assistant for a company offering {product} ({_product_type_label()}).
Tone: concise, solution-oriented, technical when needed.
Scope: only this product and questions covered in the FAQ below. If the question is not in the FAQ AND not related to this product, reply exactly:
{off_topic}
Reply in the user's language.
Order: read CURRENT SCENARIO STATE below; if a scenario is active, continue at the next step; otherwise detect a new scenario from SCENARII; prefer FAQ facts; escalate to human when needed.
Only one active intent at a time. Close or abandon the current scenario (scenario_state null) before starting a different one.
Handoff signals: handoff_signal = "agent_demande_humain" when you propose a human; "human_requires_human" when the user insists on a human.
If history contains "Human support:" lines, do not repeat transfer announcements or invent agent names.
Client session (for tickets): {sid}"""

    output_spec = """Respond with a SINGLE UTF-8 JSON object, no text before or after, no markdown. Schema:
{
  "reply": "text shown to the user (required)",
  "scenario": null or short scenario name,
  "scenario_state": null or {
    "active": "scenario_name",
    "step": integer_step,
    "collected": { "field": "value" }
  },
  "handoff_signal": null or "agent_demande_humain" or "human_requires_human",
  "ticket": null or {
    "summary": "1-2 sentence summary",
    "scenario": "detected scenario or null",
    "session_id": "repeat session id from above"
  },
  "feedback": null or {
    "reference": { "page": "optional URL or page id" },
    "ancien_texte": "current text if any",
    "nouveau_texte": "proposed text",
    "notation": 1-5,
    "remarques": "free comment"
  },
  "action": null or {
    "type": "callback_request" | "issue_reporting" | "newsletter" | "survey" | "feedback_agent",
    "payload": { }
  },
  "buttons": null or [
    { "label": "text on button", "value": "value sent when clicked" }
  ]
}
Rules for scenario_state:
- Increment step and fill collected each turn while the scenario continues.
- Set scenario_state to null when exit criteria are met or the user abandons.
Fill ticket when human handoff or complex support is needed (do not set timestamp — server adds it).
Fill feedback only when feedback_page scenario is complete.
Fill action when callback_request, issue_reporting, newsletter, survey, or feedback_agent data is complete and ready to persist.
For issue_reporting: record the report only — do not answer or solve the reported issue in the same turn.
When offering fixed choices (survey, feedback_agent step 2, etc.): put only the question in reply; do NOT list options with | in reply; set buttons with translated labels and stable value keys."""

    parts = [
        "=== RULES ===",
        rules,
        "=== CURRENT SCENARIO STATE ===",
        state_block,
        "=== SCENARII DOCUMENT ===",
        scen,
        "=== FAQ ===",
        faq,
        "=== HISTORY ===",
        hist,
    ]

    wiki = load_wiki_excerpt()
    if wiki:
        parts += ["=== WIKI (excerpt) ===", wiki]

    parts += [
        "=== CURRENT MESSAGE (User) ===",
        user_message.strip(),
        "=== EXPECTED OUTPUT ===",
        output_spec,
    ]
    return "\n\n".join(parts)


_JSON_FENCE = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE
)


def _parse_agent_json(raw: str) -> AgentResult:
    s = (raw or "").strip()
    if not s:
        raise RuntimeError("empty LLM text response")

    m = _JSON_FENCE.match(s)
    if m:
        s = m.group(1).strip()

    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        brace = s.find("{")
        obj = None
        if brace >= 0:
            depth = 0
            for i, ch in enumerate(s[brace:], start=brace):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(s[brace : i + 1])
                            break
                        except json.JSONDecodeError:
                            pass
        if obj is None:
            return AgentResult(reply=s)

    if not isinstance(obj, dict):
        return AgentResult(reply=raw.strip())

    reply = obj.get("reply")
    if reply is None or (isinstance(reply, str) and not reply.strip()):
        reply = raw.strip()
    else:
        reply = str(reply).strip()

    scenario = obj.get("scenario")
    scenario = None if scenario in (None, "") else str(scenario).strip() or None

    hs = obj.get("handoff_signal")
    if hs not in ("agent_demande_humain", "human_requires_human"):
        hs = None

    ticket = obj.get("ticket") if isinstance(obj.get("ticket"), dict) else None
    ss = obj.get("scenario_state") if isinstance(obj.get("scenario_state"), dict) else None
    feedback = obj.get("feedback") if isinstance(obj.get("feedback"), dict) else None
    action = obj.get("action") if isinstance(obj.get("action"), dict) else None
    buttons = _parse_buttons(obj.get("buttons"))

    return AgentResult(
        reply=reply,
        scenario=scenario,
        handoff_signal=hs,
        ticket=ticket,
        scenario_state=ss,
        feedback=feedback,
        action=action,
        buttons=buttons,
    )


def _agent_response_to_result(resp: AgentResponse) -> AgentResult:
    scenario_state = (
        resp.scenario_state.model_dump(exclude_none=True) if resp.scenario_state else None
    )
    ticket = resp.ticket.model_dump(exclude_none=True) if resp.ticket else None
    feedback = resp.feedback.model_dump(exclude_none=True) if resp.feedback else None
    action = resp.action.model_dump(exclude_none=True) if resp.action else None
    reply = (resp.reply or "").strip()
    if not reply:
        reply = "Sorry, I could not process your request."
    return AgentResult(
        reply=reply,
        scenario=resp.scenario,
        handoff_signal=resp.handoff_signal,
        ticket=ticket,
        scenario_state=scenario_state,
        feedback=feedback,
        action=action,
        buttons=_buttons_from_models(resp.buttons),
    )


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _enrich_ticket(
    ticket: Optional[dict[str, Any]], session_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if ticket is None:
        return None
    out = dict(ticket)
    sid = (session_id or "").strip()
    if sid:
        out.setdefault("session_id", sid)
    # Always server time — LLM often hallucinates a fixed placeholder date.
    out["timestamp"] = _utc_now_iso()
    return out


def agent_chat_turn(
    user_message: str,
    *,
    history: Optional[list[dict[str, str]]] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
) -> AgentResult:
    um = (user_message or "").strip()
    if not um:
        raise ValueError("prompt empty")

    scenario_state: Optional[dict] = None
    sid = (session_id or "").strip()
    if sid:
        session_data = read_transcript_for_session(sid)
        if isinstance(session_data, dict):
            raw_state = session_data.get("scenario_state")
            if isinstance(raw_state, dict):
                scenario_state = raw_state

    prompt = _build_concatenated_prompt(
        um, history, session_id, scenario_state=scenario_state
    )
    active_model = model or config.LLM_MODEL

    try:
        resp = generate_structured(
            prompt,
            AgentResponse,
            model=active_model,
            backup_model=config.LLM_MODEL_BACKUP or None,
            hedge_after=1.0,
        )
        result = _agent_response_to_result(resp)
    except Exception:
        raw = generate(prompt, model=active_model)
        result = _parse_agent_json(raw)
        if result.reply == raw.strip() and not result.action:
            result.reply = "Sorry, I could not process your request."

    if result.ticket is not None:
        result.ticket = _enrich_ticket(result.ticket, session_id)

    if sid:
        update_scenario_state_in_transcript(sid, result.scenario_state)

    return result
