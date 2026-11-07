"""Member SQL operations scoped to the same transaction as room registration."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import MemberRecord


class MemberRepository:
    """Persist members without deciding capacity, generating tokens or committing."""

    def __init__(self, session: Session):
        self.session = session

    def revoke_active(self, *, at: datetime) -> None:
        self.session.execute(
            update(MemberRecord)
            .where(MemberRecord.revoked_at.is_(None))
            .values(revoked_at=at)
        )

    def occupied_slots(self, room_id: UUID, device: str) -> set[int]:
        """Read occupied seats while the caller holds the room row lock."""
        return set(self.session.scalars(
            select(MemberRecord.slot).where(
                MemberRecord.room_id == room_id,
                MemberRecord.device == device,
                MemberRecord.revoked_at.is_(None),
                MemberRecord.slot.is_not(None),
            )
        ))

    def add(self, member: MemberRecord) -> None:
        self.session.add(member)

    def active(self, room_id: UUID) -> list[MemberRecord]:
        return list(self.session.scalars(select(MemberRecord).where(
            MemberRecord.room_id == room_id, MemberRecord.revoked_at.is_(None)
        ).order_by(MemberRecord.device, MemberRecord.slot)))
