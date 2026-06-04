"""Pydantic models for API request validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatTurn(BaseModel):
    """A prior message in the conversation history (excluding the current user turn)."""

    role: str = Field(..., description="user or assistant")
    content: str = Field(default="")
    from_human: bool = Field(
        default=False,
        description="True when the assistant message came from human support",
    )
    prenom: Optional[str] = Field(default=None, description="Support agent first name")


class GeminiPromptBody(BaseModel):
    """POST /agent/prompt — latest user message in prompt; optional prior messages."""

    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Latest user message (max 500 characters)",
    )
    session_id: Optional[str] = Field(
        default=None,
        alias="sessionId",
        description="Client session id (browser localStorage)",
    )
    messages: Optional[List[ChatTurn]] = Field(
        default=None,
        description="Prior turns (excluding current): alternating user / assistant",
    )


class HumanReplyBody(BaseModel):
    """POST /backoffice/human — operator reply inserted into transcript."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: Optional[str] = Field(default=None, alias="sessionId")
    file: Optional[str] = Field(
        default=None,
        description="Transcript basename in var/sessions/",
    )
    content: str = Field(..., min_length=1)
    prenom: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def require_session_or_file(self) -> "HumanReplyBody":
        if not (self.session_id or "").strip() and not (self.file or "").strip():
            raise ValueError("sessionId or file required")
        return self


class HumanInChargeBody(BaseModel):
    """POST /backoffice/human-in-charge — toggle human takeover."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: Optional[str] = Field(default=None, alias="sessionId")
    file: Optional[str] = None
    active: bool = Field(...)

    @model_validator(mode="after")
    def require_session_or_file(self) -> "HumanInChargeBody":
        if not (self.session_id or "").strip() and not (self.file or "").strip():
            raise ValueError("sessionId or file required")
        return self


class ArchiveSessionBody(BaseModel):
    """POST /backoffice/sessions/archive."""

    file: str = Field(..., min_length=1)


class FeedbackPageBody(BaseModel):
    """POST /agent/feedback-page — embeddable page feedback widget."""

    model_config = ConfigDict(populate_by_name=True)

    scope: str = Field(..., description="product, site, or page (global accepted as site)")
    notation: int = Field(..., ge=1, le=5)
    remarques: str = Field(default="", max_length=2000)
    page: Optional[str] = Field(
        default=None,
        max_length=500,
        description="URL path or page id when scope is page",
    )
    session_id: Optional[str] = Field(default=None, alias="sessionId")
