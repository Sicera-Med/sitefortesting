from __future__ import annotations

from typing import Any

from app.core.clock import utcnow
from app.core.context import request_id_ctx
from app.core.ids import new_id
from app.domain.models import AuditEvent, User
from app.store import Store


def record(
    store: Store,
    actor: User | None,
    action: str,
    *,
    target_id: str,
    target_type: str = "study",
    **payload: Any,
) -> AuditEvent:
    """Пишет событие аудита. События по исследованию — с target_type="study",
    чтобы таймлайн карточки собирался одним запросом."""
    return store.append_audit(
        AuditEvent(
            id=new_id("ev"),
            actor_id=actor.id if actor else None,
            actor_role=str(actor.role) if actor else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            at=utcnow(),
            payload=payload,
            request_id=request_id_ctx.get(),
        )
    )
