"""Room SQL operations scoped to a caller-owned transaction."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.db.models import RoomRecord


class RoomRepository:
    """Read and write room records without committing or applying registration policy."""

    def __init__(self, session: Session):
        self.session = session

    def lock_creation(self) -> None:
        """Serialize capacity checks and code reservation until transaction completion."""
        self.session.execute(text("SELECT pg_advisory_xact_lock(724601)"))

    def close_open(self, *, at: datetime, reason: str) -> None:
        self.session.execute(
            update(RoomRecord)
            .where(RoomRecord.closed_at.is_(None))
            .values(closed_at=at, closed_reason=reason)
        )

    def close_expired(self, *, at: datetime, idle_before: datetime) -> None:
        """Apply expiry cutoffs supplied by the service, retaining room history."""
        self.session.execute(
            update(RoomRecord)
            .where(
                RoomRecord.closed_at.is_(None),
                (RoomRecord.expires_at <= at)
                | ((RoomRecord.phase == "lobby") & (RoomRecord.last_activity_at <= idle_before)),
            )
            .values(closed_at=at, closed_reason="expired")
        )

    def count_open(self, runtime_id: UUID | None = None) -> int:
        query = select(func.count()).select_from(RoomRecord).where(RoomRecord.closed_at.is_(None))
        if runtime_id is not None:
            query = query.where(RoomRecord.runtime_id == runtime_id)
        return self.session.scalar(query)

    def code_exists(self, code: str) -> bool:
        # Include closed history so old room URLs are never reassigned.
        return self.session.scalar(select(RoomRecord.id).where(RoomRecord.code == code)) is not None

    def get_by_code_for_update(self, code: str) -> RoomRecord | None:
        """Hold a row lock while the service validates and allocates a member slot."""
        return self.session.scalar(
            select(RoomRecord).where(RoomRecord.code == code).with_for_update()
        )

    def add(self, room: RoomRecord) -> None:
        self.session.add(room)
        # Insert before its host member. The reverse host FK is deferred until commit.
        self.session.flush()

    def touch(self, room: RoomRecord, *, at: datetime) -> None:
        room.last_activity_at = at
