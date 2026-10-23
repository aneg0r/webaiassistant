"""HTTP notification hooks. An empty event URL skips that event."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app import config

log = logging.getLogger(__name__)

EVENT_CHAT_CONNECTED = "chat_connected"
EVENT_HUMAN_REQUESTED = "human_requested"
EVENT_REMOVE_CONNECTED = "remove_connected"
EVENT_REMOVE_HUMAIN = "remove_humain"
HUMAN_REQUEST_SIGNAL = "human_requires_human"

CONTENT_MAX_CHARS = 500
TIMEOUT_SECONDS = 5.0


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _truncate(content: Optional[str]) -> Optional[str]:
    if content is None:
        return None
    text = content.strip()
    if len(text) <= CONTENT_MAX_CHARS:
        return text
    return text[:CONTENT_MAX_CHARS]


def transcript_has_human_request(transcript: Optional[dict]) -> bool:
    if not isinstance(transcript, dict):
        return False
    messages = transcript.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if isinstance(message, dict) and message.get("handoff_signal") == HUMAN_REQUEST_SIGNAL:
            return True
    return False


def events_to_notify(
    *,
    session_id: Optional[str],
    prompt: str,
    handoff_signal: Optional[str],
    existing_transcript: Optional[dict],
) -> list[str]:
    """Which alerts this turn should send. Closed sessions send nothing."""
    if (prompt or "").strip() == config.CHAT_CLOSED_SESSION_PROMPT:
        return []

    events: list[str] = []
    sid = (session_id or "").strip()
    if sid and not isinstance(existing_transcript, dict):
        events.append(EVENT_CHAT_CONNECTED)
    if handoff_signal == HUMAN_REQUEST_SIGNAL and not transcript_has_human_request(
        existing_transcript
    ):
        events.append(EVENT_HUMAN_REQUESTED)
    return events


class NoopNotifier:
    """Notifier that drops every event."""

    def schedule(
        self,
        step: str,
        *,
        content: Optional[str] = None,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        pass


class HttpNotifier:
    """GET one URL per event, with the alert fields as query parameters."""

    def url_for(self, step: str) -> str:
        if step == EVENT_CHAT_CONNECTED:
            return config.NOTIFY_URL_CHAT_CONNECTED
        if step == EVENT_HUMAN_REQUESTED:
            return config.NOTIFY_URL_HUMAN_REQUESTED
        return ""

    def schedule(
        self,
        step: str,
        *,
        content: Optional[str] = None,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        handoff_signal: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        url = (self.url_for(step) or "").strip()
        if not url:
            return
        payload = _payload(
            step,
            content=content,
            client_ip=client_ip,
            session_id=session_id,
            handoff_signal=handoff_signal,
        )
        threading.Thread(
            target=_get_notification,
            args=(url, payload),
            daemon=True,
            name="notify-http",
        ).start()


def _get_notification(url: str, payload: dict[str, Any]) -> None:
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            client.get(url, params=_query_params(payload))
    except Exception:
        log.exception("HTTP notification failed event=%s", payload.get("event"))


_notifier: HttpNotifier = HttpNotifier()


def get_notifier() -> HttpNotifier:
    return _notifier


def schedule_notification(
    step: str,
    *,
    content: Optional[str] = None,
    client_ip: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    _notifier.schedule(
        step,
        content=content,
        client_ip=client_ip,
        session_id=session_id,
        **kwargs,
    )


def _prise_en_charge_jobs() -> list[tuple[str, str]]:
    return [
        (EVENT_REMOVE_CONNECTED, (config.NOTIFY_URL_REMOVE_CONNECTED or "").strip()),
        (EVENT_REMOVE_HUMAIN, (config.NOTIFY_URL_REMOVE_HUMAIN or "").strip()),
    ]


def _payload(event: str, *, content: Optional[str] = None, client_ip: Optional[str] = None, session_id: Optional[str] = None, handoff_signal: Optional[str] = None) -> dict[str, Any]:
    return {
        "event": event,
        "session_id": (session_id or "").strip() or None,
        "client_ip": (client_ip or "").strip() or None,
        "content": _truncate(content),
        "handoff_signal": handoff_signal,
        "at": _utc_now_iso(),
    }


def _query_params(payload: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        params[key] = str(value)
    return params


def _get_result(event: str, url: str) -> dict[str, Any]:
    payload = _payload(event)
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.get(url, params=_query_params(payload))
        return {
            "event": event,
            "ok": response.is_success,
            "status_code": response.status_code,
        }
    except Exception as exc:
        log.exception("HTTP notification failed event=%s", event)
        return {"event": event, "ok": False, "error": str(exc)}


def send_prise_en_charge() -> dict[str, Any]:
    """GET the two operator clear-alert URLs at the same time."""
    jobs = _prise_en_charge_jobs()
    active = [(event, url) for event, url in jobs if url]
    skipped = [event for event, url in jobs if not url]
    if not active:
        return {"ok": True, "sent": [], "skipped": skipped}

    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def run(event: str, url: str) -> None:
        item = _get_result(event, url)
        with lock:
            results.append(item)

    threads = [
        threading.Thread(target=run, args=(event, url), daemon=True, name="notify-http")
        for event, url in active
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT_SECONDS + 1.0)

    by_event = {item["event"]: item for item in results}
    sent: list[dict[str, Any]] = []
    for event, _url in active:
        sent.append(by_event.get(event) or {"event": event, "ok": False, "error": "timeout"})
    return {"ok": all(item.get("ok") for item in sent), "sent": sent, "skipped": skipped}


def notify_turn(
    *,
    session_id: Optional[str],
    client_ip: Optional[str],
    content: str,
    handoff_signal: Optional[str],
    existing_transcript: Optional[dict],
) -> None:
    """Schedule connection and human-request alerts for one chat turn."""
    try:
        for event in events_to_notify(
            session_id=session_id,
            prompt=content,
            handoff_signal=handoff_signal,
            existing_transcript=existing_transcript,
        ):
            signal = HUMAN_REQUEST_SIGNAL if event == EVENT_HUMAN_REQUESTED else None
            schedule_notification(
                event,
                content=content,
                client_ip=client_ip,
                session_id=session_id,
                handoff_signal=signal,
            )
    except Exception:
        log.exception("failed to schedule chat notification")
