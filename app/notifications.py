"""Notification hooks — NoopNotifier by default."""

from __future__ import annotations

from typing import Any, Optional


class NoopNotifier:
    """Default notifier: does nothing."""

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


_notifier: NoopNotifier = NoopNotifier()


def get_notifier() -> NoopNotifier:
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
