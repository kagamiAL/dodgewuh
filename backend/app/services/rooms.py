"""Registration policy and transaction orchestration; repositories own SQL."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4
from time import monotonic
from sqlalchemy import select

from app.db.models import AllocationRecord, MemberRecord, RoomRecord
from app.repositories.history import HistoryRepository
from app.protocol import Registration
from app.repositories.members import MemberRepository
from app.repositories.rooms import RoomRepository

ROOM_LIMIT = 10
DEVICE_CAPACITY = 4
LOBBY_IDLE_TTL = timedelta(minutes=30)
ROOM_TTL = timedelta(hours=4)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class RoomError(Exception):
    """Expected registration rejection translated into the public REST error shape."""

    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


class Rooms:
    """Own registration decisions and transactions for one coordinator lifetime.

    Both repositories share a session, so room and member changes commit together.
    Repositories never commit independently or decide HTTP rejection behavior.
    """

    def __init__(self, sessions):
        self.sessions = sessions
        self.runtime_id = uuid4()
        self.reservations = {}
        self.empty_since = {}

    def start(self):
        """End former runtime sessions while preserving their durable records.

        Run one coordinator only: startup invalidates previous memberships rather
        than attempting to recover an interrupted game.
        """
        with self.sessions.begin() as db:
            now = datetime.now(timezone.utc)
            for room in db.scalars(select(RoomRecord).where(RoomRecord.closed_at.is_(None))):
                HistoryRepository(db).end(room.id, 'server_restart')
            RoomRepository(db).close_open(at=now, reason="server_restart")
            MemberRepository(db).revoke_active(at=now)

    def count(self):
        """Check SQL readiness and count this runtime's open rooms."""
        with self.sessions.begin() as db:
            rooms = RoomRepository(db)
            return rooms.count_open(self.runtime_id)

    def _create_room(self, rooms: RoomRepository, now: datetime) -> RoomRecord:
        # Hold the creation lock through commit so capacity checks and code selection
        # remain valid even when multiple HTTP requests create rooms simultaneously.
        rooms.lock_creation()
        if rooms.count_open() >= ROOM_LIMIT:
            raise RoomError(429, "SERVER_BUSY", "Room capacity reached")

        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if not rooms.code_exists(code):
                break

        room = RoomRecord(
            id=uuid4(),
            code=code,
            host_id=uuid4(),
            runtime_id=self.runtime_id,
            created_at=now,
            last_activity_at=now,
            expires_at=now + ROOM_TTL,
        )
        rooms.add(room)
        return room

    def _validate_join(self, room: RoomRecord | None, device: str, now: datetime):
        if room is None or room.closed_at or room.runtime_id != self.runtime_id:
            raise RoomError(404, "ROOM_NOT_FOUND", "Room not found")
        idle = room.phase == "lobby" and room.last_activity_at <= now - LOBBY_IDLE_TTL
        if room.expires_at <= now or idle:
            raise RoomError(404, "ROOM_NOT_FOUND", "Room expired")
        if device == "phone" and room.phase != "lobby":
            raise RoomError(409, "INVALID_PHASE", "Phones can join only in lobby")

    def register(self, name, device="screen", code=None):
        """Atomically create room+host, or validate and join a locked existing room.

        No code means creation. The context manager commits before the result
        reaches the HTTP handler; a rejected registration rolls back all writes.
        """
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as db:
            rooms = RoomRepository(db)
            members = MemberRepository(db)
            if code is None:
                room = self._create_room(rooms, now)
                member_id, slot = room.host_id, 0
            else:
                room = rooms.get_by_code_for_update(code.strip().upper())
                self._validate_join(room, device, now)
                occupied = members.occupied_slots(room.id, device)
                # Lowest vacant slot preserves the initial phone assignment order.
                slot = next((i for i in range(DEVICE_CAPACITY) if i not in occupied), None)
                if slot is None:
                    raise RoomError(409, "ROOM_FULL", "Device slots are full")
                member_id = uuid4()
                rooms.touch(room, at=now)

            # Generate 32 random bytes; store only a hash of this high-entropy secret.
            token = secrets.token_urlsafe(32)
            members.add(MemberRecord(
                id=member_id,
                room_id=room.id,
                name=name,
                device=device,
                slot=slot,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                created_at=now,
            ))
            self.reservations[str(member_id)] = monotonic()
            self.empty_since.setdefault(room.code, monotonic())
            return Registration(
                room_id=str(room.id),
                room_code=room.code,
                member_id=str(member_id),
                token=token,
                ws_path=f"/ws/rooms/{room.code}",
            )

    def authenticate(self, code, token):
        """Return detached public membership facts after checking a room-scoped secret."""
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as db:
            rooms = RoomRepository(db)
            room = rooms.get_by_code_for_update(code.strip().upper())
            self._validate_join(room, 'screen', now)
            members = MemberRepository(db).active(room.id)
            digest = hashlib.sha256(token.encode()).hexdigest()
            member = next((m for m in members if secrets.compare_digest(m.token_hash, digest)), None)
            if member is None:
                raise RoomError(401, 'UNAUTHORIZED', 'Invalid membership')
            rooms.touch(room, at=now)
            return {
                'room_id': str(room.id), 'room_code': room.code, 'host_id': str(room.host_id),
                'member_id': str(member.id),
                'members': [dict(member_id=str(m.id), name=m.name, device=m.device, slot=m.slot) for m in members],
            }

    def close_worker_room(self, code):
        """Retain interrupted room history while making all memberships unusable."""
        with self.sessions.begin() as db:
            room = RoomRepository(db).get_by_code_for_update(code)
            if room and room.runtime_id == self.runtime_id and room.closed_at is None:
                now = datetime.now(timezone.utc)
                room.closed_at, room.closed_reason = now, 'worker_lost'
                HistoryRepository(db).end(room.id, 'worker_lost')
                for member in MemberRepository(db).active(room.id):
                    member.revoked_at = now

    def lifecycle(self, code, *, phase='lobby', connected=frozenset(), remove=None, token=None):
        """Apply one serialized coordinator lifecycle decision and return live facts."""
        now, clock = datetime.now(timezone.utc), monotonic()
        with self.sessions.begin() as db:
            room = RoomRepository(db).get_by_code_for_update(code)
            if token is not None:
                self._validate_join(room, 'screen', now)
            if room is None or room.closed_at or room.runtime_id != self.runtime_id:
                return None
            members = MemberRepository(db).active(room.id)
            if token is not None:
                digest = hashlib.sha256(token.encode()).hexdigest()
                member = next((m for m in members if secrets.compare_digest(m.token_hash, digest)), None)
                if member is None:
                    raise RoomError(401, 'UNAUTHORIZED', 'Invalid membership')
                remove = str(member.id)
            room.phase = phase
            if connected:
                self.empty_since.pop(code, None)
            else:
                self.empty_since.setdefault(code, clock)
            expired = room.expires_at <= now or (phase == 'lobby' and room.last_activity_at <= now - LOBBY_IDLE_TTL)
            expired |= clock - self.empty_since.get(code, clock) >= 300
            removed = []
            for member in members:
                mid = str(member.id)
                if mid in connected:
                    self.reservations.pop(mid, None)
                else:
                    self.reservations.setdefault(mid, clock)
                stale = phase == 'lobby' and clock - self.reservations.get(mid, clock) >= 30
                if mid == remove or stale:
                    member.revoked_at, member.slot = now, None
                    removed.append(mid)
            reason = 'host_left' if str(room.host_id) == remove else 'expired'
            if expired or str(room.host_id) in removed:
                room.closed_at, room.closed_reason = now, reason
                HistoryRepository(db).end(room.id, reason)
                for member in members:
                    member.revoked_at, member.slot = now, None
                    self.reservations.pop(str(member.id), None)
                self.empty_since.pop(code, None)
                return dict(closed=reason)
            for mid in removed:
                self.reservations.pop(mid, None)
            return dict(room_id=str(room.id), room_code=code, host_id=str(room.host_id),
                        members=[dict(member_id=str(m.id), name=m.name, device=m.device, slot=m.slot)
                                 for m in members if m.revoked_at is None])

    def open_codes(self):
        with self.sessions() as db:
            return list(db.scalars(select(RoomRecord.code).where(
                RoomRecord.runtime_id == self.runtime_id, RoomRecord.closed_at.is_(None))))

    def allocate(self, code, allocation_id, url):
        with self.sessions.begin() as db:
            room = RoomRepository(db).get_by_code_for_update(code)
            self._validate_join(room, 'screen', datetime.now(timezone.utc))
            db.add(AllocationRecord(id=allocation_id, room_id=room.id, worker_url=url,
                                    created_at=datetime.now(timezone.utc), report_seq=0))

    def report(self, code, allocation_id, seq, state):
        with self.sessions.begin() as db:
            room = RoomRepository(db).get_by_code_for_update(code)
            self._validate_join(room, 'screen', datetime.now(timezone.utc))
            allocation = db.get(AllocationRecord, allocation_id)
            if allocation is None or allocation.room_id != room.id or allocation.ended_at:
                raise ValueError('Inactive allocation')
            HistoryRepository(db).report(allocation, seq, state)

    def end_allocation(self, code, allocation_id, reason):
        """End history even when another lifecycle policy already closed the room."""
        with self.sessions.begin() as db:
            room = RoomRepository(db).get_by_code_for_update(code)
            allocation = db.get(AllocationRecord, allocation_id)
            if room and room.runtime_id == self.runtime_id and allocation and allocation.room_id == room.id:
                HistoryRepository(db).end(room.id, room.closed_reason or reason)
