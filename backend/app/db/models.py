"""Durable registration records. Runtime game state belongs to workers."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared ORM metadata used by the application and Alembic schema comparison."""


class RoomRecord(Base):
    """Saved room identity and expiry; a saved row does not imply a live game."""
    __tablename__ = "rooms"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(6), unique=True)
    # Room and host reference each other. Check this FK at transaction commit so
    # registration can insert the room first and its required host second.
    host_id: Mapped[UUID] = mapped_column(ForeignKey("members.id", name="fk_rooms_host", use_alter=True, deferrable=True, initially="DEFERRED"))
    # Each coordinator boot gets a new ID; previous runtime rooms cannot be joined.
    runtime_id: Mapped[UUID] = mapped_column(index=True)
    phase: Mapped[str] = mapped_column(String(16), default="lobby")
    # Persist UTC wall-clock timestamps; process-monotonic time cannot survive restart.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))


class MemberRecord(Base):
    """Registered device identity, occupied seat and hashed bearer credential."""
    __tablename__ = "members"
    # Screens and phones each have slots 0–3; the creator occupies screen slot 0.
    # Spectators are watch-only and have no slot (NULL); a separate cap limits them.
    # The unique constraint backs up the service's per-room transaction lock.
    __table_args__ = (
        UniqueConstraint("room_id", "device", "slot", name="uq_member_slot"),
        CheckConstraint("device IN ('phone', 'screen', 'spectator')", name="ck_member_device"),
        CheckConstraint("slot IS NULL OR slot BETWEEN 0 AND 3", name="ck_member_slot"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(24))
    device: Mapped[str] = mapped_column(String(9))
    slot: Mapped[int | None] = mapped_column(Integer)
    # Raw tokens are returned once to the client and never stored here.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AllocationRecord(Base):
    """Durable identity of a single, never resumed worker channel."""
    __tablename__ = 'worker_allocations'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    room_id: Mapped[UUID] = mapped_column(ForeignKey('rooms.id'), unique=True)
    report_seq: Mapped[int] = mapped_column(Integer, default=0)
    worker_url: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(32))


class AssignmentRecord(Base):
    __tablename__ = 'assignments'
    __table_args__ = (UniqueConstraint('allocation_id', 'version', 'member_id'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    allocation_id: Mapped[UUID] = mapped_column(ForeignKey('worker_allocations.id'))
    member_id: Mapped[UUID] = mapped_column(ForeignKey('members.id'))
    version: Mapped[int] = mapped_column(Integer)
    team: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(4))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MatchRecord(Base):
    __tablename__ = 'matches'
    __table_args__ = (UniqueConstraint('allocation_id', 'ordinal'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    allocation_id: Mapped[UUID] = mapped_column(ForeignKey('worker_allocations.id'))
    ordinal: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(32))


class ResultRecord(Base):
    __tablename__ = 'results'
    match_id: Mapped[UUID] = mapped_column(ForeignKey('matches.id'), primary_key=True)
    winner: Mapped[int | None] = mapped_column(Integer)  # None = drawn best of 3
    team1: Mapped[int] = mapped_column(Integer)
    team2: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
