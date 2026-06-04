"""Apply agent result side-effects (feedback, actions)."""

from __future__ import annotations

from typing import Any, Optional

from app import actions
from app.agent import AgentResult


def persist_turn_side_effects(result: AgentResult, session_id: Optional[str]) -> None:
    if result.feedback and isinstance(result.feedback, dict):
        ref = result.feedback.get("reference") or {}
        if not isinstance(ref, dict):
            ref = {}
        actions.save_item_feedback(
            reference=ref,
            ancien_texte=str(result.feedback.get("ancien_texte") or ""),
            nouveau_texte=str(result.feedback.get("nouveau_texte") or ""),
            notation=int(result.feedback.get("notation") or 3),
            remarques=str(result.feedback.get("remarques") or ""),
            session_id=session_id,
        )

    if result.action and isinstance(result.action, dict):
        action_type = (result.action.get("type") or "").strip()
        payload = result.action.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        if action_type == "callback_request":
            actions.save_callback_action(payload, session_id)
        elif action_type == "newsletter":
            actions.save_newsletter_action(payload, session_id)
        elif action_type == "issue_reporting":
            actions.save_issue_reporting_action(payload, session_id)
        elif action_type == "survey":
            actions.save_survey_action(payload, session_id)
        elif action_type == "feedback_agent":
            actions.save_feedback_agent_action(payload, session_id)
