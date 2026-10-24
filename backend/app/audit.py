from typing import Optional

from sqlmodel import Session

from app.db import engine
from app.models import AuditActor, AuditLog


def write_audit(
    entity: str,
    entity_id: str,
    actor: AuditActor | str,
    action: str,
    detail: Optional[dict] = None,
    session: Optional[Session] = None,
) -> AuditLog:
    """Append one row to audit_log. There is deliberately no update or delete counterpart.

    Pass `session` to join the caller's transaction (the caller commits).
    Without it, the row is written and committed on its own.
    """
    row = AuditLog(
        entity=entity,
        entity_id=entity_id,
        actor=AuditActor(actor),
        action=action,
        detail_json=detail,
    )
    if session is not None:
        session.add(row)
        return row
    with Session(engine) as own:
        own.add(row)
        own.commit()
        own.refresh(row)
        own.expunge(row)
    return row
